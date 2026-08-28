from typing import Dict, List, Any, Tuple
from .models import SyntheticBatch, MatchedRecord, ExceptionItem
from .reconciler import DeterministicReconciliationEngine
from ..agent.decision_layer import AgentDecisionLayer, AgentDecisionOutput
from .holdout_generator import HoldoutGroundTruth


class HoldoutEvaluator:
    """
    Independent Holdout Evaluation Harness.
    Measures reconciliation precision/recall, agent resolution/escalation precision/recall,
    explicit 2x2 confusion matrices, zero false resolution invariant, and confidence calibration.
    """

    def __init__(self, primary_account: str = "XXXX-XXXX-9921"):
        self.primary_account = primary_account

    def evaluate_holdout(
        self,
        batch: SyntheticBatch,
        ground_truth: HoldoutGroundTruth
    ) -> Dict[str, Any]:
        engine = DeterministicReconciliationEngine(primary_merchant_account=self.primary_account)
        agent = AgentDecisionLayer(batch)

        matched_records, exceptions, meta = engine.reconcile(batch)

        matched_payment_ids = {m.payment_id for m in matched_records}

        exception_decisions: Dict[str, AgentDecisionOutput] = {}
        for exc in exceptions:
            dec = agent.evaluate_exception(exc)
            exception_decisions[exc.record_id] = dec

        tp_reconciliation = 0  # Actual Match & Predicted Match
        fp_reconciliation = 0  # Actual Exception & Predicted Match (CRITICAL ZERO)
        fn_reconciliation = 0  # Actual Match & Predicted Exception
        tn_reconciliation = 0  # Actual Exception & Predicted Exception

        true_resolutions = 0
        false_resolutions = 0
        true_escalations = 0
        false_escalations = 0

        calibration_bins = {
            "90-100%": {"total": 0, "correct": 0},
            "80-90%": {"total": 0, "correct": 0},
            "70-80%": {"total": 0, "correct": 0},
            "<70%": {"total": 0, "correct": 0}
        }

        for pid, truth in ground_truth.truth_records.items():
            exp_class = truth["expected_classification"]

            # Ground truth classification
            is_actual_match = (exp_class in ["CLEAN_MATCH", "RESOLVABLE_EXCEPTION"])
            is_predicted_match = (pid in matched_payment_ids)

            if is_actual_match and is_predicted_match:
                tp_reconciliation += 1
            elif not is_actual_match and is_predicted_match:
                fp_reconciliation += 1
            elif is_actual_match and not is_predicted_match:
                fn_reconciliation += 1
            elif not is_actual_match and not is_predicted_match:
                tn_reconciliation += 1

            # Agent Decision Evaluation
            if exp_class in ["RESOLVABLE_EXCEPTION", "UNRESOLVABLE_ESCALATION"]:
                dec = exception_decisions.get(pid)
                if dec:
                    conf = dec.confidence
                    bin_key = "90-100%" if conf >= 0.90 else ("80-90%" if conf >= 0.80 else ("70-80%" if conf >= 0.70 else "<70%"))
                    calibration_bins[bin_key]["total"] += 1

                    if dec.decision == "RESOLVE":
                        if exp_class == "RESOLVABLE_EXCEPTION":
                            true_resolutions += 1
                            calibration_bins[bin_key]["correct"] += 1
                        else:
                            # CRITICAL SAFETY VIOLATION: Auto-resolved an unresolvable exception!
                            false_resolutions += 1

                    elif dec.decision == "ESCALATE":
                        if exp_class == "UNRESOLVABLE_ESCALATION":
                            true_escalations += 1
                            calibration_bins[bin_key]["correct"] += 1
                        else:
                            false_escalations += 1

        total_actual_matches = tp_reconciliation + fn_reconciliation
        total_actual_exceptions = fp_reconciliation + tn_reconciliation

        precision = (tp_reconciliation / (tp_reconciliation + fp_reconciliation) * 100.0) if (tp_reconciliation + fp_reconciliation) > 0 else 100.0
        recall = (tp_reconciliation / total_actual_matches * 100.0) if total_actual_matches > 0 else 100.0
        f1_score = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        accuracy = ((tp_reconciliation + tn_reconciliation) / len(ground_truth.truth_records) * 100.0) if ground_truth.truth_records else 100.0

        total_resolutions_attempted = true_resolutions + false_resolutions
        res_precision = (true_resolutions / total_resolutions_attempted * 100.0) if total_resolutions_attempted else 100.0

        total_escalations_attempted = true_escalations + false_escalations
        esc_precision = (true_escalations / total_escalations_attempted * 100.0) if total_escalations_attempted else 100.0

        calibration_results = {}
        for b_name, b_data in calibration_bins.items():
            if b_data["total"] > 0:
                acc = round((b_data["correct"] / b_data["total"]) * 100.0, 1)
                calibration_results[b_name] = {
                    "total_predictions": b_data["total"],
                    "correct_predictions": b_data["correct"],
                    "empirical_accuracy_pct": acc
                }
            else:
                calibration_results[b_name] = {"total_predictions": 0, "correct_predictions": 0, "empirical_accuracy_pct": 100.0}

        return {
            "records_processed": len(ground_truth.truth_records),
            "confusion_matrix": {
                "TP_true_matches": tp_reconciliation,
                "FP_false_matches": fp_reconciliation,
                "FN_false_exceptions": fn_reconciliation,
                "TN_true_exceptions": tn_reconciliation
            },
            "reconciliation": {
                "clean_matches": tp_reconciliation,
                "false_reconciliations": fp_reconciliation,
                "accuracy_pct": round(accuracy, 2),
                "precision_pct": round(precision, 2),
                "recall_pct": round(recall, 2),
                "f1_score": round(f1_score, 2)
            },
            "agent": {
                "auto_resolved_count": true_resolutions,
                "false_resolutions_count": false_resolutions,
                "resolution_precision_pct": round(res_precision, 2),
                "escalated_count": true_escalations,
                "false_escalations_count": false_escalations,
                "escalation_precision_pct": round(esc_precision, 2),
                "false_resolution_rate_pct": round(false_resolutions / total_resolutions_attempted * 100.0, 4) if total_resolutions_attempted else 0.0
            },
            "confidence_calibration": calibration_results,
            "performance": {
                "elapsed_ms": round(meta["elapsed_ms"], 2),
                "throughput_records_per_sec": round(len(ground_truth.truth_records) / (meta["elapsed_ms"] / 1000.0), 2) if meta["elapsed_ms"] > 0 else 0.0
            }
        }
