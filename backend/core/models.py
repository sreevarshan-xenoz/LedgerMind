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
    SPLIT_SETTLEMENT_BATCH = "SPLIT_SETTLEMENT_BATCH"
    
    # Honest Unresolved categories
    ORPHAN_PAYMENT = "ORPHAN_PAYMENT"
    BANK_UTR_AMOUNT_MISMATCH = "BANK_UTR_AMOUNT_MISMATCH"
    CHARGEBACK_DISPUTE_HOLD = "CHARGEBACK_DISPUTE_HOLD"
    DUPLICATE_AUTH_CAPTURE = "DUPLICATE_AUTH_CAPTURE"
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
    auth_code: Optional[str] = None
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
    gross_amount: float
    fee: float
    tax: float
    net_settled: float
    match_type: str = "3_WAY_EXACT"  # 3_WAY_EXACT, 2_WAY_SETTLED, AI_RESOLVED_TIMING, etc.
    matched_at: str


class ReconciliationMetrics(BaseModel):
    total_records_ingested: int
    matched_count: int
    deterministic_matches: int
    ai_investigated_count: int
    ai_resolved_count: int
    honest_unresolved_count: int
    match_rate_pct: float
    match_accuracy_pct: float
    throughput_records_per_sec: float
    processing_time_ms: float
    total_gmv: float
    total_settled_net: float
    total_fees_verified: float
    total_tax_verified: float
    unreconciled_discrepancy_amount: float


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
