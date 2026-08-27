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


class SyntheticFinancialGenerator:
    """
    Generates realistic multi-source financial feeds (Orders, Razorpay Payments,
    Bank Settlements, Refunds) with injected realistic edge cases and ground truth metadata.
    """

    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.payment_methods = ["upi", "card", "netbanking", "wallet"]
        self.method_weights = [0.55, 0.30, 0.10, 0.05]
        self.fee_rates = {
            "upi": 0.0,            # 0% for standard UPI
            "card": 0.02,          # 2.0% MDR for Cards
            "netbanking": 0.018,   # 1.8% for Netbanking
            "wallet": 0.019        # 1.9% for Wallets
        }
        self.gst_rate = 0.18       # 18% GST on processing fees

    def calculate_fee_and_tax(self, amount: float, method: str, custom_fee_rate: Optional[float] = None) -> Tuple[float, float, float]:
        rate = custom_fee_rate if custom_fee_rate is not None else self.fee_rates.get(method, 0.02)
        fee = round(amount * rate, 2)
        tax = round(fee * self.gst_rate, 2)
        net = round(amount - fee - tax, 2)
        return fee, tax, net

    def generate_batch(
        self,
        batch_id: str = "batch_001",
        num_records: int = 1000,
        anomaly_rate: float = 0.087,
        start_date: Optional[datetime] = None
    ) -> SyntheticBatch:
        if start_date is None:
            start_date = datetime(2026, 8, 20, 9, 0, 0)

        orders: List[Order] = []
        payments: List[Payment] = []
        settlements: List[Settlement] = []
        refunds: List[Refund] = []
        ground_truth: Dict[str, GroundTruthMetadata] = {}

        # Tracking for batch settlements (multi-transaction UTRs)
        settlement_batches: Dict[str, List[Tuple[float, float, float, str]]] = {}

        for i in range(num_records):
            rec_num = i + 1
            order_id = f"order_{rec_num:05d}_{uuid.uuid4().hex[:6]}"
            payment_id = f"pay_{rec_num:05d}_{uuid.uuid4().hex[:6]}"
            customer_id = f"cust_{random.randint(100, 9999)}"
            
            txn_time = start_date + timedelta(minutes=random.randint(5, 7200))
            txn_time_str = txn_time.isoformat()

            # Realistic transaction amount distributions in INR (from small ₹199 to large ₹45,000)
            amount_type = random.choices(["small", "medium", "large"], weights=[0.60, 0.35, 0.05])[0]
            if amount_type == "small":
                amount = float(random.choice([199, 299, 499, 799, 999, 1499]))
            elif amount_type == "medium":
                amount = float(random.randint(1500, 9500))
            else:
                amount = float(random.choice([12500, 18430, 19200, 24999, 38500, 48000]))

            method = random.choices(self.payment_methods, weights=self.method_weights)[0]
            fee, tax, net = self.calculate_fee_and_tax(amount, method)

            is_anomaly = random.random() < anomaly_rate

            if not is_anomaly:
                # Standard clean 3-way match
                settlement_id = f"setl_d_{txn_time.strftime('%Y%m%d')}_{random.randint(10, 99)}"
                orders.append(Order(
                    order_id=order_id,
                    amount=amount,
                    currency="INR",
                    status=OrderStatus.PAID,
                    customer_id=customer_id,
                    created_at=txn_time_str
                ))
                payments.append(Payment(
                    payment_id=payment_id,
                    order_id=order_id,
                    amount=amount,
                    fee=fee,
                    tax=tax,
                    net_amount=net,
                    status=PaymentStatus.CAPTURED,
                    method=method,
                    settlement_id=settlement_id,
                    auth_code=f"AUTH_{random.randint(100000, 999999)}",
                    created_at=txn_time_str
                ))
                
                if settlement_id not in settlement_batches:
                    settlement_batches[settlement_id] = []
                settlement_batches[settlement_id].append((amount, fee, tax, txn_time_str))

                ground_truth[payment_id] = GroundTruthMetadata(
                    is_anomaly=False,
                    expected_match_status="MATCHED",
                    expected_discrepancy=0.0,
                    explanation="Clean 3-way match across Order, Gateway payment, and Settlement."
                )

            else:
                # Anomaly injection with clear category definitions
                anomaly_type = random.choice([
                    ExceptionCategory.TIMING_LAG,
                    ExceptionCategory.MDR_GST_VARIANCE,
                    ExceptionCategory.PARTIAL_REFUND_NETTED,
                    ExceptionCategory.SPLIT_SETTLEMENT_BATCH,
                    ExceptionCategory.ORPHAN_PAYMENT,
                    ExceptionCategory.BANK_UTR_AMOUNT_MISMATCH,
                    ExceptionCategory.CHARGEBACK_DISPUTE_HOLD,
                    ExceptionCategory.DUPLICATE_AUTH_CAPTURE,
                    ExceptionCategory.MISSING_SETTLEMENT_RECORD
                ])

                if anomaly_type == ExceptionCategory.TIMING_LAG:
                    # Settled T+3 due to bank holiday cutoff; explainable timing
                    settlement_id = f"setl_d_{(txn_time + timedelta(days=3)).strftime('%Y%m%d')}_{random.randint(10, 99)}"
                    orders.append(Order(order_id=order_id, amount=amount, status=OrderStatus.PAID, customer_id=customer_id, created_at=txn_time_str))
                    payments.append(Payment(payment_id=payment_id, order_id=order_id, amount=amount, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method=method, settlement_id=settlement_id, created_at=txn_time_str))
                    if settlement_id not in settlement_batches:
                        settlement_batches[settlement_id] = []
                    settlement_batches[settlement_id].append((amount, fee, tax, (txn_time + timedelta(days=3)).isoformat()))

                    ground_truth[payment_id] = GroundTruthMetadata(
                        is_anomaly=True,
                        anomaly_type=anomaly_type.value,
                        expected_match_status="AUTO_RESOLVED",
                        expected_discrepancy=0.0,
                        explanation="Settlement processed on T+3 due to weekend/bank cutoff timing window."
                    )

                elif anomaly_type == ExceptionCategory.MDR_GST_VARIANCE:
                    # International card surcharge (e.g., 3.0% instead of standard 2.0%)
                    custom_fee, custom_tax, custom_net = self.calculate_fee_and_tax(amount, method, custom_fee_rate=0.03)
                    settlement_id = f"setl_d_{txn_time.strftime('%Y%m%d')}_{random.randint(10, 99)}"
                    orders.append(Order(order_id=order_id, amount=amount, status=OrderStatus.PAID, customer_id=customer_id, created_at=txn_time_str))
                    payments.append(Payment(payment_id=payment_id, order_id=order_id, amount=amount, fee=custom_fee, tax=custom_tax, net_amount=custom_net, status=PaymentStatus.CAPTURED, method=method, settlement_id=settlement_id, created_at=txn_time_str))
                    if settlement_id not in settlement_batches:
                        settlement_batches[settlement_id] = []
                    settlement_batches[settlement_id].append((amount, custom_fee, custom_tax, txn_time_str))

                    diff = round(custom_fee + custom_tax - (fee + tax), 2)
                    ground_truth[payment_id] = GroundTruthMetadata(
                        is_anomaly=True,
                        anomaly_type=anomaly_type.value,
                        expected_match_status="AUTO_RESOLVED",
                        expected_discrepancy=diff,
                        explanation=f"Custom MDR surcharge applied (+1% international rate). Net fee variance is ₹{diff}."
                    )

                elif anomaly_type == ExceptionCategory.PARTIAL_REFUND_NETTED:
                    # A refund occurred, deducting amount from net payout
                    refund_amount = round(amount * random.choice([0.25, 0.50, 1.0]), 2)
                    settlement_id = f"setl_d_{txn_time.strftime('%Y%m%d')}_{random.randint(10, 99)}"
                    orders.append(Order(order_id=order_id, amount=amount, status=OrderStatus.REFUNDED if refund_amount == amount else OrderStatus.PAID, customer_id=customer_id, created_at=txn_time_str))
                    payments.append(Payment(payment_id=payment_id, order_id=order_id, amount=amount, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.REFUNDED if refund_amount == amount else PaymentStatus.CAPTURED, method=method, settlement_id=settlement_id, created_at=txn_time_str))
                    refund_id = f"rfnd_{rec_num:05d}_{uuid.uuid4().hex[:6]}"
                    refunds.append(Refund(
                        refund_id=refund_id,
                        payment_id=payment_id,
                        amount=refund_amount,
                        reason="Customer initiated partial cancellation",
                        status=RefundStatus.PROCESSED,
                        created_at=(txn_time + timedelta(hours=2)).isoformat()
                    ))
                    if settlement_id not in settlement_batches:
                        settlement_batches[settlement_id] = []
                    # Settle net minus refund
                    settlement_batches[settlement_id].append((amount - refund_amount, fee, tax, txn_time_str))

                    ground_truth[payment_id] = GroundTruthMetadata(
                        is_anomaly=True,
                        anomaly_type=anomaly_type.value,
                        expected_match_status="AUTO_RESOLVED",
                        expected_discrepancy=refund_amount,
                        explanation=f"Refund of ₹{refund_amount} was netted against settlement batch."
                    )

                elif anomaly_type == ExceptionCategory.SPLIT_SETTLEMENT_BATCH:
                    # Grouped under shared multi-payment settlement UTR
                    settlement_id = f"setl_shared_batch_{random.randint(1, 5)}"
                    orders.append(Order(order_id=order_id, amount=amount, status=OrderStatus.PAID, customer_id=customer_id, created_at=txn_time_str))
                    payments.append(Payment(payment_id=payment_id, order_id=order_id, amount=amount, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method=method, settlement_id=settlement_id, created_at=txn_time_str))
                    if settlement_id not in settlement_batches:
                        settlement_batches[settlement_id] = []
                    settlement_batches[settlement_id].append((amount, fee, tax, txn_time_str))

                    ground_truth[payment_id] = GroundTruthMetadata(
                        is_anomaly=True,
                        anomaly_type=anomaly_type.value,
                        expected_match_status="AUTO_RESOLVED",
                        expected_discrepancy=0.0,
                        explanation="Order aggregated in multi-order batch settlement."
                    )

                elif anomaly_type == ExceptionCategory.ORPHAN_PAYMENT:
                    # Payment exists in Razorpay but has no corresponding Order in ERP (Unresolved)
                    settlement_id = f"setl_d_{txn_time.strftime('%Y%m%d')}_{random.randint(10, 99)}"
                    payments.append(Payment(payment_id=payment_id, order_id=None, amount=amount, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method=method, settlement_id=settlement_id, created_at=txn_time_str))
                    if settlement_id not in settlement_batches:
                        settlement_batches[settlement_id] = []
                    settlement_batches[settlement_id].append((amount, fee, tax, txn_time_str))

                    ground_truth[payment_id] = GroundTruthMetadata(
                        is_anomaly=True,
                        anomaly_type=anomaly_type.value,
                        expected_match_status="UNRESOLVED",
                        expected_discrepancy=amount,
                        explanation="Orphan payment: Captured in Gateway with missing ERP Order ID."
                    )

                elif anomaly_type == ExceptionCategory.BANK_UTR_AMOUNT_MISMATCH:
                    # Bank credited less than expected (Unresolved honest exception)
                    variance = float(random.choice([250, 450, 770, 1200]))
                    settlement_id = f"setl_d_{txn_time.strftime('%Y%m%d')}_{random.randint(10, 99)}"
                    orders.append(Order(order_id=order_id, amount=amount, status=OrderStatus.PAID, customer_id=customer_id, created_at=txn_time_str))
                    payments.append(Payment(payment_id=payment_id, order_id=order_id, amount=amount, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method=method, settlement_id=settlement_id, created_at=txn_time_str))
                    if settlement_id not in settlement_batches:
                        settlement_batches[settlement_id] = []
                    # Injected unexplained bank deduction
                    settlement_batches[settlement_id].append((amount - variance, fee, tax, txn_time_str))

                    ground_truth[payment_id] = GroundTruthMetadata(
                        is_anomaly=True,
                        anomaly_type=anomaly_type.value,
                        expected_match_status="UNRESOLVED",
                        expected_discrepancy=variance,
                        explanation=f"Unexplained bank shortfall of ₹{variance} on UTR payout."
                    )

                elif anomaly_type == ExceptionCategory.CHARGEBACK_DISPUTE_HOLD:
                    # Dispute open, settlement withheld (Unresolved)
                    orders.append(Order(order_id=order_id, amount=amount, status=OrderStatus.PAID, customer_id=customer_id, created_at=txn_time_str))
                    payments.append(Payment(payment_id=payment_id, order_id=order_id, amount=amount, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method=method, settlement_id=None, created_at=txn_time_str))

                    ground_truth[payment_id] = GroundTruthMetadata(
                        is_anomaly=True,
                        anomaly_type=anomaly_type.value,
                        expected_match_status="UNRESOLVED",
                        expected_discrepancy=net,
                        explanation="Chargeback dispute raised by customer; funds placed on hold."
                    )

                elif anomaly_type == ExceptionCategory.DUPLICATE_AUTH_CAPTURE:
                    # Duplicate capture on single order (Unresolved)
                    dup_pay_id = f"pay_{rec_num:05d}_dup_{uuid.uuid4().hex[:4]}"
                    orders.append(Order(order_id=order_id, amount=amount, status=OrderStatus.PAID, customer_id=customer_id, created_at=txn_time_str))
                    payments.append(Payment(payment_id=payment_id, order_id=order_id, amount=amount, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method=method, settlement_id=None, created_at=txn_time_str))
                    payments.append(Payment(payment_id=dup_pay_id, order_id=order_id, amount=amount, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method=method, settlement_id=None, created_at=txn_time_str))

                    ground_truth[payment_id] = GroundTruthMetadata(
                        is_anomaly=True,
                        anomaly_type=anomaly_type.value,
                        expected_match_status="UNRESOLVED",
                        expected_discrepancy=amount,
                        explanation="Duplicate gateway payment captured for single Order ID."
                    )

                elif anomaly_type == ExceptionCategory.MISSING_SETTLEMENT_RECORD:
                    # Payment captured, but settlement record missing from bank feed (Unresolved)
                    orders.append(Order(order_id=order_id, amount=amount, status=OrderStatus.PAID, customer_id=customer_id, created_at=txn_time_str))
                    payments.append(Payment(payment_id=payment_id, order_id=order_id, amount=amount, fee=fee, tax=tax, net_amount=net, status=PaymentStatus.CAPTURED, method=method, settlement_id=None, created_at=txn_time_str))

                    ground_truth[payment_id] = GroundTruthMetadata(
                        is_anomaly=True,
                        anomaly_type=anomaly_type.value,
                        expected_match_status="UNRESOLVED",
                        expected_discrepancy=net,
                        explanation="Payment captured but not yet remitted by bank/gateway."
                    )

        # Consolidate settlement batches into Bank Settlement objects with realistic UTRs
        for s_id, items in settlement_batches.items():
            tot_gross = sum(item[0] for item in items)
            tot_fee = sum(item[1] for item in items)
            tot_tax = sum(item[2] for item in items)
            tot_net = round(tot_gross - tot_fee - tot_tax, 2)
            settlement_date = items[0][3]
            bank_code = random.choice(["HDFC", "ICIC", "SBIN", "UTIB", "KKBK"])
            utr = f"{bank_code}UTR{random.randint(100000000, 999999999)}"

            settlements.append(Settlement(
                settlement_id=s_id,
                utr=utr,
                gross_amount=round(tot_gross, 2),
                total_fee=round(tot_fee, 2),
                total_tax=round(tot_tax, 2),
                net_payout=tot_net,
                settlement_date=settlement_date,
                account_number=f"XXXX-XXXX-{random.randint(1000, 9999)}",
                status=SettlementStatus.SETTLED
            ))

        return SyntheticBatch(
            batch_id=batch_id,
            orders=orders,
            payments=payments,
            settlements=settlements,
            refunds=refunds,
            ground_truth=ground_truth
        )
