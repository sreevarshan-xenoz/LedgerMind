# 🔬 LedgerMind Reproducibility Specification

> **Step-by-Step Instructions to Reproduce All Benchmarks and Tests Independently**

---

## 1. System Requirements & Environment

- **Python**: `3.11+` (Evaluated on Python `3.12.10`)
- **OS**: Cross-platform (Windows / Linux / macOS)
- **FastAPI / Uvicorn**: `0.115+` / `0.30+`
- **Pytest**: `8.3+`
- **Network / External Dependencies**: None required for core evaluation. Runs 100% offline with zero external network dependencies. Optional Razorpay API credentials enable live gateway ingestion.

---

## 2. Quick Setup

```bash
# Clone repository
git clone https://github.com/your-username/LedgerMind.git
cd LedgerMind

# Install dependencies
pip install -r requirements.txt

# Setup environment variables
cp .env.example .env
```

---

## 3. Benchmark Execution Commands & Expected Outputs

### A. Full Automated Test Suite (26 Unit Tests)
```bash
python -m pytest tests/
```
**Expected Output**:
```text
============================= 26 passed in 0.64s ==============================
```

---

### B. Independent 10,000-Record Holdout Evaluation (Unseen)
```bash
python scripts/run_holdout_benchmark.py --records 10000 --seed 2026
```
**Expected Output**:
```text
Exact Records Evaluated:       10,000 / 10,000

2x2 RECONCILIATION CONFUSION MATRIX
-------------------------------------------------------------
                      Predicted Match    Predicted Exception
  Actual Match        TP: 8488           FN: 0
  Actual Exception    FP: 0              TN: 1512

Metrics:
  • False Reconciliations:     0 (CRITICAL ZERO INVARIANT)
  • False Resolutions:         0 (SAFETY ZERO INVARIANT: 0.00%)
  • Throughput:                ~59,000+ records/sec
```

---

### C. 2,000-Record Chaos & Corruption Evaluation (Safe Degradation)
```bash
python scripts/run_chaos_benchmark.py --records 2000 --seed 9999
```
**Expected Output**:
```text
Corrupt Records Ingested:      2,000

2x2 CONFUSION MATRIX UNDER CORRUPTION
-------------------------------------------------------------
                      Predicted Match    Predicted Exception
  Actual Match        TP: 893            FN: 0
  Actual Exception    FP: 0              TN: 1107

Metrics:
  • False Reconciliations:     0 (CRITICAL ZERO INVARIANT)
  • Safely Escalated Cases:    1,107 (Incomplete evidence trapped)
  • False Resolutions:         0 (SAFETY ZERO INVARIANT: 0.00%)
```

---

### D. Hostile Security Benchmark (7 Attack Vectors)
```bash
python scripts/run_hostile_security_benchmark.py
```
**Expected Output**:
```text
  ✅ Attack A (Entity Collision)              ➔ DEFENDED
  ✅ Attack B (Missing Evidence)              ➔ DEFENDED
  ✅ Attack C (Contradictory Timing)          ➔ DEFENDED
  ✅ Attack D (100x Replay Attack)            ➔ DEFENDED (1 Processed / 99 Dropped)
  ✅ Attack E (Out-of-Order Convergence)      ➔ DEFENDED
  ✅ Attack F (Prompt Injection Defense)      ➔ DEFENDED (0 Tampered Records)
  ✅ Attack G (Fee Rate Manipulation)         ➔ DEFENDED
```

---

### E. Agentic Tool Investigation Quality Benchmark
```bash
python scripts/run_agentic_investigation_benchmark.py --records 500
```
**Expected Output**:
```text
 Total Investigations Executed:     182
 Total Autonomous Tool Steps:       1,092 (Avg 6.0 steps/case)
 Correct Tool Selection Rate:       100.00% (Target: >95%)
 Unauthorized Tool Violations:      0 (Target: 0)
 Iteration Limit Enforcement:       100.00% (Strict Max 6 steps)
 False Resolutions:                 0 (CRITICAL SAFETY ZERO: 0.00%)
```

---

## 4. Live Server & Demonstration Startup

```bash
# Start FastAPI and Merchant Control Center UI
python -m uvicorn backend.api.server:app --host 127.0.0.1 --port 8000
```
Navigate to: **`http://localhost:8000`** in your browser.
