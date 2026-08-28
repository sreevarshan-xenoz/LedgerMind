import pytest
import json
import hmac
import hashlib
from backend.integrations.razorpay.client import RazorpayClient
from backend.integrations.razorpay.payments import map_razorpay_payment
from backend.integrations.razorpay.settlements import map_razorpay_settlement
from backend.integrations.razorpay.refunds import map_razorpay_refund
from backend.integrations.razorpay.webhooks import WebhookHandler
from backend.agent.evidence_graph import EvidenceGraphInvestigator
from backend.core.live_store import LiveReconciliationStore
from backend.core.models import PaymentStatus, OrderStatus, ExceptionCategory, Settlement, SettlementStatus


def test_razorpay_client_sandbox():
    client = RazorpayClient()
    payments = client.fetch_payments(count=10)
    settlements = client.fetch_settlements(count=5)
    refunds = client.fetch_refunds(count=5)

    assert len(payments) == 10
    assert len(settlements) == 5
    assert len(refunds) == 5
    assert payments[0]["id"].startswith("pay_rzp_live_")
    assert payments[0]["amount"] > 0


def test_razorpay_payment_mapper():
    raw_rzp = {
        "id": "pay_test_99812",
        "entity": "payment",
        "amount": 500000,  # 5,000 INR in paise
        "currency": "INR",
        "status": "captured",
        "order_id": "order_test_99812",
        "method": "card",
        "fee": 10000,      # 100 INR in paise
        "tax": 1800,       # 18 INR in paise
        "auth_code": "AUTH_998811",
        "created_at": 1787300000
    }

    payment, order = map_razorpay_payment(raw_rzp)
    assert payment.payment_id == "pay_test_99812"
    assert payment.amount == 5000.0
    assert payment.fee == 100.0
    assert payment.tax == 18.0
    assert payment.net_amount == 4882.0
    assert payment.status == PaymentStatus.CAPTURED
    assert order.order_id == "order_test_99812"
    assert order.amount == 5000.0


def test_webhook_hmac_signature_verification():
    secret = "test_webhook_secret_key_123"
    handler = WebhookHandler(webhook_secret=secret)

    payload_dict = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_webhook_001",
                    "amount": 250000,
                    "currency": "INR",
                    "status": "captured",
                    "fee": 5000,
                    "tax": 900
                }
            }
        }
    }
    raw_body = json.dumps(payload_dict).encode("utf-8")

    # Generate valid signature
    valid_sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    assert handler.verify_signature(raw_body, valid_sig) is True

    # Invalid signature must fail
    assert handler.verify_signature(raw_body, "invalid_forged_signature_hex") is False


def test_webhook_idempotency():
    handler = WebhookHandler()
    payload = {"event": "payment.captured", "id": "evt_unique_12345", "payload": {}}

    res1 = handler.process_event(payload, event_id="evt_unique_12345")
    assert res1["status"] == "PROCESSED"

    res2 = handler.process_event(payload, event_id="evt_unique_12345")
    assert res2["status"] == "SKIPPED_DUPLICATE"


def test_live_store_and_human_review_queue():
    store = LiveReconciliationStore()

    # Ingest settlement and primary payment
    setl = Settlement(
        settlement_id="setl_live_01",
        utr="HDFC_UTR_LIVE_01",
        gross_amount=5000.0,
        total_fee=100.0,
        total_tax=18.0,
        net_payout=4882.0,
        settlement_date="2026-08-21T10:00:00",
        account_number="XXXX-XXXX-9921",
        status=SettlementStatus.SETTLED
    )
    store.ingest_settlement(setl)

    # Ingest primary payment & duplicate payment
    raw_pay_a = {"id": "pay_live_dup_A", "amount": 500000, "fee": 10000, "tax": 1800, "order_id": "ord_live_dup_1", "settlement_id": "setl_live_01", "status": "captured"}
    raw_pay_b = {"id": "pay_live_dup_B", "amount": 500000, "fee": 10000, "tax": 1800, "order_id": "ord_live_dup_1", "status": "captured"}

    pay_a, ord_a = map_razorpay_payment(raw_pay_a)
    pay_b, _ = map_razorpay_payment(raw_pay_b)

    store.ingest_payment(pay_a, ord_a)
    result = store.ingest_payment(pay_b)

    assert result.metrics.total_records_ingested == 2
    assert result.metrics.true_reconciliations == 1
    assert len(store.human_review_queue) == 1

    # Check human review queue item
    exc_id = list(store.human_review_queue.keys())[0]
    queue_item = store.human_review_queue[exc_id]
    assert queue_item["record_id"] == "pay_live_dup_B"
    assert "Double capture" in queue_item["math_proof"]
    assert len(queue_item["citations"]) >= 1

    # Execute human approval action
    action_res = store.process_human_decision(exc_id, "INITIATE_REFUND", "Approved immediate reversal of secondary authorization.")
    assert action_res["status"] == "SUCCESS"
    assert len(store.human_review_queue) == 0
    assert len(store.audit_action_log) == 1
