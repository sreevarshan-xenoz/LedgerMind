from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    CREATED = "created"
    PAID = "paid"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentStatus(str, Enum):
    CAPTURED = "captured"
    AUTHORIZED = "authorized"
    FAILED = "failed"
    REFUNDED = "refunded"


class SettlementStatus(str, Enum):
    PROCESSED = "processed"
    SETTLED = "settled"
    FAILED = "failed"


class RefundStatus(str, Enum):
    PROCESSED = "processed"
    PENDING = "pending"
    FAILED = "failed"


class ExceptionCategory(str, Enum):
    # Auto-resolved categories
    TIMING_LAG = "TIMING_LAG"
    MDR_GST_VARIANCE = "MDR_GST_VARIANCE"
    PARTIAL_REFUND_NETTED = "PARTIAL_REFUND_NETTED"
    POST_SETTLEMENT_REFUND_DEFERRED = "POST_SETTLEMENT_REFUND_DEFERRED"
    SPLIT_SETTLEMENT_BATCH = "SPLIT_SETTLEMENT_BATCH"
    SPLIT_MULTI_UTR_SETTLED = "SPLIT_MULTI_UTR_SETTLED"
    
    # Honest Unresolved categories
    ORPHAN_PAYMENT = "ORPHAN_PAYMENT"
    BANK_UTR_AMOUNT_MISMATCH = "BANK_UTR_AMOUNT_MISMATCH"
    CHARGEBACK_DISPUTE_HOLD = "CHARGEBACK_DISPUTE_HOLD"
    DUPLICATE_AUTH_CAPTURE = "DUPLICATE_AUTH_CAPTURE"
    AMOUNT_COLLISION_CROSS_ORDER = "AMOUNT_COLLISION_CROSS_ORDER"
    ACCOUNT_MISMATCH = "ACCOUNT_MISMATCH"
    MISSING_SETTLEMENT_RECORD = "MISSING_SETTLEMENT_RECORD"
    UNKNOWN_DISCREPANCY = "UNKNOWN_DISCREPANCY"


class Order(BaseModel):
    order_id: str
    amount: float
    currency: str = "INR"
    status: OrderStatus
    customer_id: str
    created_at: str


class Payment(BaseModel):
    payment_id: str
    order_id: Optional[str] = None
    amount: float
    fee: float = 0.0
    tax: float = 0.0
    net_amount: float = 0.0
    status: PaymentStatus
    method: str = "card"  # card, upi, netbanking, wallet
    settlement_id: Optional[str] = None
    settlement_ids: Optional[List[str]] = None  # for split settlements across multi-UTRs
    auth_code: Optional[str] = None
    account_number: Optional[str] = None
    created_at: str


class Settlement(BaseModel):
    settlement_id: str
    utr: str
    gross_amount: float
    total_fee: float = 0.0
    total_tax: float = 0.0
    net_payout: float
    settlement_date: str
    account_number: str
    payment_ids: Optional[List[str]] = None
    status: SettlementStatus = SettlementStatus.SETTLED


class Refund(BaseModel):
    refund_id: str
    payment_id: str
    amount: float
    reason: str = "customer_request"
    status: RefundStatus = RefundStatus.PROCESSED
    created_at: str


class GroundTruthMetadata(BaseModel):
    is_anomaly: bool = False
    anomaly_type: Optional[str] = None
    expected_match_status: str = "MATCHED"  # MATCHED, AUTO_RESOLVED, UNRESOLVED
    expected_discrepancy: float = 0.0
    explanation: Optional[str] = None


class SyntheticBatch(BaseModel):
    batch_id: str
    orders: List[Order]
    payments: List[Payment]
    settlements: List[Settlement]
    refunds: List[Refund]
    ground_truth: Dict[str, GroundTruthMetadata] = Field(default_factory=dict)


class ExceptionItem(BaseModel):
    exception_id: str
    record_id: str  # payment_id or order_id
    order_id: Optional[str] = None
    payment_id: Optional[str] = None
    settlement_id: Optional[str] = None
    settlement_utr: Optional[str] = None
    expected_amount: float
    actual_amount: float
    discrepancy_amount: float
    category: ExceptionCategory
    is_resolved: bool = False
    confidence: float = 0.0
    ai_reasoning_trace: str = ""
    suggested_action: str = ""
    audit_trail: List[str] = Field(default_factory=list)


class MatchedRecord(BaseModel):
    match_id: str
    order_id: str
    payment_id: str
    settlement_id: Optional[str] = None
    settlement_utrs: List[str] = Field(default_factory=list)
    gross_amount: float
    fee: float
    tax: float
    net_settled: float
    match_type: str = "3_WAY_EXACT"  # 3_WAY_EXACT, 3_WAY_SPLIT_UTR, AI_RESOLVED_TIMING, etc.
    matched_at: str


class ReconciliationMetrics(BaseModel):
    total_records_ingested: int
    true_reconciliations: int
    false_reconciliations: int = 0
    exceptions_detected: int
    exceptions_correctly_diagnosed: int
    honest_unresolved_count: int
    reconciliation_accuracy_pct: float
    exception_recall_pct: float
    exception_precision_pct: float
    ai_resolution_rate_pct: float
    throughput_records_per_sec: float
    processing_time_ms: float
    total_gmv: float
    total_settled_net: float
    total_fees_verified: float
    total_tax_verified: float
    unreconciled_discrepancy_amount: float

    # Aliases for backward compatibility in UI HUD
    @property
    def matched_count(self) -> int:
        return self.true_reconciliations

    @property
    def deterministic_matches(self) -> int:
        return self.true_reconciliations

    @property
    def ai_investigated_count(self) -> int:
        return self.exceptions_detected

    @property
    def ai_resolved_count(self) -> int:
        return self.exceptions_correctly_diagnosed

    @property
    def match_rate_pct(self) -> float:
        return round((self.true_reconciliations / self.total_records_ingested * 100.0), 2) if self.total_records_ingested > 0 else 0.0

    @property
    def match_accuracy_pct(self) -> float:
        return self.reconciliation_accuracy_pct


class ReconciliationResult(BaseModel):
    batch_id: str
    metrics: ReconciliationMetrics
    exception_breakdown: Dict[str, int]
    matched_records: List[MatchedRecord] = Field(default_factory=list)
    resolved_exceptions: List[ExceptionItem] = Field(default_factory=list)
    unresolved_exceptions: List[ExceptionItem] = Field(default_factory=list)


class SettlementQAQuery(BaseModel):
    query: str
    payment_id: Optional[str] = None
    order_id: Optional[str] = None
    settlement_id: Optional[str] = None
    batch_id: Optional[str] = None


class SettlementQAResponse(BaseModel):
    query: str
    matched_order_id: Optional[str] = None
    matched_payment_id: Optional[str] = None
    matched_settlement_id: Optional[str] = None
    order_amount: Optional[float] = None
    gateway_fee: Optional[float] = None
    gst_tax: Optional[float] = None
    net_payout: Optional[float] = None
    refund_deduction: Optional[float] = None
    unexplained_variance: Optional[float] = None
    status: str
    answer: str
    breakdown_table: Dict[str, Any] = Field(default_factory=dict)
    suggested_action: str
    confidence: float


class FinancialLineageNode(BaseModel):
    node_type: str  # "ORDER", "PAYMENT", "SETTLEMENT", "REFUNDS"
    entity_id: str
    status: str
    amount: float
    formatted_amount: str
    meta: str
    verified: bool
    source: str
    timestamp: Optional[str] = None


class FinancialStatement(BaseModel):
    gross_amount: float
    gateway_fee: float
    gst_tax: float
    refund_deductions: float
    expected_net: float
    actual_net: float
    residual_variance: float
    variance_pct: float
    formula_description: str


class EvidenceChecklistItem(BaseModel):
    name: str
    status: str  # "VERIFIED", "MISSING", "NOT_APPLICABLE"
    detail: str
    icon: str  # "✓", "○", "⚠"


class InvestigationContext(BaseModel):
    exception_id: str
    target_record: str
    payment_id: str
    order_id: Optional[str] = None
    settlement_id: Optional[str] = None
    category: str
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    lifecycle_stage: str = "HUMAN_REVIEW"  # "DETECTED", "INVESTIGATING", "RESOLVED", "HUMAN_REVIEW", "ESCALATED", "CLOSED"
    title: str
    subheading: str
    variance_summary: str
    variance_explanation: str
    financials: FinancialStatement
    lineage: List[FinancialLineageNode]
    evidence_checklist: List[EvidenceChecklistItem]
    agent_trace: Dict[str, Any]
    decision: Dict[str, Any]
    timeline: List[Dict[str, Any]] = Field(default_factory=list)


class AskLedgerMindRequest(BaseModel):
    query: str
    screen_context: str = "investigations"  # investigations, overview, settlements, exceptions, benchmarks, audit-log
    case_id: Optional[str] = None
    settlement_id: Optional[str] = None
    depth: str = "analyst"  # executive, analyst, technical
    history: List[Dict[str, Any]] = Field(default_factory=list)


class AskLedgerMindResponse(BaseModel):
    query: str
    intent: str
    depth: str
    direct_answer: str
    key_metrics: List[Dict[str, Any]] = Field(default_factory=list)
    visualization: Optional[Dict[str, Any]] = None
    explanation: str
    depth_variants: Dict[str, str] = Field(default_factory=dict)
    evidence_citations: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_summary: Dict[str, Any] = Field(default_factory=dict)
    recommended_actions: List[Dict[str, Any]] = Field(default_factory=list)
    conversation_context: Dict[str, Any] = Field(default_factory=dict)

