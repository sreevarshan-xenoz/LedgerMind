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


class HoldoutGroundTruth:
    """Isolated ground-truth registry for evaluation against unseen data."""
    def __init__(self):
        self.truth_records: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        payment_id: str,
        expected_classification: str,  # "CLEAN_MATCH", "RESOLVABLE_EXCEPTION", "UNRESOLVABLE_ESCALATION"
        root_cause: str,
        variance_amount: float = 0.0,
        notes: str = ""
    ):
        self.truth_records[payment_id] = {
            "payment_id": payment_id,
            "expected_classification": expected_classification,
            "root_cause": root_cause,
            "variance_amount": round(variance_amount, 2),
            "notes": notes
        }


class IndependentHoldoutGenerator:
    """
    Independent 10,000-record dataset generator.
    Generates EXACT requested payment record count across 4 isolated partitions.
    Decoupled from reconciler rules.
    """

    def __init__(self, seed: int = 4242):
        self.seed = seed
        self.rng = random.Random(seed)
        self.payment_methods = ["card", "upi", "netbanking", "wallet"]
        self.base_date = datetime(2026, 8, 1, 9, 0, 0, tzinfo=timezone.utc)
        self.primary_account = "XXXX-XXXX-9921"

    def generate_holdout_10k(
        self,
        clean_count: int = 6500,
        known_anomalies_count: int = 1500,
        edge_cases_count: int = 1000,
        novel_combos_count: int = 1000
    ) -> Tuple[SyntheticBatch, HoldoutGroundTruth]:
        orders: List[Order] = []
        payments: List[Payment] = []
        settlements: List[Settlement] = []
        refunds: List[Refund] = []
        truth = HoldoutGroundTruth()

        global_idx = 1

        # -------------------------------------------------------------------
        # PARTITION 1: Clean 3-Way Reconciliations (Exact Count)
        # -------------------------------------------------------------------
        for _ in range(clean_count):
            oid = f"ord_h_clean_{global_idx:06d}"
            pid = f"pay_h_clean_{global_idx:06d}"
            sid = f"setl_h_clean_{global_idx:06d}"
            utr = f"HDFC_UTR_HC_{global_idx:06d}"

            amt = round(self.rng.choice([499.0, 999.0, 1499.0, 2500.0, 4999.0, 12000.0, 25000.0]), 2)
            method = self.rng.choice(self.payment_methods)
            
            rate = 0.0 if method == "upi" else (0.02 if method == "card" else (0.018 if method == "netbanking" else 0.019))
            fee = round(amt * rate, 2)
            tax = round(fee * 0.18, 2)
            net = round(amt - fee - tax, 2)

            txn_time = self.base_date + timedelta(minutes=global_idx * 2)
            setl_time = txn_time + timedelta(days=1)

            orders.append(Order(
                order_id=oid, amount=amt, currency="INR", status=OrderStatus.PAID,
                customer_id=f"cust_h_{global_idx:06d}", created_at=txn_time.isoformat()
            ))

            payments.append(Payment(
                payment_id=pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=net,
                status=PaymentStatus.CAPTURED, method=method, settlement_id=sid,
                account_number=self.primary_account, created_at=txn_time.isoformat()
            ))

            settlements.append(Settlement(
                settlement_id=sid, utr=utr, gross_amount=amt, total_fee=fee, total_tax=tax,
                net_payout=net, settlement_date=setl_time.isoformat(),
                account_number=self.primary_account, status=SettlementStatus.SETTLED
            ))

            truth.register(pid, "CLEAN_MATCH", "EXACT_3_WAY_MATCH", 0.0, "Standard clean transaction")
            global_idx += 1

        # -------------------------------------------------------------------
        # PARTITION 2: Known Anomalies (Exact Count)
        # -------------------------------------------------------------------
        anomaly_types = ["FEE_VARIANCE", "PRE_REFUND", "TIMING_LAG", "FOREIGN_ACCOUNT", "DOUBLE_CAPTURE_PAIR"]
        
        i = 0
        while i < known_anomalies_count:
            oid = f"ord_h_anom_{global_idx:06d}"
            pid = f"pay_h_anom_{global_idx:06d}"
            sid = f"setl_h_anom_{global_idx:06d}"
            utr = f"HDFC_UTR_HA_{global_idx:06d}"

            amt = round(self.rng.choice([1500.0, 3000.0, 7500.0, 15000.0, 50000.0]), 2)
            anom_choice = self.rng.choice(anomaly_types)

            txn_time = self.base_date + timedelta(minutes=global_idx * 2)
            setl_time = txn_time + timedelta(days=1)

            if anom_choice == "FEE_VARIANCE":
                std_fee = round(amt * 0.02, 2)
                std_tax = round(std_fee * 0.18, 2)
                act_fee = round(amt * 0.03, 2)
                act_tax = round(act_fee * 0.18, 2)
                net = round(amt - act_fee - act_tax, 2)
                var = round((act_fee + act_tax) - (std_fee + std_tax), 2)

                orders.append(Order(order_id=oid, amount=amt, currency="INR", status=OrderStatus.PAID, customer_id="c_anom", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=act_fee, tax=act_tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=sid, account_number=self.primary_account, created_at=txn_time.isoformat()))
                settlements.append(Settlement(settlement_id=sid, utr=utr, gross_amount=amt, total_fee=act_fee, total_tax=act_tax, net_payout=net, settlement_date=setl_time.isoformat(), account_number=self.primary_account, status=SettlementStatus.SETTLED))
                truth.register(pid, "RESOLVABLE_EXCEPTION", "MDR_GST_VARIANCE", var, "Card tier surcharge 3% MDR")
                i += 1
                global_idx += 1

            elif anom_choice == "PRE_REFUND":
                fee = round(amt * 0.02, 2)
                tax = round(fee * 0.18, 2)
                rfnd_amt = round(amt * 0.4, 2)
                net = round(amt - fee - tax - rfnd_amt, 2)

                orders.append(Order(order_id=oid, amount=amt, currency="INR", status=OrderStatus.REFUNDED, customer_id="c_anom", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.REFUNDED, method="card", settlement_id=sid, account_number=self.primary_account, created_at=txn_time.isoformat()))
                settlements.append(Settlement(settlement_id=sid, utr=utr, gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=setl_time.isoformat(), account_number=self.primary_account, status=SettlementStatus.SETTLED))
                refunds.append(Refund(refund_id=f"rfnd_h_{global_idx:06d}", payment_id=pid, amount=rfnd_amt, created_at=(txn_time + timedelta(hours=2)).isoformat()))
                truth.register(pid, "RESOLVABLE_EXCEPTION", "PARTIAL_REFUND_NETTED", rfnd_amt, "Pre-settlement refund netted")
                i += 1
                global_idx += 1

            elif anom_choice == "TIMING_LAG":
                fee = round(amt * 0.02, 2)
                tax = round(fee * 0.18, 2)
                net = round(amt - fee - tax, 2)
                late_setl_time = txn_time + timedelta(days=4)

                orders.append(Order(order_id=oid, amount=amt, currency="INR", status=OrderStatus.PAID, customer_id="c_anom", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=sid, account_number=self.primary_account, created_at=txn_time.isoformat()))
                settlements.append(Settlement(settlement_id=sid, utr=utr, gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=late_setl_time.isoformat(), account_number=self.primary_account, status=SettlementStatus.SETTLED))
                truth.register(pid, "RESOLVABLE_EXCEPTION", "TIMING_LAG", 0.0, "T+4 bank clearing lag")
                i += 1
                global_idx += 1

            elif anom_choice == "FOREIGN_ACCOUNT":
                fee = round(amt * 0.02, 2)
                tax = round(fee * 0.18, 2)
                net = round(amt - fee - tax, 2)
                foreign_acct = "XXXX-XXXX-8833"

                orders.append(Order(order_id=oid, amount=amt, currency="INR", status=OrderStatus.PAID, customer_id="c_anom", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=sid, account_number=self.primary_account, created_at=txn_time.isoformat()))
                settlements.append(Settlement(settlement_id=sid, utr=utr, gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=setl_time.isoformat(), account_number=foreign_acct, status=SettlementStatus.SETTLED))
                truth.register(pid, "UNRESOLVABLE_ESCALATION", "ACCOUNT_MISMATCH", net, "Remitted to foreign account 8833")
                i += 1
                global_idx += 1

            else:  # DOUBLE_CAPTURE_PAIR (Consumes 2 records to maintain strict count)
                if i + 2 > known_anomalies_count:
                    continue  # skip pair if not enough budget
                fee = round(amt * 0.02, 2)
                tax = round(fee * 0.18, 2)
                net = round(amt - fee - tax, 2)

                orders.append(Order(order_id=oid, amount=amt, currency="INR", status=OrderStatus.PAID, customer_id="c_anom", created_at=txn_time.isoformat()))
                # Record 1: Primary clean payment
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=sid, account_number=self.primary_account, created_at=txn_time.isoformat()))
                settlements.append(Settlement(settlement_id=sid, utr=utr, gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=setl_time.isoformat(), account_number=self.primary_account, status=SettlementStatus.SETTLED))
                truth.register(pid, "CLEAN_MATCH", "EXACT_3_WAY_MATCH", 0.0, "Primary payment on order")

                # Record 2: Secondary duplicate capture
                dup_pid = f"pay_h_anom_dup_{global_idx:06d}"
                payments.append(Payment(payment_id=dup_pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=None, account_number=self.primary_account, created_at=(txn_time + timedelta(seconds=15)).isoformat()))
                truth.register(dup_pid, "UNRESOLVABLE_ESCALATION", "DUPLICATE_AUTH_CAPTURE", amt, "Secondary double capture authorization")
                
                i += 2
                global_idx += 1

        # -------------------------------------------------------------------
        # PARTITION 3: Ambiguous / Edge Cases (Exact Count)
        # -------------------------------------------------------------------
        for _ in range(edge_cases_count):
            oid = f"ord_h_edge_{global_idx:06d}"
            pid = f"pay_h_edge_{global_idx:06d}"
            amt = round(self.rng.choice([10000.0, 20000.0, 50000.0]), 2)
            txn_time = self.base_date + timedelta(minutes=global_idx * 2)

            edge_type = self.rng.choice(["SPLIT_UTR", "POST_REFUND", "UNEXPLAINED_SHORTFALL"])

            if edge_type == "SPLIT_UTR":
                fee = round(amt * 0.02, 2)
                tax = round(fee * 0.18, 2)
                net = round(amt - fee - tax, 2)
                chunk_1 = round(net * 0.6, 2)
                chunk_2 = round(net - chunk_1, 2)

                sid1 = f"setl_h_split1_{global_idx:06d}"
                sid2 = f"setl_h_split2_{global_idx:06d}"

                orders.append(Order(order_id=oid, amount=amt, currency="INR", status=OrderStatus.PAID, customer_id="c_edge", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_ids=[sid1, sid2], account_number=self.primary_account, created_at=txn_time.isoformat()))

                settlements.append(Settlement(settlement_id=sid1, utr=f"HDFC_UTR_SP1_{global_idx:06d}", gross_amount=round(amt*0.6, 2), total_fee=round(fee*0.6, 2), total_tax=round(tax*0.6, 2), net_payout=chunk_1, settlement_date=(txn_time + timedelta(days=1)).isoformat(), payment_ids=[pid], account_number=self.primary_account, status=SettlementStatus.SETTLED))
                settlements.append(Settlement(settlement_id=sid2, utr=f"HDFC_UTR_SP2_{global_idx:06d}", gross_amount=round(amt*0.4, 2), total_fee=round(fee*0.4, 2), total_tax=round(tax*0.4, 2), net_payout=chunk_2, settlement_date=(txn_time + timedelta(days=2)).isoformat(), payment_ids=[pid], account_number=self.primary_account, status=SettlementStatus.SETTLED))

                truth.register(pid, "RESOLVABLE_EXCEPTION", "SPLIT_MULTI_UTR_SETTLED", 0.0, "Split across 2 UTRs")

            elif edge_type == "POST_REFUND":
                fee = round(amt * 0.02, 2)
                tax = round(fee * 0.18, 2)
                net = round(amt - fee - tax, 2)
                rfnd_amt = round(amt * 0.5, 2)

                sid = f"setl_h_edge_{global_idx:06d}"
                setl_time = txn_time + timedelta(days=1)
                rfnd_time = setl_time + timedelta(days=2)

                orders.append(Order(order_id=oid, amount=amt, currency="INR", status=OrderStatus.REFUNDED, customer_id="c_edge", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.REFUNDED, method="card", settlement_id=sid, account_number=self.primary_account, created_at=txn_time.isoformat()))
                settlements.append(Settlement(settlement_id=sid, utr=f"HDFC_UTR_HE_{global_idx:06d}", gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=setl_time.isoformat(), account_number=self.primary_account, status=SettlementStatus.SETTLED))
                refunds.append(Refund(refund_id=f"rfnd_h_post_{global_idx:06d}", payment_id=pid, amount=rfnd_amt, created_at=rfnd_time.isoformat()))

                truth.register(pid, "RESOLVABLE_EXCEPTION", "POST_SETTLEMENT_REFUND_DEFERRED", rfnd_amt, "Post-settlement refund deferred")

            else:  # UNEXPLAINED_SHORTFALL
                fee = round(amt * 0.02, 2)
                tax = round(fee * 0.18, 2)
                net = round(amt - fee - tax, 2)
                shortfall = round(self.rng.choice([250.0, 500.0, 1000.0]), 2)
                bad_net = round(net - shortfall, 2)

                sid = f"setl_h_edge_{global_idx:06d}"
                orders.append(Order(order_id=oid, amount=amt, currency="INR", status=OrderStatus.PAID, customer_id="c_edge", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=sid, account_number=self.primary_account, created_at=txn_time.isoformat()))
                settlements.append(Settlement(settlement_id=sid, utr=f"HDFC_UTR_HE_{global_idx:06d}", gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=bad_net, settlement_date=(txn_time + timedelta(days=1)).isoformat(), account_number=self.primary_account, status=SettlementStatus.SETTLED))

                truth.register(pid, "UNRESOLVABLE_ESCALATION", "BANK_UTR_AMOUNT_MISMATCH", shortfall, f"Bank UTR shortfall of ₹{shortfall:,.2f}")

            global_idx += 1

        # -------------------------------------------------------------------
        # PARTITION 4: Novel Combinations (Exact Count)
        # -------------------------------------------------------------------
        for _ in range(novel_combos_count):
            oid = f"ord_h_novel_{global_idx:06d}"
            pid = f"pay_h_novel_{global_idx:06d}"
            sid = f"setl_h_novel_{global_idx:06d}"
            amt = round(self.rng.choice([8000.0, 16000.0, 32000.0]), 2)
            txn_time = self.base_date + timedelta(minutes=global_idx * 2)

            combo_choice = self.rng.choice(["ORPHAN_ABANDONED", "DELAYED_FEE_SURCHARGE", "MISSING_SETTLEMENT"])

            if combo_choice == "ORPHAN_ABANDONED":
                payments.append(Payment(payment_id=pid, order_id="ord_ghost_99999", amount=amt, fee=100.0, tax=18.0, net_amount=amt-118.0, status=PaymentStatus.CAPTURED, method="card", settlement_id=None, account_number=self.primary_account, created_at=txn_time.isoformat()))
                truth.register(pid, "UNRESOLVABLE_ESCALATION", "ORPHAN_PAYMENT", amt, "Orphan payment - no ERP order")

            elif combo_choice == "DELAYED_FEE_SURCHARGE":
                fee = round(amt * 0.035, 2)
                tax = round(fee * 0.18, 2)
                net = round(amt - fee - tax, 2)
                late_setl = txn_time + timedelta(days=3)

                orders.append(Order(order_id=oid, amount=amt, currency="INR", status=OrderStatus.PAID, customer_id="c_combo", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=sid, account_number=self.primary_account, created_at=txn_time.isoformat()))
                settlements.append(Settlement(settlement_id=sid, utr=f"HDFC_UTR_HN_{global_idx:06d}", gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=late_setl.isoformat(), account_number=self.primary_account, status=SettlementStatus.SETTLED))
                truth.register(pid, "RESOLVABLE_EXCEPTION", "MDR_GST_VARIANCE", round(fee - amt*0.02, 2), "MDR surcharge 3.5% + T+3 lag")

            else:  # MISSING_SETTLEMENT
                orders.append(Order(order_id=oid, amount=amt, currency="INR", status=OrderStatus.PAID, customer_id="c_combo", created_at=txn_time.isoformat()))
                payments.append(Payment(payment_id=pid, order_id=oid, amount=amt, fee=50.0, tax=9.0, net_amount=amt-59.0, status=PaymentStatus.CAPTURED, method="upi", settlement_id=None, account_number=self.primary_account, created_at=txn_time.isoformat()))
                truth.register(pid, "UNRESOLVABLE_ESCALATION", "MISSING_SETTLEMENT_RECORD", amt-59.0, "Unsettled gateway payment")

            global_idx += 1

        batch = SyntheticBatch(
            batch_id="independent_holdout_10k",
            orders=orders,
            payments=payments,
            settlements=settlements,
            refunds=refunds
        )

        return batch, truth
