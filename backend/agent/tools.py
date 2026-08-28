from datetime import datetime
from typing import Dict, Any, Optional
from ..core.models import SyntheticBatch, Order, Payment, Settlement, Refund


class InvestigationTools:
    """
    Structured analytical tools called during exception investigation
    and merchant Settlement Q&A.
    """

    def __init__(self, batch: SyntheticBatch):
        self.batch = batch
        self.orders_map = {o.order_id: o for o in batch.orders}
        self.payments_map = {p.payment_id: p for p in batch.payments}
        self.settlements_map = {s.settlement_id: s for s in batch.settlements}
        self.refunds_map: Dict[str, list] = {}
        for r in batch.refunds:
            self.refunds_map.setdefault(r.payment_id, []).append(r)

    def inspect_payment_lifecycle(self, payment_id: str) -> Dict[str, Any]:
        """Inspects full end-to-end lifecycle timestamps and status."""
        payment = self.payments_map.get(payment_id)
        if not payment:
            return {"error": f"Payment ID {payment_id} not found."}

        order = self.orders_map.get(payment.order_id) if payment.order_id else None
        settlement = self.settlements_map.get(payment.settlement_id) if payment.settlement_id else None
        refunds = self.refunds_map.get(payment_id, [])

        return {
            "payment_id": payment.payment_id,
            "order_id": payment.order_id,
            "order_found": order is not None,
            "order_amount": order.amount if order else None,
            "payment_amount": payment.amount,
            "payment_fee": payment.fee,
            "payment_tax": payment.tax,
            "payment_net": payment.net_amount,
            "payment_status": payment.status.value,
            "payment_method": payment.method,
            "settlement_id": payment.settlement_id,
            "settlement_found": settlement is not None,
            "settlement_utr": settlement.utr if settlement else None,
            "settlement_date": settlement.settlement_date if settlement else None,
            "refund_count": len(refunds),
            "refunds": [{"refund_id": r.refund_id, "amount": r.amount, "reason": r.reason} for r in refunds]
        }

    def calculate_fee_variance(self, payment_id: str, standard_rate: float = 0.02) -> Dict[str, Any]:
        """Calculates expected vs charged MDR and GST variance."""
        payment = self.payments_map.get(payment_id)
        if not payment:
            return {"error": f"Payment ID {payment_id} not found."}

        expected_fee = round(payment.amount * standard_rate, 2)
        expected_tax = round(expected_fee * 0.18, 2)
        expected_net = round(payment.amount - expected_fee - expected_tax, 2)

        fee_diff = round(payment.fee - expected_fee, 2)
        tax_diff = round(payment.tax - expected_tax, 2)
        net_diff = round(expected_net - payment.net_amount, 2)

        is_variance = abs(fee_diff) > 0.01 or abs(tax_diff) > 0.01

        return {
            "payment_id": payment_id,
            "amount": payment.amount,
            "method": payment.method,
            "charged_fee": payment.fee,
            "charged_tax": payment.tax,
            "charged_net": payment.net_amount,
            "expected_fee": expected_fee,
            "expected_tax": expected_tax,
            "expected_net": expected_net,
            "fee_difference": fee_diff,
            "tax_difference": tax_diff,
            "net_difference": net_diff,
            "is_variance": is_variance,
            "implied_rate_pct": round((payment.fee / payment.amount) * 100, 2) if payment.amount > 0 else 0.0
        }

    def query_bank_settlement(self, settlement_id: str) -> Dict[str, Any]:
        """Queries the bank UTR payout record and batch aggregation details."""
        settlement = self.settlements_map.get(settlement_id)
        if not settlement:
            return {"error": f"Settlement {settlement_id} not found."}

        associated_payments = [
            p for p in self.batch.payments if p.settlement_id == settlement_id
        ]

        return {
            "settlement_id": settlement.settlement_id,
            "utr": settlement.utr,
            "gross_amount": settlement.gross_amount,
            "total_fee": settlement.total_fee,
            "total_tax": settlement.total_tax,
            "net_payout": settlement.net_payout,
            "account_number": settlement.account_number,
            "settlement_date": settlement.settlement_date,
            "status": settlement.status.value,
            "transaction_count": len(associated_payments)
        }

    def check_timing_lag(self, payment_id: str) -> Dict[str, Any]:
        """Calculates days elapsed between payment capture and settlement payout."""
        payment = self.payments_map.get(payment_id)
        if not payment or not payment.settlement_id:
            return {"has_lag": False, "days": 0}

        settlement = self.settlements_map.get(payment.settlement_id)
        if not settlement:
            return {"has_lag": False, "days": 0}

        try:
            p_time = datetime.fromisoformat(payment.created_at)
            s_time = datetime.fromisoformat(settlement.settlement_date)
            delta_days = (s_time.date() - p_time.date()).days
            return {
                "has_lag": delta_days > 1,
                "days_elapsed": delta_days,
                "payment_date": p_time.strftime("%Y-%m-%d"),
                "settlement_date": s_time.strftime("%Y-%m-%d"),
                "is_weekend_or_holiday": delta_days in [2, 3]
            }
        except Exception:
            return {"has_lag": False, "days": 0}
