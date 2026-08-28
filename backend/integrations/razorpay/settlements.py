from datetime import datetime, timezone
from typing import Dict, Any
from ...core.models import Settlement, SettlementStatus


def map_razorpay_settlement(rzp_data: Dict[str, Any], default_account: str = "XXXX-XXXX-9921") -> Settlement:
    """Normalizes Razorpay Settlement payload into LedgerMind Settlement model."""
    setl_id = rzp_data.get("id", "")
    utr = rzp_data.get("utr") or f"HDFC_UTR_{setl_id[-8:]}"

    gross_rupees = round(float(rzp_data.get("amount", 0)) / 100.0, 2)
    fee_rupees = round(float(rzp_data.get("fees", 0)) / 100.0, 2)
    tax_rupees = round(float(rzp_data.get("tax", 0)) / 100.0, 2)
    net_rupees = round(gross_rupees - fee_rupees - tax_rupees, 2)

    created_timestamp = rzp_data.get("created_at")
    if isinstance(created_timestamp, (int, float)):
        created_iso = datetime.fromtimestamp(created_timestamp, timezone.utc).isoformat()
    elif isinstance(created_timestamp, str):
        created_iso = created_timestamp
    else:
        created_iso = datetime.now(timezone.utc).isoformat()

    return Settlement(
        settlement_id=setl_id,
        utr=utr,
        gross_amount=gross_rupees,
        total_fee=fee_rupees,
        total_tax=tax_rupees,
        net_payout=net_rupees,
        settlement_date=created_iso,
        account_number=rzp_data.get("account_number") or default_account,
        status=SettlementStatus.SETTLED
    )
