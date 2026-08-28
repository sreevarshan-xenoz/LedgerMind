import pytest
from backend.core.chaos_generator import ChaosFinancialGenerator
from backend.core.holdout_generator import IndependentHoldoutGenerator
from backend.core.holdout_evaluator import HoldoutEvaluator


def test_exact_10k_holdout_accounting():
    gen = IndependentHoldoutGenerator(seed=4242)
    batch, truth = gen.generate_holdout_10k(
        clean_count=6500,
        known_anomalies_count=1500,
        edge_cases_count=1000,
        novel_combos_count=1000
    )

    assert len(batch.payments) == 10000
    assert len(truth.truth_records) == 10000


def test_chaos_generator_safe_failure():
    gen = ChaosFinancialGenerator(seed=7777)
    batch, truth = gen.generate_chaos_batch(count=500)

    assert len(batch.payments) == 500
    assert len(truth.truth_records) == 500

    evaluator = HoldoutEvaluator()
    res = evaluator.evaluate_holdout(batch, truth)

    # Invariant: Under heavy corruption, zero false reconciliations and zero false resolutions
    assert res["reconciliation"]["false_reconciliations"] == 0
    assert res["agent"]["false_resolutions_count"] == 0
    assert res["agent"]["escalated_count"] > 0
