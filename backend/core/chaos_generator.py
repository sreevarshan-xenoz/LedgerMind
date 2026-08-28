import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Tuple
from .models import (
    Order, OrderStatus,
    Payment, PaymentStatus,
    Settlement, SettlementStatus,
    Refund, RefundStatus,
    SyntheticBatch
)
from .holdout_generator import HoldoutGroundTruth


class ChaosFinancialGenerator:
    """
    Chaos / Noisy Financial Generator.
    Injects missing fee records, null UTRs, strange non-standard fee tiers (5.73%),
    timezone skew, and ghost records to verify LedgerMind's safe failure modes.
    """

    def __init__(self, seed: int = 7777):
        self.seed = seed
        self.rng = random.Random(seed)
        self.base_date = datetime(2026, 8, 15, 10, 0, 0, tzinfo=timezone.utc)
        self.primary_account = "XXXX-XXXX-9921"

    def generate_chaos_batch(self, count: int = 1000) -> Tuple[SyntheticBatch, HoldoutGroundTruth]:
        orders: List[Order] = []
        payments: List[Payment] = []
        settlements: List[Settlement] = []
        refunds: List[Refund] = []
        truth = HoldoutGroundTruth()

        for idx in range(1, count + 1):
            oid = f"ord_chaos_{idx:05d}"
            pid = f"pay_chaos_{idx:05d}"
            sid = f"setl_chaos_{idx:05d}"

            amt = round(self.rng.choice([1200.0, 3500.0, 9900.0, 18000.0, 45000.0]), 2)
            noise_type = self.rng.choice([
                "CLEAN_TXN",
                "MISSING_FEE_RECORD",
                "NULL_UTR_STATEMENT",
                "UNCONTRACTED_FEE_SURCHARGE",
                "GHOST_ORPHAN_CAPTURE",
                "TIMEZONE_SKEW",
                "UNBACKED_BANK_SHORTFALL"
            ])

            txn_time = self.base_date + timedelta(minutes=idx * 3)

            if noise_type == "CLEAN_TXN":
                fee = round(amt * 0.02, 2)
                tax = round(fee * 0.18, 2)
                net = round(amt - fee - tax, 2)
                orders.append(Order(order_id=oid, amount=amt, status=OrderStatus.PAID, customer_id="c_chaos", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=sid, account_number=self.primary_account, created_at=txn_time.isoformat()))
                settlements.append(Settlement(settlement_id=sid, utr=f"HDFC_UTR_C_{idx:05d}", gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=(txn_time + timedelta(days=1)).isoformat(), account_number=self.primary_account, status=SettlementStatus.SETTLED))
                truth.register(pid, "CLEAN_MATCH", "EXACT_3_WAY_MATCH", 0.0, "Clean transaction in chaos batch")

            elif noise_type == "MISSING_FEE_RECORD":
                # Fee is 0.0 / corrupt in payment record, but settlement netted ₹300
                orders.append(Order(order_id=oid, amount=amt, status=OrderStatus.PAID, customer_id="c_chaos", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=0.0, tax=0.0, net_amount=amt, status=PaymentStatus.CAPTURED, method="card", settlement_id=sid, account_number=self.primary_account, created_at=txn_time.isoformat()))
                settlements.append(Settlement(settlement_id=sid, utr=f"HDFC_UTR_C_{idx:05d}", gross_amount=amt, total_fee=round(amt*0.02, 2), total_tax=round(amt*0.0036, 2), net_payout=round(amt*0.9764, 2), settlement_date=(txn_time + timedelta(days=1)).isoformat(), account_number=self.primary_account, status=SettlementStatus.SETTLED))
                truth.register(pid, "UNRESOLVABLE_ESCALATION", "BANK_UTR_AMOUNT_MISMATCH", round(amt*0.0236, 2), "Missing gateway fee breakdown -> Safe failure to human queue")

            elif noise_type == "NULL_UTR_STATEMENT":
                # Settlement statement is missing or settlement_id points to nothing
                fee = round(amt * 0.02, 2)
                tax = round(fee * 0.18, 2)
                orders.append(Order(order_id=oid, amount=amt, status=OrderStatus.PAID, customer_id="c_chaos", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=amt-fee-tax, status=PaymentStatus.CAPTURED, method="card", settlement_id=None, account_number=self.primary_account, created_at=txn_time.isoformat()))
                truth.register(pid, "UNRESOLVABLE_ESCALATION", "MISSING_SETTLEMENT_RECORD", amt-fee-tax, "Null UTR reference -> Route to human queue")

            elif noise_type == "UNCONTRACTED_FEE_SURCHARGE":
                # Applied fee is 5.73% (an arbitrary non-standard tier)
                fee = round(amt * 0.0573, 2)
                tax = round(fee * 0.18, 2)
                net = round(amt - fee - tax, 2)
                orders.append(Order(order_id=oid, amount=amt, status=OrderStatus.PAID, customer_id="c_chaos", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=sid, account_number=self.primary_account, created_at=txn_time.isoformat()))
                settlements.append(Settlement(settlement_id=sid, utr=f"HDFC_UTR_C_{idx:05d}", gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=(txn_time + timedelta(days=1)).isoformat(), account_number=self.primary_account, status=SettlementStatus.SETTLED))
                truth.register(pid, "RESOLVABLE_EXCEPTION", "MDR_GST_VARIANCE", round(fee - amt*0.02, 2), "Unusual MDR surcharge of 5.73%")

            elif noise_type == "GHOST_ORPHAN_CAPTURE":
                payments.append(Payment(payment_id=pid, order_id=f"ord_ghost_{idx:05d}", amount=amt, fee=50.0, tax=9.0, net_amount=amt-59.0, status=PaymentStatus.CAPTURED, method="upi", settlement_id=None, account_number=self.primary_account, created_at=txn_time.isoformat()))
                truth.register(pid, "UNRESOLVABLE_ESCALATION", "ORPHAN_PAYMENT", amt, "Ghost payment authorization with no order in ERP")

            elif noise_type == "TIMEZONE_SKEW":
                # Settlement timestamp is 3 days earlier than payment due to timezone/clock skew
                fee = round(amt * 0.02, 2)
                tax = round(fee * 0.18, 2)
                net = round(amt - fee - tax, 2)
                skewed_setl_time = (txn_time - timedelta(days=2)).isoformat()

                orders.append(Order(order_id=oid, amount=amt, status=OrderStatus.PAID, customer_id="c_chaos", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=sid, account_number=self.primary_account, created_at=txn_time.isoformat()))
                settlements.append(Settlement(settlement_id=sid, utr=f"HDFC_UTR_C_{idx:05d}", gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=skewed_setl_time, account_number=self.primary_account, status=SettlementStatus.SETTLED))
                truth.register(pid, "CLEAN_MATCH", "EXACT_3_WAY_MATCH", 0.0, "Reconciled with clock skew tolerance")

            else:  # UNBACKED_BANK_SHORTFALL
                fee = round(amt * 0.02, 2)
                tax = round(fee * 0.18, 2)
                net = round(amt - fee - tax, 2)
                shortfall = 770.0
                orders.append(Order(order_id=oid, amount=amt, status=OrderStatus.PAID, customer_id="c_chaos", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=sid, account_number=self.primary_account, created_at=txn_time.isoformat()))
                settlements.append(Settlement(settlement_id=sid, utr=f"HDFC_UTR_C_{idx:05d}", gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net-shortfall, settlement_date=(txn_time + timedelta(days=1)).isoformat(), account_number=self.primary_account, status=SettlementStatus.SETTLED))
                truth.register(pid, "UNRESOLVABLE_ESCALATION", "BANK_UTR_AMOUNT_MISMATCH", shortfall, "Bank UTR shortfall without supporting fee adjustment -> Safe failure")

        batch = SyntheticBatch(
            batch_id=f"chaos_batch_{count}",
            orders=orders,
            payments=payments,
            settlements=settlements,
            refunds=refunds
        )

        return batch, truth
