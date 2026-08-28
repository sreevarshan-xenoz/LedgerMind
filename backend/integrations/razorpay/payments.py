from datetime import datetime, timezone
from typing import Dict, Any, Tuple
from ...core.models import Payment, PaymentStatus, Order, OrderStatus


def map_razorpay_payment(rzp_data: Dict[str, Any], default_account: str = "XXXX-XXXX-9921") -> Tuple[Payment, Order]:
    """
    Normalizes Razorpay Payment API/Webhook payload into LedgerMind models.
    Converts paise to rupees and computes net amounts.
    """
    pay_id = rzp_data.get("id", "")
    order_id = rzp_data.get("order_id") or f"order_{pay_id}"
    
    # Razorpay amounts are in paise (1 INR = 100 paise)
    gross_rupees = round(float(rzp_data.get("amount", 0)) / 100.0, 2)
    fee_rupees = round(float(rzp_data.get("fee", 0)) / 100.0, 2)
    tax_rupees = round(float(rzp_data.get("tax", 0)) / 100.0, 2)
    net_rupees = round(gross_rupees - fee_rupees - tax_rupees, 2)

    raw_status = rzp_data.get("status", "captured").lower()
    if raw_status == "captured":
        pay_status = PaymentStatus.CAPTURED
        ord_status = OrderStatus.PAID
    elif raw_status == "refunded":
        pay_status = PaymentStatus.REFUNDED
        ord_status = OrderStatus.REFUNDED
    elif raw_status == "authorized":
        pay_status = PaymentStatus.AUTHORIZED
        ord_status = OrderStatus.CREATED
    else:
        pay_status = PaymentStatus.FAILED
        ord_status = OrderStatus.CANCELLED

    created_timestamp = rzp_data.get("created_at")
    if isinstance(created_timestamp, (int, float)):
        created_iso = datetime.fromtimestamp(created_timestamp, timezone.utc).isoformat()
    elif isinstance(created_timestamp, str):
        created_iso = created_timestamp
    else:
        created_iso = datetime.now(timezone.utc).isoformat()

    order = Order(
        order_id=order_id,
        amount=gross_rupees,
        currency=rzp_data.get("currency", "INR"),
        status=ord_status,
        customer_id=rzp_data.get("customer_id") or rzp_data.get("email") or f"cust_{pay_id[-6:]}",
        created_at=created_iso
    )

    payment = Payment(
        payment_id=pay_id,
        order_id=order_id,
        amount=gross_rupees,
        fee=fee_rupees,
        tax=tax_rupees,
        net_amount=net_rupees,
        status=pay_status,
        method=rzp_data.get("method", "card"),
        settlement_id=rzp_data.get("settlement_id"),
        auth_code=rzp_data.get("auth_code") or rzp_data.get("acquirer_data", {}).get("auth_code"),
        account_number=default_account,
        created_at=created_iso
    )

    return payment, order
