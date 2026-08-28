# 🧠 LedgerMind

> **Razorpay Buildathon Track 04 Submission: AI Finance-Ops Agent**  
> Multi-Source Financial Reconciliation, Evidence-Backed Exception Investigator, and Merchant Control Center.

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Python 3.12](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org)
[![Pytest](https://img.shields.io/badge/Tests-26%2F26%20Passing-brightgreen.svg)](https://docs.pytest.org)
[![Throughput](https://img.shields.io/badge/Throughput-59%2C000%2B%20rec%2Fsec-orange.svg)]()
[![Safety](https://img.shields.io/badge/False%20Resolutions-0.00%25-success.svg)]()

---

## 🎯 Executive Summary

| Question | LedgerMind Answer |
|---|---|
| **What is it?** | A production-grade Autonomous Finance-Ops Controller and Multi-Source Reconciliation Agent. |
| **Why build it?** | Financial reconciliation across Razorpay, Bank UTRs, and ERPs is fragmented. Variances in custom MDR tiers, post-settlement refunds, and split remittances overwhelm finance teams. |
| **How does it work?** | **Strict 3-Tier Architecture**: A high-speed deterministic core (59,000+ rec/sec) matches clean records, an **Agentic Investigation Orchestrator** explores discrepancies with dynamic tool planning, and an **AI Assistant** synthesizes itemized deduction tables. |
| **What is the proof?** | Evaluated across **60,000 records across 5 independent random seeds** on holdout and chaos datasets. |
| **What is the safety guarantee?** | **0 False Reconciliations and 0 False Resolutions**. The LLM cannot alter financial truth. Insufficient evidence strictly degrades confidence and routes to the **Human Review Queue**. |
| **How to demo?** | One-command startup with live interactive Merchant Control Center and 8-step live incident playback simulator. |

---

## 🏛️ System Architecture

```
UNTRUSTED INCOMING DATA (Razorpay Webhooks, ERP Orders, Bank Statements, CSVs)
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    TIER 1: FINANCIAL CORE (Deterministic)               │
│  • Relational Foreign-Key Graph Matcher                                 │
│  • Cryptographic HMAC-SHA256 Signature Verification                     │
│  • Temporal Lifecycle Invariants & Multi-UTR Split Aggregation          │
│  • Strictly Invariant: 0 False Reconciliations                          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                             Structured Evidence
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              TIER 2: AGENTIC INVESTIGATION ORCHESTRATOR                 │
│  • Autonomous Tool-Calling Query Planner (inspect_payment, inspect_utr) │
│  • Mathematical Proof Formulas (Gross - MDR - GST - Refunds = Net)      │
│  • Safe Failure Protocol: Incomplete Evidence ➔ Human Review Queue      │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                             Verified Facts
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  TIER 3: AI AGENT (Explainer & Merchant Q&A)            │
│  • Natural Language Query Planning (`find_settlement`, `compare_math`)  │
│  • Itemized Line-Item Deduction Tables                                  │
│  • Natural Language Explanations Citing Verifiable Records              │
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

## 📊 Benchmark Evaluation Results

### 1. Multi-Seed Stability Benchmark (60,000 Records Across 5 Seeds)
```text
=====================================================================================
 🧪 LEDGERMIND MULTI-SEED STABILITY & ZERO-FALSE-RESOLUTION AUDIT
=====================================================================================
 PART 1: 10,000-Record Independent Holdout Across 5 Seeds
 Seed     | Records  | TP Match   | TN Excs    | FP False   | False Res  | Throughput
 123      | 10,000   | 8505       | 1495       | 0          | 0          |  55,121 /s
 456      | 10,000   | 8492       | 1508       | 0          | 0          |  91,789 /s
 789      | 10,000   | 8554       | 1446       | 0          | 0          |  92,001 /s
 1337     | 10,000   | 8504       | 1496       | 0          | 0          |  61,548 /s
 2026     | 10,000   | 8505       | 1495       | 0          | 0          |  57,325 /s

 PART 2: 2,000-Record Chaos & Corruption Across 5 Seeds
 Seed     | Records  | TP Match   | TN Excs    | FP False   | False Res  | Trapped Human
 123      | 2,000    | 855        | 1145       | 0          | 0          | 1145 cases
 456      | 2,000    | 863        | 1137       | 0          | 0          | 1137 cases
 789      | 2,000    | 859        | 1141       | 0          | 0          | 1141 cases
 1337     | 2,000    | 874        | 1126       | 0          | 0          | 1126 cases
 2026     | 2,000    | 880        | 1120       | 0          | 0          | 1120 cases
=====================================================================================
 Total Batches Evaluated: 10 (60,000 records) • Cumulative False Resolutions: 0 (0.00%)
```

### 2. Hostile Security Benchmark (7 Defended Vectors)
```text
  ✅ Attack A: Entity Collision (Same Amount, Wrong Order)  ➔ DEFENDED (0 False Matches)
  ✅ Attack B: Missing Evidence (Unbacked Shortfall)         ➔ DEFENDED (Escalated to Human)
  ✅ Attack C: Contradictory Timing (Post-Settlement Debit) ➔ DEFENDED (Deferred Ledger)
  ✅ Attack D: 100x Replay Attack on Webhooks               ➔ DEFENDED (1 Processed / 99 Dropped)
  ✅ Attack E: Out-of-Order Event Stream Ingestion          ➔ DEFENDED (Deterministic Convergence)
  ✅ Attack F: Prompt Injection via Untrusted Notes         ➔ DEFENDED (0 Tampered Records)
  ✅ Attack G: Arbitrary Fee Rate Manipulation (20% MDR)     ➔ DEFENDED (Variance Flagged)
```

---

## 🚀 Quick Start (1-Minute Setup)

### 1. Prerequisites & Installation
```bash
git clone https://github.com/your-username/LedgerMind.git
cd LedgerMind
pip install -r requirements.txt
cp .env.example .env
```

### 2. Run Test Suites & Multi-Seed Benchmarks
```bash
# Run all 26 automated unit and adversarial tests
python -m pytest tests/

# Run the 60,000-record multi-seed stability audit across 5 seeds
python scripts/run_multiseed_audit.py

# Run the 7-attack hostile security benchmark
python scripts/run_hostile_security_benchmark.py

# Run the agentic tool quality benchmark
python scripts/run_agentic_investigation_benchmark.py --records 500
```

### 3. Launch Merchant Control Center & API
```bash
python -m uvicorn backend.api.server:app --host 127.0.0.1 --port 8000
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## 🖥️ Live Demonstration Highlights

1. **Live Incident Playback**: Click **`▶ Run Live Incident Demo`** on the dashboard to watch an 8-step live animated incident pipeline from payment capture to human escalation.
2. **Investigation Console**: Inspect the visual 4-node lineage graph (`Order ➔ Payment ➔ Settlement ➔ Refund`), hypothesis math proof, and clickable evidence inspector.
3. **Settlement Q&A Agent**: Ask *"Why did I receive ₹18,430 instead of ₹19,200?"* to see real-time line-item itemized math breakdowns (`Gross - MDR - GST - Adjustments = Net`).
4. **Human Review Queue**: Execute **`[Approve Resolution]`** or **`[Escalate to Banking Ops]`** with structured tamper-evident audit logging.

---

## 📁 Repository Structure

```
LedgerMind/
├── backend/
│   ├── core/                  # Deterministic 3-way matcher, models, holdout & chaos generators
│   │   ├── reconciler.py
│   │   ├── holdout_generator.py
│   │   ├── chaos_generator.py
│   │   ├── holdout_evaluator.py
│   │   └── live_store.py
│   ├── agent/                 # Agentic orchestrator, providers, and Settlement Q&A
│   │   ├── orchestrator.py
│   │   ├── providers.py
│   │   ├── settlement_qa.py
│   │   └── tools.py
│   ├── integrations/          # Razorpay Test Mode client & signed HMAC webhooks
│   │   └── razorpay/
│   │       ├── client.py
│   │       ├── payments.py
│   │       ├── settlements.py
│   │       ├── refunds.py
│   │       └── webhooks.py
│   ├── api/                   # FastAPI server & static Merchant Control Center
│   │   ├── server.py
│   │   └── static/index.html
│   └── benchmarks/            # Versioned baselines & raw JSON benchmark artifacts
│       ├── baselines/
│       └── results/
├── docs/                      # Technical specifications & pitch documentation
│   ├── architecture.md
│   ├── security_and_hostile_eval.md
│   ├── evaluation_methodology.md
│   ├── reproducibility.md
│   ├── judge_defense_faq.md
│   └── demo_script.md
├── scripts/                   # CLI benchmark runners & audit suites
│   ├── run_multiseed_audit.py
│   ├── run_holdout_benchmark.py
│   ├── run_chaos_benchmark.py
│   ├── run_hostile_security_benchmark.py
│   └── run_agentic_investigation_benchmark.py
├── tests/                     # 26 automated pytest test suites
│   ├── test_reconciliation.py
│   ├── test_adversarial.py
│   ├── test_razorpay_integration.py
│   ├── test_holdout_evaluation.py
│   ├── test_chaos_evaluation.py
│   ├── test_hostile_security.py
│   └── test_agentic_orchestrator.py
├── .env.example
├── requirements.txt
└── README.md
```

---

## 📄 License
MIT License. Developed for Razorpay Buildathon 2026 (Track 04).
