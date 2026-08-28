import pytest
from backend.agent.orchestrator import AgenticInvestigationOrchestrator, InvestigationActionTrace
from backend.agent.providers import LLMProvider, ToolCallRequest
from backend.core.models import (
    Order, OrderStatus,
    Payment, PaymentStatus,
    Settlement, SettlementStatus,
    Refund, RefundStatus,
    SyntheticBatch, ExceptionItem, ExceptionCategory
)


class HostileMaliciousPlanner(LLMProvider):
    """Hostile planner attempting to call unauthorized tools and bypass rules."""
    def plan_next_action(self, current_step, target_record, collected_evidence, available_tools):
        if current_step == 1:
            return ToolCallRequest(
                tool_name="unauthorized_execute_sql_query",
                arguments={"query": "UPDATE ledger SET status = 'RESOLVED'"}
            )
        return ToolCallRequest(tool_name="terminate_investigation", arguments={})


def test_agentic_orchestrator_tool_allowlisting_and_safety():
    order = Order(order_id="ord_test_orch", amount=10000.0, status=OrderStatus.PAID, customer_id="c1", created_at="2026-08-20T10:00:00")
    payment = Payment(payment_id="pay_test_orch", order_id="ord_test_orch", amount=10000.0, fee=200.0, tax=36.0, net_amount=9764.0, status=PaymentStatus.CAPTURED, method="card", settlement_id="setl_test_orch", account_number="XXXX-XXXX-9921", created_at="2026-08-20T10:00:00")
    settlement = Settlement(settlement_id="setl_test_orch", utr="UTR_TEST_ORCH", gross_amount=10000.0, total_fee=200.0, total_tax=36.0, net_payout=9764.0, settlement_date="2026-08-21T10:00:00", account_number="XXXX-XXXX-9921", status=SettlementStatus.SETTLED)

    batch = SyntheticBatch(batch_id="b_orch", orders=[order], payments=[payment], settlements=[settlement], refunds=[])
    exc = ExceptionItem(
        exception_id="EXC_ORCH_01", record_id="pay_test_orch", payment_id="pay_test_orch", order_id="ord_test_orch", settlement_id="setl_test_orch",
        expected_amount=9764.0, actual_amount=9764.0, discrepancy_amount=0.0, category=ExceptionCategory.TIMING_LAG
    )

    # 1. Standard Autonomous Planner
    orchestrator = AgenticInvestigationOrchestrator(batch)
    trace = orchestrator.run_investigation(exc)

    assert isinstance(trace, InvestigationActionTrace)
    assert len(trace.steps) >= 3
    assert trace.iterations_used <= orchestrator.MAX_ITERATIONS
    assert trace.final_decision == "RESOLVE"
    assert trace.requires_human is False

    # 2. Hostile Malicious Planner calling unauthorized tools
    hostile_orchestrator = AgenticInvestigationOrchestrator(batch, provider=HostileMaliciousPlanner())
    hostile_trace = hostile_orchestrator.run_investigation(exc)

    # Invariant: Unauthorized tool rejected immediately, degraded to human review
    assert hostile_trace.terminated_reason == "UNAUTHORIZED_TOOL_REJECTED"
    assert hostile_trace.final_decision == "ESCALATE"
    assert hostile_trace.requires_human is True


def test_agentic_orchestrator_missing_evidence_safe_failure():
    # Payment exists, but settlement statement and fee records are MISSING
    order = Order(order_id="ord_missing", amount=20000.0, status=OrderStatus.PAID, customer_id="c_m", created_at="2026-08-20T10:00:00")
    payment = Payment(payment_id="pay_missing", order_id="ord_missing", amount=20000.0, fee=0.0, tax=0.0, net_amount=20000.0, status=PaymentStatus.CAPTURED, method="card", settlement_id=None, account_number="XXXX-XXXX-9921", created_at="2026-08-20T10:00:00")

    batch = SyntheticBatch(batch_id="b_missing", orders=[order], payments=[payment], settlements=[], refunds=[])
    exc = ExceptionItem(
        exception_id="EXC_M_01", record_id="pay_missing", payment_id="pay_missing", order_id="ord_missing",
        expected_amount=19528.0, actual_amount=0.0, discrepancy_amount=19528.0, category=ExceptionCategory.MISSING_SETTLEMENT_RECORD
    )

    orchestrator = AgenticInvestigationOrchestrator(batch)
    trace = orchestrator.run_investigation(exc)

    assert trace.final_decision == "ESCALATE"
    assert trace.requires_human is True
    assert trace.confidence <= 0.99
