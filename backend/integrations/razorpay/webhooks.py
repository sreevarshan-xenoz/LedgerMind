import hmac
import hashlib
import json
import time
from typing import Dict, Any, Tuple, Optional, Set
from .payments import map_razorpay_payment
from .settlements import map_razorpay_settlement
from .refunds import map_razorpay_refund
from ...core.models import Payment, Order, Settlement, Refund


class WebhookHandler:
    """
    Razorpay Webhook Handler with HMAC-SHA256 signature verification,
    idempotency tracking, and event normalization into LedgerMind models.
    """

    def __init__(self, webhook_secret: Optional[str] = None):
        self.webhook_secret = webhook_secret or "sample_webhook_secret_abc123"
        self.processed_event_ids: Set[str] = set()

    def verify_signature(self, raw_payload: bytes, signature: str) -> bool:
        """Verifies the HMAC-SHA256 signature from X-Razorpay-Signature header."""
        if not signature or not self.webhook_secret:
            return False
        
        expected_signature = hmac.new(
            self.webhook_secret.encode("utf-8"),
            raw_payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)

    def process_event(
        self,
        event_payload: Dict[str, Any],
        event_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes a validated Razorpay webhook event.
        Ensures idempotent processing and maps to LedgerMind entities.
        """
        evt_id = event_id or event_payload.get("event_id") or event_payload.get("id")
        if evt_id:
            if evt_id in self.processed_event_ids:
                return {
                    "status": "SKIPPED_DUPLICATE",
                    "event_id": evt_id,
                    "message": "Event has already been processed idempotently."
                }
            self.processed_event_ids.add(evt_id)

        event_name = event_payload.get("event", "")
        payload_entity = event_payload.get("payload", {})

        result: Dict[str, Any] = {
            "status": "PROCESSED",
            "event": event_name,
            "event_id": evt_id,
            "payment": None,
            "order": None,
            "settlement": None,
            "refund": None
        }

        if event_name in ["payment.captured", "payment.authorized", "payment.failed"]:
            pay_data = payload_entity.get("payment", {}).get("entity", {})
            if pay_data:
                payment, order = map_razorpay_payment(pay_data)
                result["payment"] = payment
                result["order"] = order

        elif event_name in ["refund.created", "refund.processed"]:
            rfnd_data = payload_entity.get("refund", {}).get("entity", {})
            if rfnd_data:
                refund = map_razorpay_refund(rfnd_data)
                result["refund"] = refund

        elif event_name in ["settlement.processed"]:
            setl_data = payload_entity.get("settlement", {}).get("entity", {})
            if setl_data:
                settlement = map_razorpay_settlement(setl_data)
                result["settlement"] = settlement

        return result
