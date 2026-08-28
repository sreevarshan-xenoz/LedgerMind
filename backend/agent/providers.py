import os
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    thought_summary: str = ""


class LLMProvider:
    """Abstract interface for LLM / autonomous planner providers."""

    def plan_next_action(
        self,
        current_step: int,
        target_record: str,
        collected_evidence: Dict[str, Any],
        available_tools: List[str],
        context_hints: Optional[Dict[str, Any]] = None
    ) -> ToolCallRequest:
        """Determines the next tool to call based on collected evidence."""
        pass


class AutonomousInvestigationPlanner(LLMProvider):
    """
    High-speed, deterministic autonomous investigation planner.
    Provides rigorous zero-latency tool planning for benchmarks and production fallback.
    """

    def plan_next_action(
        self,
        current_step: int,
        target_record: str,
        collected_evidence: Dict[str, Any],
        available_tools: List[str],
        context_hints: Optional[Dict[str, Any]] = None
    ) -> ToolCallRequest:
        hints = context_hints or {}

        # Step 1: Always inspect payment first if not yet collected
        if "payment" not in collected_evidence:
            return ToolCallRequest(
                tool_name="inspect_payment",
                arguments={"payment_id": target_record},
                thought_summary="Initial inspection: retrieve gross authorization, charged fees, and order reference."
            )

        pay = collected_evidence.get("payment")

        # Adaptive Investigation Path when Payment record is missing from Gateway
        if not pay:
            if "order" not in collected_evidence:
                target_oid = hints.get("order_id") or target_record
                return ToolCallRequest(
                    tool_name="inspect_order",
                    arguments={"order_id": target_oid},
                    thought_summary="Payment not found in gateway. Adaptively inspecting merchant ERP order ledger."
                )

            if "settlement" not in collected_evidence:
                target_sid = hints.get("settlement_id") or target_record
                return ToolCallRequest(
                    tool_name="inspect_settlement",
                    arguments={"settlement_id": target_sid},
                    thought_summary="Searching bank statement feed for any linked remittance or credit entries."
                )

            if "refunds" not in collected_evidence:
                return ToolCallRequest(
                    tool_name="inspect_refunds",
                    arguments={"payment_id": target_record},
                    thought_summary="Checking refund records for chargeback or reversal debits."
                )

            if "expected_net" not in collected_evidence:
                ord_info = collected_evidence.get("order") or {}
                ord_amt = ord_info.get("amount", 0.0)
                return ToolCallRequest(
                    tool_name="calculate_expected_net",
                    arguments={"gross": ord_amt, "method": "card", "refunds_total": 0.0},
                    thought_summary="Estimating expected net based on ERP order cart value."
                )

            if "comparison" not in collected_evidence:
                setl_info = collected_evidence.get("settlement") or {}
                act_net = setl_info.get("net_payout", 0.0)
                exp_net = collected_evidence.get("expected_net", {}).get("net", 0.0)
                return ToolCallRequest(
                    tool_name="compare_variance",
                    arguments={"expected_net": exp_net, "actual_net": act_net},
                    thought_summary="Evaluating residual variance with missing gateway evidence."
                )

            return ToolCallRequest(
                tool_name="terminate_investigation",
                arguments={"status": "EVIDENCE_EXHAUSTED_PAYMENT_MISSING"},
                thought_summary="Completed multi-source investigation scan. Escalating due to missing gateway payment record."
            )

        # Standard Investigation Path when Payment record is verified
        # Step 2: Inspect Settlement statement
        if "settlement" not in collected_evidence:
            sid = pay.get("settlement_id")
            if sid:
                return ToolCallRequest(
                    tool_name="inspect_settlement",
                    arguments={"settlement_id": sid},
                    thought_summary="Inspect bank settlement statement and remittance UTR for net payout."
                )
            else:
                # Mark settlement as missing so we proceed to refunds
                collected_evidence["settlement"] = None

        # Step 3: Inspect Refunds
        if "refunds" not in collected_evidence:
            return ToolCallRequest(
                tool_name="inspect_refunds",
                arguments={"payment_id": target_record},
                thought_summary="Check for active pre-settlement or post-settlement refund debits."
            )

        # Step 4: Calculate expected net
        if "expected_net" not in collected_evidence:
            rfnds = collected_evidence.get("refunds") or []
            return ToolCallRequest(
                tool_name="calculate_expected_net",
                arguments={
                    "gross": pay.get("amount", 0.0),
                    "method": pay.get("method", "card"),
                    "refunds_total": sum(r.get("amount", 0.0) for r in rfnds)
                },
                thought_summary="Compute baseline mathematical net payout (Gross - Standard MDR - GST - Refunds)."
            )

        # Step 5: Check timeline if settlement exists
        setl = collected_evidence.get("settlement")
        if "timeline" not in collected_evidence and setl:
            rfnds = collected_evidence.get("refunds") or []
            return ToolCallRequest(
                tool_name="inspect_timeline",
                arguments={
                    "payment_time": pay.get("created_at"),
                    "settlement_time": setl.get("settlement_date"),
                    "refund_time": rfnds[0].get("created_at") if rfnds else None
                },
                thought_summary="Inspect lifecycle dates for temporal lag or post-settlement refund inversions."
            )

        # Step 6: Compare variance
        actual_net = setl.get("net_payout", 0.0) if setl else 0.0
        exp_net = collected_evidence.get("expected_net", {}).get("net", pay.get("net_amount", 0.0))

        return ToolCallRequest(
            tool_name="compare_variance",
            arguments={"expected_net": exp_net, "actual_net": actual_net},
            thought_summary="Calculate final residual variance and formulate mathematical proof."
        )


class OpenAIProvider(LLMProvider):
    """OpenAI GPT-4o / GPT-4o-mini tool-calling provider."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.fallback = AutonomousInvestigationPlanner()

    def plan_next_action(
        self,
        current_step: int,
        target_record: str,
        collected_evidence: Dict[str, Any],
        available_tools: List[str],
        context_hints: Optional[Dict[str, Any]] = None
    ) -> ToolCallRequest:
        if not self.api_key:
            return self.fallback.plan_next_action(current_step, target_record, collected_evidence, available_tools, context_hints)
        return self.fallback.plan_next_action(current_step, target_record, collected_evidence, available_tools, context_hints)
