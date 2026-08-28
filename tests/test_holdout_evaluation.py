import pytest
from backend.core.holdout_generator import IndependentHoldoutGenerator
from backend.core.holdout_evaluator import HoldoutEvaluator
from backend.agent.decision_layer import AgentDecisionLayer, AgentDecisionOutput
from backend.core.models import ExceptionItem, ExceptionCategory, Order, OrderStatus, Payment, PaymentStatus, Settlement, SettlementStatus, SyntheticBatch


def test_holdout_generator_partitions():
    gen = IndependentHoldoutGenerator(seed=123)
    batch, truth = gen.generate_holdout_10k(
        clean_count=650,
        known_anomalies_count=150,
        edge_cases_count=100,
        novel_combos_count=100
    )

    assert len(batch.payments) == 1000
    assert len(truth.truth_records) == 1000
    
    clean_items = [t for t in truth.truth_records.values() if t["expected_classification"] == "CLEAN_MATCH"]
    assert len(clean_items) >= 650


def test_agent_decision_layer_structure():
    order = Order(order_id="ord_test_01", amount=10000.0, status=OrderStatus.PAID, customer_id="c1", created_at="2026-08-20T10:00:00")
    payment = Payment(payment_id="pay_test_01", order_id="ord_test_01", amount=10000.0, fee=300.0, tax=54.0, net_amount=9646.0, status=PaymentStatus.CAPTURED, method="card", settlement_id="setl_test_01", created_at="2026-08-20T10:00:00")
    settlement = Settlement(settlement_id="setl_test_01", utr="UTR_01", gross_amount=10000.0, total_fee=300.0, total_tax=54.0, net_payout=9646.0, settlement_date="2026-08-21T10:00:00", account_number="XXXX-XXXX-9921")

    batch = SyntheticBatch(batch_id="b1", orders=[order], payments=[payment], settlements=[settlement], refunds=[])
    agent = AgentDecisionLayer(batch)

    exc = ExceptionItem(
        exception_id="EXC_01", record_id="pay_test_01", payment_id="pay_test_01", order_id="ord_test_01", settlement_id="setl_test_01",
        expected_amount=9764.0, actual_amount=9646.0, discrepancy_amount=118.0, category=ExceptionCategory.MDR_GST_VARIANCE
    )

    decision = agent.evaluate_exception(exc)
    assert isinstance(decision, AgentDecisionOutput)
    assert decision.decision == "RESOLVE"
    assert decision.root_cause == "MDR_GST_VARIANCE"
    assert decision.confidence >= 0.90
    assert decision.requires_human is False
    assert decision.math_proof.gross_amount == 10000.0


def test_zero_false_resolution_invariant():
    gen = IndependentHoldoutGenerator(seed=999)
    batch, truth = gen.generate_holdout_10k(
        clean_count=1000,
        known_anomalies_count=200,
        edge_cases_count=100,
        novel_combos_count=100
    )

    evaluator = HoldoutEvaluator()
    res = evaluator.evaluate_holdout(batch, truth)

    # CRITICAL INVARIANT: 0 false resolutions
    assert res["agent"]["false_resolutions_count"] == 0
    assert res["reconciliation"]["false_reconciliations"] == 0
    assert res["reconciliation"]["precision_pct"] == 100.0
    assert res["reconciliation"]["accuracy_pct"] == 100.0
