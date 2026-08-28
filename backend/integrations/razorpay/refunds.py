from datetime import datetime, timezone
from typing import Dict, Any
from ...core.models import Refund, RefundStatus


def map_razorpay_refund(rzp_data: Dict[str, Any]) -> Refund:
    """Normalizes Razorpay Refund payload into LedgerMind Refund model."""
    rfnd_id = rzp_data.get("id", "")
    pay_id = rzp_data.get("payment_id", "")
    amount_rupees = round(float(rzp_data.get("amount", 0)) / 100.0, 2)

    created_timestamp = rzp_data.get("created_at")
    if isinstance(created_timestamp, (int, float)):
        created_iso = datetime.fromtimestamp(created_timestamp, timezone.utc).isoformat()
    elif isinstance(created_timestamp, str):
        created_iso = created_timestamp
    else:
        created_iso = datetime.now(timezone.utc).isoformat()

    return Refund(
        refund_id=rfnd_id,
        payment_id=pay_id,
        amount=amount_rupees,
        reason=rzp_data.get("notes", {}).get("reason") or "Customer requested refund",
        status=RefundStatus.PROCESSED,
        created_at=created_iso
    )
