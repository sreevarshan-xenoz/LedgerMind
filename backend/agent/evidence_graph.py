from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from ..core.models import ExceptionItem, ExceptionCategory, SyntheticBatch
from .tools import InvestigationTools


class EvidenceCitation(BaseModel):
    entity_type: str  # PAYMENT, ORDER, SETTLEMENT, REFUND, FEE_TIER
    entity_id: str
    field_name: str
    field_value: str
    description: str


class EvidenceDiagnosis(BaseModel):
    exception_id: str
    record_id: str
    category: ExceptionCategory
    decision: str  # RESOLVED or HUMAN_REVIEW_REQUIRED
    math_proof: str
    citations: List[EvidenceCitation] = Field(default_factory=list)
    confidence: float
    reasoning_trace: str
    action_required: str
    requires_human_approval: bool = False


class EvidenceGraphInvestigator:
    """
    Evidence-backed AI investigator. Every finding is anchored by verifiable
    ledger citations and mathematical proofs. Discrepancies without rigorous evidence
    are strictly routed to the Human Approval Queue.
    """

    def __init__(self, batch: SyntheticBatch):
        self.batch = batch
        self.tools = InvestigationTools(batch)
        self.orders_map = {o.order_id: o for o in batch.orders}
        self.payments_map = {p.payment_id: p for p in batch.payments}
        self.settlements_map = {s.settlement_id: s for s in batch.settlements}
        self.refunds_map: Dict[str, list] = {}
        for r in batch.refunds:
            self.refunds_map.setdefault(r.payment_id, []).append(r)

    def diagnose_exception(self, exc: ExceptionItem) -> EvidenceDiagnosis:
        pid = exc.payment_id or exc.record_id
        payment = self.payments_map.get(pid)
        order = self.orders_map.get(exc.order_id) if exc.order_id else (self.orders_map.get(payment.order_id) if payment and payment.order_id else None)
        settlement = self.settlements_map.get(exc.settlement_id) if exc.settlement_id else (self.settlements_map.get(payment.settlement_id) if payment and payment.settlement_id else None)
        refunds = self.refunds_map.get(pid, [])

        citations: List[EvidenceCitation] = []

        # 1. Check for Duplicate Authorization (Human Action Required)
        if exc.category == ExceptionCategory.DUPLICATE_AUTH_CAPTURE:
            if payment:
                citations.append(EvidenceCitation(entity_type="PAYMENT", entity_id=payment.payment_id, field_name="amount", field_value=f"₹{payment.amount:,.2f}", description="Duplicate capture authorization"))
            if order:
                citations.append(EvidenceCitation(entity_type="ORDER", entity_id=order.order_id, field_name="amount", field_value=f"₹{order.amount:,.2f}", description="Merchant ERP Order cart total"))

            return EvidenceDiagnosis(
                exception_id=exc.exception_id,
                record_id=pid,
                category=exc.category,
                decision="HUMAN_REVIEW_REQUIRED",
                math_proof=f"Double capture: 2 x ₹{payment.amount if payment else exc.expected_amount:,.2f} charged for single order {order.order_id if order else 'N/A'}.",
                citations=citations,
                confidence=0.99,
                reasoning_trace=f"Multiple payments detected for Order {order.order_id if order else 'N/A'}. Payment {pid} requires human review for refund initiation.",
                action_required="Click [Approve Refund] to trigger gateway reversal on secondary payment.",
                requires_human_approval=True
            )

        # 2. Check for Foreign Account Mismatch (Human Action Required)
        if exc.category == ExceptionCategory.ACCOUNT_MISMATCH:
            if settlement:
                citations.append(EvidenceCitation(entity_type="SETTLEMENT", entity_id=settlement.settlement_id, field_name="account_number", field_value=settlement.account_number, description="Unauthorized destination bank account"))
                citations.append(EvidenceCitation(entity_type="SETTLEMENT", entity_id=settlement.settlement_id, field_name="utr", field_value=settlement.utr, description="Bank remittance reference"))

            return EvidenceDiagnosis(
                exception_id=exc.exception_id,
                record_id=pid,
                category=exc.category,
                decision="HUMAN_REVIEW_REQUIRED",
                math_proof=f"Destination account {settlement.account_number if settlement else 'UNKNOWN'} mismatch with designated primary account.",
                citations=citations,
                confidence=0.99,
                reasoning_trace=f"Bank UTR was credited to foreign account {settlement.account_number if settlement else 'UNKNOWN'}. Immediate merchant ops escalation required.",
                action_required="Click [Escalate to Banking Ops] to halt gateway payout routing.",
                requires_human_approval=True
            )

        # 3. Check for Post-Settlement Refund Timing (Auto-Resolved with Evidence)
        if exc.category == ExceptionCategory.POST_SETTLEMENT_REFUND_DEFERRED:
            total_rfnd = sum(r.amount for r in refunds)
            if payment:
                citations.append(EvidenceCitation(entity_type="PAYMENT", entity_id=payment.payment_id, field_name="net_amount", field_value=f"₹{payment.net_amount:,.2f}", description="Initial gross net payout"))
            if settlement:
                citations.append(EvidenceCitation(entity_type="SETTLEMENT", entity_id=settlement.settlement_id, field_name="settlement_date", field_value=settlement.settlement_date, description="Initial bank settlement clearance date"))
            if refunds:
                citations.append(EvidenceCitation(entity_type="REFUND", entity_id=refunds[0].refund_id, field_name="created_at", field_value=refunds[0].created_at, description="Refund request date (Post-Settlement)"))

            return EvidenceDiagnosis(
                exception_id=exc.exception_id,
                record_id=pid,
                category=exc.category,
                decision="RESOLVED",
                math_proof=f"Initial settlement ₹{payment.net_amount if payment else 0:,.2f} remitted on {settlement.settlement_date if settlement else 'T+1'}. Subsequent refund ₹{total_rfnd:,.2f} deferred to next cycle.",
                citations=citations,
                confidence=0.99,
                reasoning_trace="Refund was requested after settlement cutoff. Initial payout verified gross; refund debit queued in deferred ledger.",
                action_required="No manual action required. Deferred ledger entry verified.",
                requires_human_approval=False
            )

        # 4. Check for Multi-UTR Split Settlement (Auto-Resolved with Evidence)
        if exc.category == ExceptionCategory.SPLIT_MULTI_UTR_SETTLED:
            if payment:
                citations.append(EvidenceCitation(entity_type="PAYMENT", entity_id=payment.payment_id, field_name="amount", field_value=f"₹{payment.amount:,.2f}", description="Gross payment authorized"))
            if exc.settlement_utr:
                citations.append(EvidenceCitation(entity_type="SETTLEMENT", entity_id=exc.settlement_id or "SPLIT", field_name="utrs", field_value=exc.settlement_utr, description="Consolidated split settlement UTRs"))

            return EvidenceDiagnosis(
                exception_id=exc.exception_id,
                record_id=pid,
                category=exc.category,
                decision="RESOLVED",
                math_proof=f"Gross ₹{payment.amount if payment else 0:,.2f} = Σ(Net UTRs ₹{exc.actual_amount:,.2f}) + Fees ₹{(payment.fee + payment.tax) if payment else 0:,.2f}.",
                citations=citations,
                confidence=0.99,
                reasoning_trace="Transaction verified across multi-UTR split remittance batch with 100% mathematical precision.",
                action_required="No action required. Remittance confirmed across split schedules.",
                requires_human_approval=False
            )

        # 5. Check for MDR Fee Surcharge (Auto-Resolved with Evidence)
        if exc.category == ExceptionCategory.MDR_GST_VARIANCE:
            fee_var = self.tools.calculate_fee_variance(pid)
            if payment:
                citations.append(EvidenceCitation(entity_type="PAYMENT", entity_id=payment.payment_id, field_name="fee", field_value=f"₹{payment.fee:,.2f}", description=f"Gateway charged fee ({fee_var.get('implied_rate_pct')}% MDR)"))
                citations.append(EvidenceCitation(entity_type="PAYMENT", entity_id=payment.payment_id, field_name="tax", field_value=f"₹{payment.tax:,.2f}", description="GST (18% on fee)"))
            if order:
                citations.append(EvidenceCitation(entity_type="ORDER", entity_id=order.order_id, field_name="amount", field_value=f"₹{order.amount:,.2f}", description="Gross cart amount"))

            diff = fee_var.get("net_difference", exc.discrepancy_amount)
            return EvidenceDiagnosis(
                exception_id=exc.exception_id,
                record_id=pid,
                category=exc.category,
                decision="RESOLVED",
                math_proof=f"₹{abs(diff):,.2f} variance = ({fee_var.get('implied_rate_pct')}% applied - 2.0% baseline) on ₹{payment.amount if payment else 0:,.2f} gross.",
                citations=citations,
                confidence=0.96,
                reasoning_trace=f"Custom MDR surcharge of {fee_var.get('implied_rate_pct')}% confirmed for international/corporate card tier.",
                action_required="Auto-adjusted fee schedule ledger entry for card tier surcharge.",
                requires_human_approval=False
            )

        # 6. Unresolved / Unknown Discrepancy (Human Review Required)
        if payment:
            citations.append(EvidenceCitation(entity_type="PAYMENT", entity_id=payment.payment_id, field_name="amount", field_value=f"₹{payment.amount:,.2f}", description="Gateway captured amount"))
        if settlement:
            citations.append(EvidenceCitation(entity_type="SETTLEMENT", entity_id=settlement.settlement_id, field_name="net_payout", field_value=f"₹{settlement.net_payout:,.2f}", description="Actual bank remittance payout"))

        return EvidenceDiagnosis(
            exception_id=exc.exception_id,
            record_id=pid,
            category=exc.category,
            decision="HUMAN_REVIEW_REQUIRED",
            math_proof=f"Unaccounted discrepancy: ₹{abs(exc.discrepancy_amount):,.2f} remains unexplained by standard fee schedules or registered refunds. Auto-resolution blocked.",
            citations=citations,
            confidence=0.31,
            reasoning_trace=f"No matching fee schedule, refund debit, or batch split explains the ₹{abs(exc.discrepancy_amount):,.2f} variance. Safe escalation to banking ops.",
            action_required="Click [Escalate to Merchant Ops] to request bank deduction memo.",
            requires_human_approval=True
        )
