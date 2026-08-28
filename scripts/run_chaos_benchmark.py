import os
import sys
import json
import argparse

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.chaos_generator import ChaosFinancialGenerator
from backend.core.holdout_evaluator import HoldoutEvaluator


def main():
    parser = argparse.ArgumentParser(description="LedgerMind Chaos / Noisy Dataset Benchmark (Safe Failure Mode)")
    parser.add_argument("--records", type=int, default=2000, help="Total chaos records")
    parser.add_argument("--seed", type=int, default=7777, help="Random seed")
    args = parser.parse_args()

    print("\n" + "="*75)
    print(" 🌪️ LEDGERMIND CHAOS & NOISY BENCHMARK (SAFE FAILURE MODE EVALUATION)")
    print("="*75)
    print(f" Injected Financial Corruptions:")
    print(f"   • Missing fee & GST records in gateway payloads")
    print(f"   • Null / missing UTR settlement statements")
    print(f"   • Uncontracted non-standard fee surcharges (e.g. 5.73% MDR)")
    print(f"   • Timezone clock skews (IST vs UTC vs naive)")
    print(f"   • Ghost / abandoned authorization captures")
    print(f"   • Unbacked bank balance deductions (₹770 unexplained shortfalls)")
    print("-" * 75)

    print(f"\nGenerating {args.records:,} noisy & corrupted financial records...")
    gen = ChaosFinancialGenerator(seed=args.seed)
    batch, ground_truth = gen.generate_chaos_batch(count=args.records)

    evaluator = HoldoutEvaluator()
    res = evaluator.evaluate_holdout(batch, ground_truth)

    cm = res["confusion_matrix"]
    rec = res["reconciliation"]
    agt = res["agent"]
    cal = res["confidence_calibration"]
    perf = res["performance"]

    print("\n" + "="*75)
    print("                    CHAOS EVALUATION RESULTS")
    print("="*75)
    print(f" Corrupt Records Ingested:      {res['records_processed']:,}")

    print("\n 2x2 CONFUSION MATRIX UNDER CORRUPTION")
    print(" -------------------------------------------------------------")
    print(f"                      Predicted Match    Predicted Exception")
    print(f"  Actual Match        TP: {cm['TP_true_matches']:<14} FN: {cm['FN_false_exceptions']}")
    print(f"  Actual Exception    FP: {cm['FP_false_matches']:<14} TN: {cm['TN_true_exceptions']}")

    print("\n SAFE DEGRADATION METRICS")
    print(" -------------------------------------------------------------")
    print(f" Reconciliation Accuracy:       {rec['accuracy_pct']:.2f}%")
    print(f" Precision:                     {rec['precision_pct']:.2f}%")
    print(f" Recall:                        {rec['recall_pct']:.2f}%")
    print(f" False Reconciliations:         {rec['false_reconciliations']}  (CRITICAL ZERO INVARIANT)")

    print("\n AGENT ESCALATION SAFETY")
    print(" -------------------------------------------------------------")
    print(f" Safely Escalated to Human:     {agt['escalated_count']:,} cases (Incomplete evidence trapped)")
    print(f" Escalation Precision:          {agt['escalation_precision_pct']:.2f}%")
    print(f" Auto-Resolved (Valid Proofs):  {agt['auto_resolved_count']:,} cases")
    print(f" False Resolutions:             {agt['false_resolutions_count']}  (SAFETY INVARIANT: 0.00%)")

    print("\n PERFORMANCE & THROUGHPUT")
    print(" -------------------------------------------------------------")
    print(f" Processing Latency:            {perf['elapsed_ms']:.2f} ms")
    print(f" Throughput:                    {perf['throughput_records_per_sec']:,.2f} records/sec")
    print("="*75)

    # Save artifact
    results_dir = os.path.join(os.path.dirname(__file__), "..", "backend", "benchmarks", "results")
    os.makedirs(results_dir, exist_ok=True)
    out_path = os.path.join(results_dir, "chaos_benchmark_result.json")
    with open(out_path, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\n✅ Chaos evaluation saved to: {out_path}\n")


if __name__ == "__main__":
    main()
