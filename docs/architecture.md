# 🏛️ LedgerMind Architecture Specification

> **Razorpay Buildathon Track 04: AI Finance-Ops Agent**  
> Multi-Source Financial Reconciliation & Evidence-Backed AI Investigator.

---

## 1. Core Architectural Philosophy

Financial systems demand **deterministic precision, auditability, and safety**. An LLM should never directly balance a ledger or compute debit/credit payouts.

LedgerMind enforces an explicit **three-tier boundary**:

```
UNTRUSTED INCOMING DATA (Webhooks, ERP Feeds, Customer Notes, Bank Statements)
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    TIER 1: FINANCIAL CORE (Deterministic)               │
│  • Relational Foreign-Key Graph Matcher                                 │
│  • Cryptographic HMAC-SHA256 Signature Verification                     │
│  • Temporal Lifecycle & Multi-UTR Split Remittance Aggregator           │
│  • Strictly Invariant: 0 False Matches                                  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                             Structured Evidence
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                TIER 2: EVIDENCE-BACKED DECISION ENGINE                  │
│  • Tool-Augmented Hypothesis Testing State Machine                      │
│  • Mathematical Variance Verification (MDR %, GST, Refunds)             │
│  • Safe Failure Protocol: Incomplete Evidence ➔ Human Review Queue      │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                             Verified Facts
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  TIER 3: AI AGENT (Explainer & Merchant Q&A)            │
│  • Natural Language Query Planning (`find_settlement`, `compare_math`)  │
│  • Itemized Line-Item Breakdown Generation                              │
│  • Merchant Guidance with Citation Anchoring                            │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                 TIER 4: POLICY & HUMAN-IN-THE-LOOP (HITL)               │
│  • Operator Action Queue (`[Approve]`, `[Escalate to Banking Ops]`)     │
│  • Tamper-Evident Audit Logging                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Invariant Rules of the Financial Core

1. **Strict Relational Path Matching**:
   Transactions are matched strictly through verifiable relational foreign keys: `Order.order_id ↔ Payment.order_id` and `Payment.settlement_id / settlement_ids ↔ Settlement.settlement_id`. Cross-order amount matching without relational graph paths is forbidden.

2. **Temporal Lifecycle Invariants**:
   - Pre-Settlement Refund (`refund.created_at <= settlement.settlement_date`): Deducted from gross settlement net.
   - Post-Settlement Refund (`refund.created_at > settlement.settlement_date`): Initial settlement is matched gross; refund is queued as a `POST_SETTLEMENT_REFUND_DEFERRED` debit in the subsequent cycle.

3. **Multi-UTR Split Remittance Aggregation**:
   When gateway payouts are partitioned across $N$ bank UTRs, the engine evaluates:
   $$\text{Gross} - \text{MDR Fee} - \text{GST} = \sum_{i=1}^N \text{NetPayout}(\text{UTR}_i)$$

4. **Zero False Resolution Guarantee**:
   The Decision Engine cannot auto-resolve an anomaly unless mathematical proof is established across payment, settlement, fee, and refund records. If any evidence record is missing or contradictory, confidence drops and the record is escalated to the Human Queue.
