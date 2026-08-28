import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from .models import (
    Order, OrderStatus,
    Payment, PaymentStatus,
    Settlement, SettlementStatus,
    Refund, RefundStatus,
    SyntheticBatch, GroundTruthMetadata,
    ExceptionCategory
)


class AdversarialFinancialGenerator:
    """
    Generates challenging, adversarial, out-of-order financial datasets
    designed to rigorously test and attempt to break reconciliation engines.
    """

    def __init__(self, seed: int = 1337):
        random.seed(seed)
        self.standard_account = "XXXX-XXXX-9921"
        self.foreign_account = "XXXX-XXXX-4410"

    def generate_adversarial_batch(
        self,
        batch_id: str = "adv_batch_001",
        num_records: int = 100,
        start_date: Optional[datetime] = None
    ) -> SyntheticBatch:
        if start_date is None:
            start_date = datetime(2026, 8, 20, 10, 0, 0)

        orders: List[Order] = []
        payments: List[Payment] = []
        settlements: List[Settlement] = []
        refunds: List[Refund] = []
        ground_truth: Dict[str, GroundTruthMetadata] = {}

        # 1. Clean Control Records (50% of batch)
        clean_count = int(num_records * 0.50)
        for i in range(clean_count):
            idx = i + 1
            ord_id = f"ord_clean_{idx:04d}"
            pay_id = f"pay_clean_{idx:04d}"
            setl_id = f"setl_clean_{idx:04d}"
            amt = float(random.choice([1000, 2500, 4800, 7500, 12000]))
            fee = round(amt * 0.02, 2)
            tax = round(fee * 0.18, 2)
            net = round(amt - fee - tax, 2)
            t_str = (start_date + timedelta(minutes=idx * 15)).isoformat()
            s_date = (start_date + timedelta(days=1, minutes=idx * 15)).isoformat()

            orders.append(Order(order_id=ord_id, amount=amt, status=OrderStatus.PAID, customer_id=f"cust_{idx}", created_at=t_str))
            payments.append(Payment(payment_id=pay_id, order_id=ord_id, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=setl_id, account_number=self.standard_account, created_at=t_str))
            settlements.append(Settlement(settlement_id=setl_id, utr=f"HDFCUTR{random.randint(1000000, 9999999)}", gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=s_date, account_number=self.standard_account, status=SettlementStatus.SETTLED))

            ground_truth[pay_id] = GroundTruthMetadata(
                is_anomaly=False,
                expected_match_status="MATCHED",
                expected_discrepancy=0.0,
                explanation="Clean 3-way control record."
            )

        remaining = num_records - clean_count
        attacks_per_type = max(1, remaining // 6)

        # 2. Attack Vector 1: Duplicate Payment Captures (Order ₹5,000 -> Pay A ₹5,000, Pay B ₹5,000)
        for i in range(attacks_per_type):
            ord_id = f"ord_dup_{i+1:03d}"
            pay_a = f"pay_dup_{i+1:03d}_A"
            pay_b = f"pay_dup_{i+1:03d}_B"
            setl_id = f"setl_dup_{i+1:03d}"
            amt = 5000.0
            fee, tax, net = 100.0, 18.0, 4882.0
            t_str = start_date.isoformat()

            orders.append(Order(order_id=ord_id, amount=amt, status=OrderStatus.PAID, customer_id=f"cust_dup_{i}", created_at=t_str))
            payments.append(Payment(payment_id=pay_a, order_id=ord_id, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=setl_id, account_number=self.standard_account, created_at=t_str))
            payments.append(Payment(payment_id=pay_b, order_id=ord_id, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=None, account_number=self.standard_account, created_at=t_str))
            settlements.append(Settlement(settlement_id=setl_id, utr=f"HDFCUTR{random.randint(1000000, 9999999)}", gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=(start_date + timedelta(days=1)).isoformat(), account_number=self.standard_account))

            ground_truth[pay_a] = GroundTruthMetadata(is_anomaly=False, expected_match_status="MATCHED", explanation="Primary valid payment on order.")
            ground_truth[pay_b] = GroundTruthMetadata(is_anomaly=True, anomaly_type="DUPLICATE_AUTH_CAPTURE", expected_match_status="UNRESOLVED", expected_discrepancy=amt, explanation="Duplicate capture requiring customer refund.")

        # 3. Attack Vector 2: Post-Settlement Refund Timing (Refund AFTER settlement)
        for i in range(attacks_per_type):
            ord_id = f"ord_post_ref_{i+1:03d}"
            pay_id = f"pay_post_ref_{i+1:03d}"
            setl_id = f"setl_post_ref_{i+1:03d}"
            rfnd_id = f"rfnd_post_{i+1:03d}"
            amt = 10000.0
            rfnd_amt = 2000.0
            fee, tax, net = 200.0, 36.0, 9764.0
            
            p_time = start_date
            s_time = start_date + timedelta(days=1)   # Aug 21
            r_time = start_date + timedelta(days=3)   # Aug 23 (After settlement!)

            orders.append(Order(order_id=ord_id, amount=amt, status=OrderStatus.REFUNDED, customer_id=f"cust_post_{i}", created_at=p_time.isoformat()))
            payments.append(Payment(payment_id=pay_id, order_id=ord_id, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.REFUNDED, method="card", settlement_id=setl_id, account_number=self.standard_account, created_at=p_time.isoformat()))
            settlements.append(Settlement(settlement_id=setl_id, utr=f"HDFCUTR{random.randint(1000000, 9999999)}", gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=s_time.isoformat(), account_number=self.standard_account))
            refunds.append(Refund(refund_id=rfnd_id, payment_id=pay_id, amount=rfnd_amt, reason="Post-delivery return", created_at=r_time.isoformat()))

            ground_truth[pay_id] = GroundTruthMetadata(
                is_anomaly=True,
                anomaly_type="POST_SETTLEMENT_REFUND_DEFERRED",
                expected_match_status="AUTO_RESOLVED",
                expected_discrepancy=rfnd_amt,
                explanation="Refund requested post-settlement. Aug 21 settlement was gross net; ₹2000 refund deferred to future debit cycle."
            )

        # 4. Attack Vector 3: Amount Collision Disambiguation (Order A ₹5,000, Order B ₹5,000)
        for i in range(attacks_per_type):
            ord_a = f"ord_coll_A_{i+1:03d}"
            ord_b = f"ord_coll_B_{i+1:03d}"
            pay_a = f"pay_coll_A_{i+1:03d}"
            pay_b = f"pay_coll_B_{i+1:03d}"
            setl_a = f"setl_coll_A_{i+1:03d}"
            amt = 5000.0
            fee, tax, net = 100.0, 18.0, 4882.0
            t_str = start_date.isoformat()

            orders.append(Order(order_id=ord_a, amount=amt, status=OrderStatus.PAID, customer_id=f"cust_cA_{i}", created_at=t_str))
            orders.append(Order(order_id=ord_b, amount=amt, status=OrderStatus.PAID, customer_id=f"cust_cB_{i}", created_at=t_str))

            payments.append(Payment(payment_id=pay_a, order_id=ord_a, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=setl_a, account_number=self.standard_account, created_at=t_str))
            # Payment B captured without settlement reference
            payments.append(Payment(payment_id=pay_b, order_id=ord_b, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=None, account_number=self.standard_account, created_at=t_str))

            settlements.append(Settlement(settlement_id=setl_a, utr=f"HDFCUTR_COLL_{i}", gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=(start_date + timedelta(days=1)).isoformat(), account_number=self.standard_account))

            ground_truth[pay_a] = GroundTruthMetadata(is_anomaly=False, expected_match_status="MATCHED", explanation="Matched with exact foreign keys.")
            ground_truth[pay_b] = GroundTruthMetadata(is_anomaly=True, anomaly_type="MISSING_SETTLEMENT_RECORD", expected_match_status="UNRESOLVED", expected_discrepancy=net, explanation="Identical amount collision: Order B payment is unsettled and must not falsely match Settlement A.")

        # 5. Attack Vector 4: Split Multi-UTR Settlement (1 Payment -> 2 Settlement UTRs)
        for i in range(attacks_per_type):
            ord_id = f"ord_split_{i+1:03d}"
            pay_id = f"pay_split_{i+1:03d}"
            setl_1 = f"setl_split_1_{i+1:03d}"
            setl_2 = f"setl_split_2_{i+1:03d}"
            amt = 50000.0
            fee, tax = 847.46, 152.54  # Total Fee+Tax = ₹1,000.00
            net = 49000.0
            chunk_1_net = 30000.0
            chunk_2_net = 19000.0
            t_str = start_date.isoformat()
            s_str = (start_date + timedelta(days=1)).isoformat()

            orders.append(Order(order_id=ord_id, amount=amt, status=OrderStatus.PAID, customer_id=f"cust_split_{i}", created_at=t_str))
            payments.append(Payment(
                payment_id=pay_id,
                order_id=ord_id,
                amount=amt,
                fee=fee,
                tax=tax,
                net_amount=net,
                status=PaymentStatus.CAPTURED,
                method="card",
                settlement_id=setl_1,
                settlement_ids=[setl_1, setl_2],
                account_number=self.standard_account,
                created_at=t_str
            ))

            settlements.append(Settlement(settlement_id=setl_1, utr=f"UTR_SPLIT_A_{i}", gross_amount=30500.0, total_fee=500.0, total_tax=0.0, net_payout=chunk_1_net, settlement_date=s_str, account_number=self.standard_account, payment_ids=[pay_id]))
            settlements.append(Settlement(settlement_id=setl_2, utr=f"UTR_SPLIT_B_{i}", gross_amount=19500.0, total_fee=500.0, total_tax=0.0, net_payout=chunk_2_net, settlement_date=s_str, account_number=self.standard_account, payment_ids=[pay_id]))

            ground_truth[pay_id] = GroundTruthMetadata(
                is_anomaly=True,
                anomaly_type="SPLIT_MULTI_UTR_SETTLED",
                expected_match_status="AUTO_RESOLVED",
                expected_discrepancy=0.0,
                explanation="Payment remitted across two settlement UTRs (₹30,000 + ₹19,000 + ₹1,000 fee/tax = ₹50,000)."
            )

        # 6. Attack Vector 5: Wrong Bank UTR / Account Number Mismatch
        for i in range(attacks_per_type):
            ord_id = f"ord_acct_err_{i+1:03d}"
            pay_id = f"pay_acct_err_{i+1:03d}"
            setl_id = f"setl_acct_err_{i+1:03d}"
            amt = 7500.0
            fee, tax, net = 150.0, 27.0, 7323.0
            t_str = start_date.isoformat()

            orders.append(Order(order_id=ord_id, amount=amt, status=OrderStatus.PAID, customer_id=f"cust_acct_{i}", created_at=t_str))
            payments.append(Payment(payment_id=pay_id, order_id=ord_id, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=setl_id, account_number=self.standard_account, created_at=t_str))
            # Settlement credited to a foreign bank account!
            settlements.append(Settlement(settlement_id=setl_id, utr=f"UTR_WRONG_ACCT_{i}", gross_amount=amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=(start_date + timedelta(days=1)).isoformat(), account_number=self.foreign_account))

            ground_truth[pay_id] = GroundTruthMetadata(
                is_anomaly=True,
                anomaly_type="ACCOUNT_MISMATCH",
                expected_match_status="UNRESOLVED",
                expected_discrepancy=net,
                explanation="Settlement UTR was remitted to an unrecognized bank account number."
            )

        # 7. Attack Vector 6: Partial Refund Fee Disguise (₹20,000 - ₹7,500 refund - ₹400 fee = ₹12,100)
        for i in range(attacks_per_type):
            ord_id = f"ord_part_disguise_{i+1:03d}"
            pay_id = f"pay_part_disguise_{i+1:03d}"
            setl_id = f"setl_part_disguise_{i+1:03d}"
            rfnd_id = f"rfnd_part_{i+1:03d}"
            amt = 20000.0
            rfnd_amt = 7500.0
            fee, tax = 338.98, 61.02  # Total Fee+Tax = ₹400.00 (2% on 20k)
            net = 12100.0             # 20,000 - 7,500 - 400 = 12,100
            t_str = start_date.isoformat()
            s_str = (start_date + timedelta(days=1)).isoformat()
            r_str = (start_date + timedelta(hours=4)).isoformat()  # Pre-settlement refund

            orders.append(Order(order_id=ord_id, amount=amt, status=OrderStatus.PAID, customer_id=f"cust_pdis_{i}", created_at=t_str))
            payments.append(Payment(payment_id=pay_id, order_id=ord_id, amount=amt, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method="card", settlement_id=setl_id, account_number=self.standard_account, created_at=t_str))
            settlements.append(Settlement(settlement_id=setl_id, utr=f"UTR_PART_DIS_{i}", gross_amount=amt - rfnd_amt, total_fee=fee, total_tax=tax, net_payout=net, settlement_date=s_str, account_number=self.standard_account))
            refunds.append(Refund(refund_id=rfnd_id, payment_id=pay_id, amount=rfnd_amt, reason="Partial cancellation", created_at=r_str))

            ground_truth[pay_id] = GroundTruthMetadata(
                is_anomaly=True,
                anomaly_type="PARTIAL_REFUND_NETTED",
                expected_match_status="AUTO_RESOLVED",
                expected_discrepancy=rfnd_amt,
                explanation="Valid partial refund ₹7,500 with exact 2% MDR fee ₹400 netted on gross."
            )

        return SyntheticBatch(
            batch_id=batch_id,
            orders=orders,
            payments=payments,
            settlements=settlements,
            refunds=refunds,
            ground_truth=ground_truth
        )
