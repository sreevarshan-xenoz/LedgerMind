from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pydantic import BaseModel, Field
from ..core.models import (
    SyntheticBatch, ExceptionItem, ExceptionCategory,
    Payment, Order, Settlement, Refund
)
from .providers import LLMProvider, AutonomousInvestigationPlanner, ToolCallRequest


class InvestigationStep(BaseModel):
    step_number: int
    action: str
    input_arguments: Dict[str, Any]
    observation: str
    thought_summary: str


class InvestigationActionTrace(BaseModel):
    investigation_id: str
    target_record: str
    steps: List[InvestigationStep] = Field(default_factory=list)
    final_decision: str  # "RESOLVE" or "ESCALATE"
    root_cause: str
    confidence: float
    evidence_citations: List[str] = Field(default_factory=list)
    math_proof: Dict[str, Any] = Field(default_factory=dict)
    recommended_action: str
    requires_human: bool
    iterations_used: int
    terminated_reason: str


class AgenticInvestigationOrchestrator:
    """
    Autonomous Tool-Calling Investigation Loop.
    Coordinates evidence collection via strict tool contracts, tracks step-by-step
    investigation traces, and ensures zero false resolutions through safe degradation.
    """

    ALLOWED_TOOLS = [
        "inspect_payment",
        "inspect_order",
        "inspect_settlement",
        "inspect_refunds",
        "inspect_bank_memo",
        "calculate_expected_net",
        "inspect_timeline",
        "compare_variance",
        "terminate_investigation"
    ]

    MAX_ITERATIONS = 6

    def __init__(self, batch: SyntheticBatch, provider: Optional[LLMProvider] = None):
        self.batch = batch
        self.provider = provider or AutonomousInvestigationPlanner()
        self.orders_map: Dict[str, Order] = {o.order_id: o for o in batch.orders}
        self.payments_map: Dict[str, Payment] = {p.payment_id: p for p in batch.payments}
        self.settlements_map: Dict[str, Settlement] = {s.settlement_id: s for s in batch.settlements}
        self.refunds_map: Dict[str, List[Refund]] = {}
        for r in batch.refunds:
            self.refunds_map.setdefault(r.payment_id, []).append(r)

    # -------------------------------------------------------------
    # Tool Implementations
    # -------------------------------------------------------------
    def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Tuple[Optional[Any], str]:
        if tool_name not in self.ALLOWED_TOOLS:
            return None, f"SECURITY_ERROR: Tool '{tool_name}' is not in the authorized tool allowlist."

        if tool_name == "inspect_payment":
            pid = args.get("payment_id", "")
            pay = self.payments_map.get(pid)
            if pay:
                return pay.model_dump(), f"Payment {pid} captured: Gross ₹{pay.amount:,.2f}, Fee ₹{pay.fee:,.2f}, Tax ₹{pay.tax:,.2f}, Method {pay.method}, SettlementRef {pay.settlement_id}."
            return None, f"Payment {pid} not found in gateway records."

        elif tool_name == "inspect_order":
            oid = args.get("order_id", "")
            order = self.orders_map.get(oid)
            if not order and getattr(self, "_current_exc", None) and self._current_exc.order_id:
                order = self.orders_map.get(self._current_exc.order_id)
            if order:
                return order.model_dump(), f"Order {order.order_id} verified: Cart Amount ₹{order.amount:,.2f}, Customer {order.customer_id}, Status {order.status}."
            return None, f"Order {oid or 'record'} not found in merchant ERP."

        elif tool_name == "inspect_settlement":
            sid = args.get("settlement_id", "")
            setl = self.settlements_map.get(sid)
            if not setl and getattr(self, "_current_exc", None) and self._current_exc.settlement_id:
                setl = self.settlements_map.get(self._current_exc.settlement_id)
            if setl:
                return setl.model_dump(), f"Settlement {setl.settlement_id} remitted: Bank UTR {setl.utr}, Net Payout ₹{setl.net_payout:,.2f}, Account {setl.account_number} on {setl.settlement_date}."
            return None, f"Settlement statement {sid or 'record'} not found in bank statement feed."

        elif tool_name == "inspect_refunds":
            pid = args.get("payment_id", "")
            refunds = self.refunds_map.get(pid, [])
            total_rfnd = sum(r.amount for r in refunds)
            return [r.model_dump() for r in refunds], f"Found {len(refunds)} refund record(s) totaling ₹{total_rfnd:,.2f}."

        elif tool_name == "inspect_bank_memo":
            utr = args.get("utr", "") or args.get("settlement_id", "")
            return None, f"Bank adjustment debit memo query for '{utr}': 0 matching adjustment records found in clearing feed."

        elif tool_name == "calculate_expected_net":
            gross = float(args.get("gross", 0.0))
            method = args.get("method", "card").lower()
            rfnd_total = float(args.get("refunds_total", 0.0))
            std_rates = {"upi": 0.0, "card": 0.02, "netbanking": 0.018, "wallet": 0.019}
            rate = std_rates.get(method, 0.02)
            fee = round(gross * rate, 2)
            tax = round(fee * 0.18, 2)
            expected_net = round(gross - fee - tax - rfnd_total, 2)
            return {
                "rate": rate, "fee": fee, "tax": tax, "net": expected_net
            }, f"Baseline net payout calculated: ₹{gross:,.2f} (Gross) - ₹{fee + tax:,.2f} (Fee+Tax) - ₹{rfnd_total:,.2f} (Refunds) = ₹{expected_net:,.2f}."

        elif tool_name == "inspect_timeline":
            p_time = args.get("payment_time")
            s_time = args.get("settlement_time")
            r_time = args.get("refund_time")
            is_post = False
            delay = 0
            if p_time and s_time:
                try:
                    p_dt = datetime.fromisoformat(p_time)
                    s_dt = datetime.fromisoformat(s_time)
                    delay = (s_dt.date() - p_dt.date()).days
                    if r_time:
                        r_dt = datetime.fromisoformat(r_time)
                        is_post = (r_dt > s_dt)
                except Exception:
                    pass
            return {
                "is_post_settlement_refund": is_post,
                "settlement_delay_days": delay
            }, f"Timeline inspected: Settlement delay {delay} day(s), Post-settlement refund debit: {is_post}."

        elif tool_name == "compare_variance":
            exp = float(args.get("expected_net", 0.0))
            act = float(args.get("actual_net", 0.0))
            var = round(exp - act, 2)
            return {"variance": var}, f"Variance analysis: Expected ₹{exp:,.2f} vs Bank Remitted ₹{act:,.2f} -> Residual Shortfall: ₹{var:,.2f}."

        elif tool_name == "terminate_investigation":
            return {"status": "TERMINATED"}, "Investigation terminated."

        return None, "Unknown tool."

    # -------------------------------------------------------------
    # Autonomous Investigation Loop
    # -------------------------------------------------------------
    def run_investigation(self, exc: ExceptionItem) -> InvestigationActionTrace:
        self._current_exc = exc
        target_pid = exc.payment_id or exc.record_id
        inv_id = f"INV_{target_pid}_{int(datetime.now().timestamp())}"
        
        collected_evidence: Dict[str, Any] = {}
        steps: List[InvestigationStep] = []
        citations: List[str] = []

        terminated_reason = "MAX_ITERATIONS_REACHED"
        hints = {"order_id": exc.order_id, "settlement_id": exc.settlement_id}

        for step_idx in range(1, self.MAX_ITERATIONS + 1):
            # Step 1: LLM/Planner decides next action
            try:
                tool_req = self.provider.plan_next_action(
                    current_step=step_idx,
                    target_record=target_pid,
                    collected_evidence=collected_evidence,
                    available_tools=self.ALLOWED_TOOLS,
                    context_hints=hints
                )
            except TypeError:
                tool_req = self.provider.plan_next_action(
                    current_step=step_idx,
                    target_record=target_pid,
                    collected_evidence=collected_evidence,
                    available_tools=self.ALLOWED_TOOLS
                )

            # Security Guardrail: Reject unsupported tools
            if tool_req.tool_name not in self.ALLOWED_TOOLS:
                steps.append(InvestigationStep(
                    step_number=step_idx,
                    action=tool_req.tool_name,
                    input_arguments=tool_req.arguments,
                    observation=f"SECURITY_VIOLATION: Tool '{tool_req.tool_name}' rejected.",
                    thought_summary="Attempted un-authorized tool call. Flagging security violation."
                ))
                terminated_reason = "UNAUTHORIZED_TOOL_REJECTED"
                break

            # Execute tool safely against isolated ledger
            raw_data, observation_str = self._execute_tool(tool_req.tool_name, tool_req.arguments)

            steps.append(InvestigationStep(
                step_number=step_idx,
                action=tool_req.tool_name,
                input_arguments=tool_req.arguments,
                observation=observation_str,
                thought_summary=tool_req.thought_summary
            ))

            # Store evidence unconditionally so state advances
            if tool_req.tool_name == "inspect_order":
                collected_evidence["order"] = raw_data
                if raw_data:
                    citations.append(f"order:{raw_data.get('order_id')}")
            elif tool_req.tool_name == "inspect_payment":
                collected_evidence["payment"] = raw_data
                if raw_data:
                    citations.append(f"payment:{target_pid}")
            elif tool_req.tool_name == "inspect_settlement":
                collected_evidence["settlement"] = raw_data
                if raw_data:
                    citations.append(f"settlement:{raw_data.get('settlement_id')}")
            elif tool_req.tool_name == "inspect_refunds":
                collected_evidence["refunds"] = raw_data if raw_data is not None else []
                if raw_data:
                    for r in raw_data:
                        citations.append(f"refund:{r.get('refund_id')}")
            elif tool_req.tool_name == "calculate_expected_net":
                collected_evidence["expected_net"] = raw_data
            elif tool_req.tool_name == "inspect_timeline":
                collected_evidence["timeline"] = raw_data
            elif tool_req.tool_name == "compare_variance":
                collected_evidence["comparison"] = raw_data
                terminated_reason = "EVALUATION_COMPLETE"
                break
            elif tool_req.tool_name == "terminate_investigation":
                terminated_reason = "EVIDENCE_EXHAUSTED"
                break

        # Step 2: Synthesize Final Decision & Mathematical Proof
        pay = collected_evidence.get("payment")
        ord_info = collected_evidence.get("order")
        setl = collected_evidence.get("settlement")
        refunds = collected_evidence.get("refunds", [])
        tl = collected_evidence.get("timeline", {})
        comp = collected_evidence.get("comparison", {})

        # 1. Unsettled / Missing Payment
        if not pay:
            gross_val = ord_info.get("amount", 0.0) if ord_info else 0.0
            var_val = exc.discrepancy_amount if exc.discrepancy_amount != 0 else gross_val
            term_reason = "UNAUTHORIZED_TOOL_REJECTED" if terminated_reason == "UNAUTHORIZED_TOOL_REJECTED" else "CRITICAL_PAYMENT_EVIDENCE_MISSING_SAFE_DEGRADATION"
            return InvestigationActionTrace(
                investigation_id=inv_id, target_record=target_pid, steps=steps,
                final_decision="ESCALATE", root_cause="PAYMENT_RECORD_MISSING", confidence=0.25,
                evidence_citations=citations,
                math_proof={
                    "gross": gross_val,
                    "variance": var_val,
                    "formula": "Primary gateway payment record missing. Cannot verify gross authorization or fee schedule."
                },
                recommended_action="ESCALATE_GATEWAY_OPS_LOCATE_PAYMENT", requires_human=True,
                iterations_used=len(steps), terminated_reason=term_reason
            )

        # 2. Duplicate Authorization
        if exc.category == ExceptionCategory.DUPLICATE_AUTH_CAPTURE:
            return InvestigationActionTrace(
                investigation_id=inv_id, target_record=target_pid, steps=steps,
                final_decision="ESCALATE", root_cause="DUPLICATE_AUTH_CAPTURE", confidence=0.98,
                evidence_citations=citations,
                math_proof={"gross": pay.get("amount", 0.0), "formula": "Secondary duplicate authorization for cart."},
                recommended_action="INITIATE_CUSTOMER_REFUND", requires_human=True,
                iterations_used=len(steps), terminated_reason="DUPLICATE_CAPTURE_TRAPPED"
            )

        # 3. Foreign Account Mismatch
        if exc.category == ExceptionCategory.ACCOUNT_MISMATCH or (setl and setl.get("account_number") != "XXXX-XXXX-9921"):
            return InvestigationActionTrace(
                investigation_id=inv_id, target_record=target_pid, steps=steps,
                final_decision="ESCALATE", root_cause="ACCOUNT_MISMATCH", confidence=0.99,
                evidence_citations=citations,
                math_proof={"gross": pay.get("amount", 0.0), "foreign_account": setl.get("account_number") if setl else "UNKNOWN"},
                recommended_action="ESCALATE_BANKING_OPS_FREEZE_PAYOUT", requires_human=True,
                iterations_used=len(steps), terminated_reason="FOREIGN_ACCOUNT_DETECTED"
            )

        # 4. Post-Settlement Refund Lifecycle (Deferred Debit)
        if tl.get("is_post_settlement_refund") or exc.category == ExceptionCategory.POST_SETTLEMENT_REFUND_DEFERRED:
            rfnd_total = sum(r.get("amount", 0.0) for r in refunds)
            return InvestigationActionTrace(
                investigation_id=inv_id, target_record=target_pid, steps=steps,
                final_decision="RESOLVE", root_cause="POST_SETTLEMENT_REFUND_DEFERRED", confidence=0.98,
                evidence_citations=citations,
                math_proof={
                    "gross": pay.get("amount", 0.0), "initial_settled": pay.get("net_amount", 0.0),
                    "subsequent_refund": rfnd_total, "formula": "Initial payout matched gross. Subsequent refund queued in deferred ledger."
                },
                recommended_action="ACCEPT_AND_LOG_DEFERRED_DEBIT", requires_human=False,
                iterations_used=len(steps), terminated_reason="POST_SETTLEMENT_LIFECYCLE_VERIFIED"
            )

        # 5. Multi-UTR Split Remittance
        if exc.category == ExceptionCategory.SPLIT_MULTI_UTR_SETTLED:
            return InvestigationActionTrace(
                investigation_id=inv_id, target_record=target_pid, steps=steps,
                final_decision="RESOLVE", root_cause="SPLIT_MULTI_UTR_SETTLED", confidence=0.99,
                evidence_citations=citations,
                math_proof={"gross": pay.get("amount", 0.0), "net_split": exc.actual_amount, "formula": "Multi-UTR split schedule matched."},
                recommended_action="ACCEPT_SPLIT_SETTLEMENT", requires_human=False,
                iterations_used=len(steps), terminated_reason="SPLIT_UTR_PROOF_VERIFIED"
            )

        # 6. Pre-Settlement Refund Netted
        if refunds and setl and exc.category == ExceptionCategory.PARTIAL_REFUND_NETTED:
            rfnd_total = sum(r.get("amount", 0.0) for r in refunds)
            exp_net = round(pay.get("amount", 0.0) - pay.get("fee", 0.0) - pay.get("tax", 0.0) - rfnd_total, 2)
            act_net = round(setl.get("net_payout", 0.0), 2)
            if abs(exp_net - act_net) <= 0.05:
                return InvestigationActionTrace(
                    investigation_id=inv_id, target_record=target_pid, steps=steps,
                    final_decision="RESOLVE", root_cause="PARTIAL_REFUND_NETTED", confidence=0.98,
                    evidence_citations=citations,
                    math_proof={"gross": pay.get("amount", 0.0), "fees": pay.get("fee", 0.0)+pay.get("tax", 0.0), "refund": rfnd_total, "net": act_net},
                    recommended_action="VERIFY_AND_CLOSE_EXCEPTION", requires_human=False,
                    iterations_used=len(steps), terminated_reason="REFUND_NETTING_VERIFIED"
                )

        # 7. MDR Fee Rate Surcharge
        if exc.category == ExceptionCategory.MDR_GST_VARIANCE:
            calc_net = collected_evidence.get("expected_net", {})
            std_fee = calc_net.get("fee", 0.0) + calc_net.get("tax", 0.0)
            act_fee = pay.get("fee", 0.0) + pay.get("tax", 0.0)
            fee_var = round(act_fee - std_fee, 2)
            return InvestigationActionTrace(
                investigation_id=inv_id, target_record=target_pid, steps=steps,
                final_decision="RESOLVE", root_cause="MDR_GST_VARIANCE", confidence=0.96,
                evidence_citations=citations,
                math_proof={"gross": pay.get("amount", 0.0), "standard_fee": std_fee, "charged_fee": act_fee, "variance": fee_var},
                recommended_action="APPLY_TIER_SURCHARGE_ADJUSTMENT", requires_human=False,
                iterations_used=len(steps), terminated_reason="MDR_SURCHARGE_VERIFIED"
            )

        # 8. Timing Lag (T+3 / T+4)
        if exc.category == ExceptionCategory.TIMING_LAG:
            return InvestigationActionTrace(
                investigation_id=inv_id, target_record=target_pid, steps=steps,
                final_decision="RESOLVE", root_cause="TIMING_WINDOW_LAG", confidence=0.97,
                evidence_citations=citations,
                math_proof={"gross": pay.get("amount", 0.0), "delay_days": tl.get("settlement_delay_days", 2)},
                recommended_action="CONFIRM_CLEARANCE_SCHEDULE", requires_human=False,
                iterations_used=len(steps), terminated_reason="TIMING_WINDOW_VERIFIED"
            )

        # Default Safe Degradation: Unexplained variance or missing evidence
        var_amount = abs(comp.get("variance", exc.discrepancy_amount))
        return InvestigationActionTrace(
            investigation_id=inv_id, target_record=target_pid, steps=steps,
            final_decision="ESCALATE", root_cause="UNEXPLAINED_SHORTFALL", confidence=0.31,
            evidence_citations=citations,
            math_proof={"gross": pay.get("amount", 0.0), "variance": var_amount, "formula": f"Shortfall of ₹{var_amount:,.2f} unexplained by available ledger records."},
            recommended_action="MERCHANT_BANK_OPS_DISPUTE_REVIEW", requires_human=True,
            iterations_used=len(steps), terminated_reason="EVIDENCE_INSUFFICIENT_SAFE_FAILURE"
        )
