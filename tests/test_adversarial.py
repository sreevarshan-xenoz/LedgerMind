import pytest
from datetime import datetime, timedelta
from backend.core.models import (
    Order, OrderStatus,
    Payment, PaymentStatus,
    Settlement, SettlementStatus,
    Refund, RefundStatus,
    SyntheticBatch, GroundTruthMetadata,
    ExceptionCategory
)
from backend.core.adversarial_generator import AdversarialFinancialGenerator
from backend.core.reconciler import DeterministicReconciliationEngine
from backend.core.benchmarking import BenchmarkEvaluator


def test_attack_duplicate_payment_capture():
    """Attack 1: Same order gets two payments. Engine must match Pay A, flag Pay B as duplicate capture."""
    engine = DeterministicReconciliationEngine()
    
    order = Order(order_id="ord_dup_1", amount=5000.0, status=OrderStatus.PAID, customer_id="c1", created_at="2026-08-20T10:00:00")
    pay_a = Payment(payment_id="pay_a", order_id="ord_dup_1", amount=5000.0, fee=100.0, tax=18.0, net_amount=4882.0, status=PaymentStatus.CAPTURED, settlement_id="setl_1", created_at="2026-08-20T10:00:00")
    pay_b = Payment(payment_id="pay_b", order_id="ord_dup_1", amount=5000.0, fee=100.0, tax=18.0, net_amount=4882.0, status=PaymentStatus.CAPTURED, settlement_id=None, created_at="2026-08-20T10:01:00")
    setl = Settlement(settlement_id="setl_1", utr="UTR1", gross_amount=5000.0, total_fee=100.0, total_tax=18.0, net_payout=4882.0, settlement_date="2026-08-21T10:00:00", account_number="XXXX-XXXX-9921")

    batch = SyntheticBatch(batch_id="test_dup", orders=[order], payments=[pay_a, pay_b], settlements=[setl], refunds=[])
    matched, exceptions, meta = engine.reconcile(batch)

    assert len(matched) == 1
    assert matched[0].payment_id == "pay_a"
    
    dup_excs = [e for e in exceptions if e.category == ExceptionCategory.DUPLICATE_AUTH_CAPTURE]
    assert len(dup_excs) == 1
    assert dup_excs[0].payment_id == "pay_b"
    assert dup_excs[0].is_resolved is False


def test_attack_post_settlement_refund_timing():
    """Attack 2: Refund occurs AFTER settlement. Engine must know initial settlement was gross-settled, not a mismatch."""
    engine = DeterministicReconciliationEngine()

    p_time = "2026-08-20T10:00:00"
    s_time = "2026-08-21T10:00:00"
    r_time = "2026-08-23T10:00:00"  # 2 days after settlement

    order = Order(order_id="ord_post_1", amount=10000.0, status=OrderStatus.REFUNDED, customer_id="c2", created_at=p_time)
    pay = Payment(payment_id="pay_post_1", order_id="ord_post_1", amount=10000.0, fee=200.0, tax=36.0, net_amount=9764.0, status=PaymentStatus.REFUNDED, settlement_id="setl_post", created_at=p_time)
    setl = Settlement(settlement_id="setl_post", utr="UTR2", gross_amount=10000.0, total_fee=200.0, total_tax=36.0, net_payout=9764.0, settlement_date=s_time, account_number="XXXX-XXXX-9921")
    rfnd = Refund(refund_id="rfnd_1", payment_id="pay_post_1", amount=2000.0, created_at=r_time)

    batch = SyntheticBatch(batch_id="test_post", orders=[order], payments=[pay], settlements=[setl], refunds=[rfnd])
    matched, exceptions, meta = engine.reconcile(batch)

    assert len(matched) == 1
    assert matched[0].match_type == "3_WAY_POST_REFUND"
    
    post_excs = [e for e in exceptions if e.category == ExceptionCategory.POST_SETTLEMENT_REFUND_DEFERRED]
    assert len(post_excs) == 1
    assert post_excs[0].is_resolved is True


def test_attack_amount_collision_disambiguation():
    """Attack 3: Order A ₹5k & Order B ₹5k. Engine must NEVER match Order B by coincidence."""
    engine = DeterministicReconciliationEngine()

    t_str = "2026-08-20T10:00:00"
    ord_a = Order(order_id="ord_A", amount=5000.0, status=OrderStatus.PAID, customer_id="cA", created_at=t_str)
    ord_b = Order(order_id="ord_B", amount=5000.0, status=OrderStatus.PAID, customer_id="cB", created_at=t_str)

    pay_a = Payment(payment_id="pay_A", order_id="ord_A", amount=5000.0, fee=100.0, tax=18.0, net_amount=4882.0, status=PaymentStatus.CAPTURED, settlement_id="setl_A", created_at=t_str)
    pay_b = Payment(payment_id="pay_B", order_id="ord_B", amount=5000.0, fee=100.0, tax=18.0, net_amount=4882.0, status=PaymentStatus.CAPTURED, settlement_id=None, created_at=t_str)

    setl_a = Settlement(settlement_id="setl_A", utr="UTR_A", gross_amount=5000.0, total_fee=100.0, total_tax=18.0, net_payout=4882.0, settlement_date="2026-08-21T10:00:00", account_number="XXXX-XXXX-9921")

    batch = SyntheticBatch(batch_id="test_coll", orders=[ord_a, ord_b], payments=[pay_a, pay_b], settlements=[setl_a], refunds=[])
    matched, exceptions, meta = engine.reconcile(batch)

    # Only pay_a should match
    assert len(matched) == 1
    assert matched[0].payment_id == "pay_A"

    # pay_b must be flagged as unsettled exception (never falsely matched!)
    unres = [e for e in exceptions if e.payment_id == "pay_B"]
    assert len(unres) == 1
    assert unres[0].category == ExceptionCategory.MISSING_SETTLEMENT_RECORD
    assert unres[0].is_resolved is False


def test_attack_split_multi_utr_settlement():
    """Attack 4: Single payment of ₹50,000 remitted in 2 settlement chunks (₹30,000 + ₹19,000 + ₹1,000 fee)."""
    engine = DeterministicReconciliationEngine()

    t_str = "2026-08-20T10:00:00"
    ord_split = Order(order_id="ord_split", amount=50000.0, status=OrderStatus.PAID, customer_id="c_sp", created_at=t_str)
    pay_split = Payment(payment_id="pay_split", order_id="ord_split", amount=50000.0, fee=847.46, tax=152.54, net_amount=49000.0, status=PaymentStatus.CAPTURED, settlement_ids=["s1", "s2"], created_at=t_str)

    setl_1 = Settlement(settlement_id="s1", utr="UTR_CHUNK_1", gross_amount=30500.0, total_fee=500.0, total_tax=0.0, net_payout=30000.0, settlement_date="2026-08-21T10:00:00", account_number="XXXX-XXXX-9921", payment_ids=["pay_split"])
    setl_2 = Settlement(settlement_id="s2", utr="UTR_CHUNK_2", gross_amount=19500.0, total_fee=500.0, total_tax=0.0, net_payout=19000.0, settlement_date="2026-08-21T10:00:00", account_number="XXXX-XXXX-9921", payment_ids=["pay_split"])

    batch = SyntheticBatch(batch_id="test_split", orders=[ord_split], payments=[pay_split], settlements=[setl_1, setl_2], refunds=[])
    matched, exceptions, meta = engine.reconcile(batch)

    assert len(matched) == 1
    assert matched[0].match_type == "3_WAY_SPLIT_UTR"
    assert matched[0].net_settled == 49000.0
    assert len(matched[0].settlement_utrs) == 2


def test_attack_foreign_account_mismatch():
    """Attack 5: Settlement UTR was credited to a foreign bank account."""
    engine = DeterministicReconciliationEngine()

    t_str = "2026-08-20T10:00:00"
    ord_acct = Order(order_id="ord_acct", amount=7500.0, status=OrderStatus.PAID, customer_id="c_acct", created_at=t_str)
    pay_acct = Payment(payment_id="pay_acct", order_id="ord_acct", amount=7500.0, fee=150.0, tax=27.0, net_amount=7323.0, status=PaymentStatus.CAPTURED, settlement_id="setl_wrong", created_at=t_str)
    setl_wrong = Settlement(settlement_id="setl_wrong", utr="UTR_WRONG", gross_amount=7500.0, total_fee=150.0, total_tax=27.0, net_payout=7323.0, settlement_date="2026-08-21T10:00:00", account_number="XXXX-XXXX-4410")

    batch = SyntheticBatch(batch_id="test_wrong_acct", orders=[ord_acct], payments=[pay_acct], settlements=[setl_wrong], refunds=[])
    matched, exceptions, meta = engine.reconcile(batch)

    assert len(matched) == 0  # Must NOT reconcile!
    assert len(exceptions) == 1
    assert exceptions[0].category == ExceptionCategory.ACCOUNT_MISMATCH
    assert exceptions[0].is_resolved is False


def test_adversarial_suite_benchmark():
    """Run full adversarial generator suite against BenchmarkEvaluator."""
    gen = AdversarialFinancialGenerator(seed=2026)
    adv_batch = gen.generate_adversarial_batch(batch_id="adv_eval", num_records=200)

    evaluator = BenchmarkEvaluator()
    results = evaluator.run_benchmark(adv_batch)

    ev = results["evaluation"]
    # Zero False Reconciliations (No financial hallucinations!)
    assert ev["false_reconciliations"] == 0
    assert ev["accuracy_pct"] >= 98.0
    assert ev["exception_recall_pct"] == 100.0
    assert ev["throughput_records_per_sec"] > 1000.0
