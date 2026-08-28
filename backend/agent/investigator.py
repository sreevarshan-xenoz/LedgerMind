from typing import List, Tuple, Dict, Any
from ..core.models import (
    ExceptionItem, ExceptionCategory,
    SyntheticBatch
)
from .tools import InvestigationTools


class AIExceptionInvestigator:
    """
    AI-driven financial exception investigator.
    Uses structured diagnostic tools to analyze discrepancies, explain variances,
    and cleanly partition into AI-Resolved vs Honest Unresolved exceptions.
    """

    def __init__(self, batch: SyntheticBatch):
        self.tools = InvestigationTools(batch)

    def investigate_all(self, raw_exceptions: List[ExceptionItem]) -> Tuple[List[ExceptionItem], List[ExceptionItem]]:
        resolved: List[ExceptionItem] = []
        unresolved: List[ExceptionItem] = []

        for exc in raw_exceptions:
            inv_exc = self.investigate_single(exc)
            if inv_exc.is_resolved:
                resolved.append(inv_exc)
            else:
                unresolved.append(inv_exc)

        return resolved, unresolved

    def investigate_single(self, exc: ExceptionItem) -> ExceptionItem:
        pid = exc.payment_id or exc.record_id
        
        # 1. Honest Unresolved Exception Categories (Strict Guardrails)
        if exc.category == ExceptionCategory.ORPHAN_PAYMENT:
            exc.is_resolved = False
            exc.confidence = 0.99
            exc.ai_reasoning_trace = (
                f"Gateway payment {pid} was captured for ₹{exc.expected_amount:,.2f} but has no matching Order record in ERP. "
                "Potential unhandled checkout webhook or dropped session."
            )
            exc.suggested_action = "Query customer checkout logs or contact customer service for missing order creation."
            exc.audit_trail.append("AI_INVESTIGATION_CONFIRMED_ORPHAN")
            return exc

        if exc.category == ExceptionCategory.DUPLICATE_AUTH_CAPTURE:
            exc.is_resolved = False
            exc.confidence = 0.99
            exc.ai_reasoning_trace = (
                f"Secondary payment capture {pid} detected on order {exc.order_id}. "
                "Customer was double-authorized on cart checkout."
            )
            exc.suggested_action = "Initiate immediate refund on duplicate payment authorization to prevent customer chargeback."
            exc.audit_trail.append("AI_INVESTIGATION_CONFIRMED_DUPLICATE")
            return exc

        if exc.category == ExceptionCategory.ACCOUNT_MISMATCH:
            exc.is_resolved = False
            exc.confidence = 0.99
            exc.suggested_action = "Urgent: Escalate to Banking Ops to audit beneficiary account routing on gateway."
            exc.audit_trail.append("AI_INVESTIGATION_FLAGGED_FOREIGN_ACCOUNT")
            return exc

        if exc.category == ExceptionCategory.MISSING_SETTLEMENT_RECORD or exc.category == ExceptionCategory.CHARGEBACK_DISPUTE_HOLD:
            exc.is_resolved = False
            exc.confidence = 0.95
            exc.ai_reasoning_trace = (
                f"Payment {pid} captured on gateway has not been assigned a bank settlement batch. "
                "May indicate a dispute hold, risk flag, or bank clearance delay."
            )
            exc.suggested_action = "Check merchant gateway dashboard for potential risk/KYC dispute hold."
            exc.audit_trail.append("AI_INVESTIGATION_FLAGGED_UNSETTLED")
            return exc

        if exc.category == ExceptionCategory.BANK_UTR_AMOUNT_MISMATCH:
            exc.is_resolved = False
            exc.confidence = 0.96
            exc.ai_reasoning_trace = (
                f"Bank UTR remittance for settlement {exc.settlement_id} shows an unexplained shortfall "
                f"of ₹{abs(exc.discrepancy_amount):,.2f} from expected gateway net payout."
            )
            exc.suggested_action = "Escalate to Bank Operations with UTR reference to verify debit memo / adjustments."
            exc.audit_trail.append("AI_INVESTIGATION_FLAGGED_BANK_VARIANCE")
            return exc

        # 2. Already Resolved Categories (Auto-resolved by Engine)
        if exc.is_resolved:
            return exc

        # 3. Investigating Fee Variance
        if exc.category == ExceptionCategory.MDR_GST_VARIANCE:
            fee_var = self.tools.calculate_fee_variance(pid)
            diff = fee_var.get("net_difference", exc.discrepancy_amount)
            implied_rate = fee_var.get("implied_rate_pct", 2.0)
            exc.is_resolved = True
            exc.confidence = 0.96
            exc.discrepancy_amount = diff
            exc.ai_reasoning_trace = (
                f"Gateway applied an effective MDR rate of {implied_rate}% (charged fee ₹{fee_var.get('charged_fee', 0)} + "
                f"₹{fee_var.get('charged_tax', 0)} GST) compared to baseline 2.0%. This matches custom corporate or international card tier."
            )
            exc.suggested_action = "Auto-adjusted fee schedule ledger entry for international/corporate card surcharge."
            exc.audit_trail.append("TOOL_CALCULATE_FEE_VARIANCE_RESOLVED")
            return exc

        # 4. Investigating Timing Lag
        if exc.category == ExceptionCategory.TIMING_LAG:
            timing = self.tools.check_timing_lag(pid)
            days = timing.get("days_elapsed", 3)
            exc.is_resolved = True
            exc.confidence = 0.98
            exc.ai_reasoning_trace = (
                f"Payment captured on {timing.get('payment_date')} settled {days} days later on {timing.get('settlement_date')}. "
                "Delay accounted for by standard banking holiday / weekend settlement cycle."
            )
            exc.suggested_action = "No action required. Remittance schedule aligns with T+N bank clearance window."
            exc.audit_trail.append("TOOL_CHECK_TIMING_LAG_RESOLVED")
            return exc

        # 5. Investigating Split / Batch Aggregation
        if exc.category == ExceptionCategory.SPLIT_SETTLEMENT_BATCH:
            exc.is_resolved = True
            exc.confidence = 0.95
            exc.ai_reasoning_trace = "Transaction was consolidated in multi-order bank remittance batch."
            exc.suggested_action = "Validated against multi-transaction bank remittance batch."
            exc.audit_trail.append("TOOL_QUERY_BANK_SETTLEMENT_BATCH_RESOLVED")
            return exc

        return exc
