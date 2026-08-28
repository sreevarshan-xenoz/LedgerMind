import pytest
from backend.core.synthetic_generator import SyntheticFinancialGenerator
from backend.core.reconciler import DeterministicReconciliationEngine
from backend.core.benchmarking import BenchmarkEvaluator
from backend.agent.investigator import AIExceptionInvestigator
from backend.agent.settlement_qa import SettlementQAAgent
from backend.core.models import SettlementQAQuery


def test_synthetic_generation():
    gen = SyntheticFinancialGenerator(seed=42)
    batch = gen.generate_batch(batch_id="test_100", num_records=100, anomaly_rate=0.10)
    
    assert len(batch.payments) == 100
    assert len(batch.settlements) > 0
    assert len(batch.ground_truth) == 100


def test_deterministic_reconciliation():
    gen = SyntheticFinancialGenerator(seed=42)
    batch = gen.generate_batch(batch_id="test_500", num_records=500, anomaly_rate=0.08)
    
    engine = DeterministicReconciliationEngine()
    matched, exceptions, meta = engine.reconcile(batch)

    assert len(matched) > 400
    assert len(exceptions) > 0
    assert meta["total_gmv"] > 0
    assert meta["elapsed_ms"] < 200.0  # Must be fast (<200ms for 500 records)


def test_ai_investigator_triage():
    gen = SyntheticFinancialGenerator(seed=42)
    batch = gen.generate_batch(batch_id="test_200", num_records=200, anomaly_rate=0.10)
    
    engine = DeterministicReconciliationEngine()
    matched, exceptions, meta = engine.reconcile(batch)

    investigator = AIExceptionInvestigator(batch)
    resolved, unresolved = investigator.investigate_all(exceptions)

    assert len(resolved) + len(unresolved) == len(exceptions)
    assert len(unresolved) > 0  # Honest exceptions must be flagged!
    for unres in unresolved:
        assert unres.is_resolved is False
        assert len(unres.ai_reasoning_trace) > 0
        assert len(unres.suggested_action) > 0


def test_settlement_qa_agent():
    gen = SyntheticFinancialGenerator(seed=42)
    batch = gen.generate_batch(batch_id="test_qa", num_records=50, anomaly_rate=0.10)
    qa = SettlementQAAgent(batch)

    # Query with payment ID
    sample_pid = batch.payments[0].payment_id
    res = qa.answer_query(SettlementQAQuery(query=f"Why is payout different for {sample_pid}?"))

    assert res.matched_payment_id == sample_pid
    assert res.confidence > 0.90
    assert len(res.answer) > 0
    assert any("Gateway MDR Fee" in k for k in res.breakdown_table.keys())


def test_benchmark_accuracy():
    gen = SyntheticFinancialGenerator(seed=123)
    batch = gen.generate_batch(batch_id="bench_test", num_records=500, anomaly_rate=0.087)
    
    evaluator = BenchmarkEvaluator()
    results = evaluator.run_benchmark(batch)

    eval_data = results["evaluation"]
    assert eval_data["accuracy_pct"] >= 98.0
    assert eval_data["throughput_records_per_sec"] > 500.0
    assert eval_data["f1_score"] >= 0.95


def test_intelligence_engine_all_scenarios():
    from backend.agent.intelligence_engine import LedgerMindIntelligenceEngine
    from backend.core.models import AskLedgerMindRequest

    gen = SyntheticFinancialGenerator(seed=42)
    batch = gen.generate_batch(batch_id="test_intel", num_records=100, anomaly_rate=0.10)
    engine = LedgerMindIntelligenceEngine(batch)

    # 1. Operational diagnosis
    r1 = engine.ask(AskLedgerMindRequest(query="Give me a complete operational diagnosis"))
    assert r1.intent == "OPERATIONAL_DIAGNOSIS"
    assert "₹" in r1.direct_answer
    assert r1.visualization is not None
    assert r1.visualization["type"] == "waterfall"
    assert len(r1.evidence_citations) > 0

    # 2. Prioritization
    r2 = engine.ask(AskLedgerMindRequest(query="What needs attention right now?"))
    assert r2.intent == "PRIORITIZATION"
    assert r2.visualization["type"] == "pareto"
    assert len(r2.key_metrics) > 0

    # 3. Settlement trend
    r3 = engine.ask(AskLedgerMindRequest(query="Why did today's settlements fall?"))
    assert r3.intent == "SETTLEMENT_TREND"
    assert r3.visualization["type"] == "waterfall"

    # 4. Explain screen
    r4 = engine.ask(AskLedgerMindRequest(query="Explain this screen", screen_context="investigations"))
    assert r4.intent == "SCREEN_EXPLANATION"
    assert "Investigation Workspace" in r4.direct_answer

    # 5. Case investigation & lifecycle
    r5 = engine.ask(AskLedgerMindRequest(query="Show payment lifecycle for PAY_DEMO_7291", case_id="PAY_DEMO_7291"))
    assert r5.intent == "CASE_INVESTIGATION"
    assert r5.visualization["type"] == "lineage_graph"

    # 6. What evidence is missing
    r6 = engine.ask(AskLedgerMindRequest(query="What evidence is missing for PAY_DEMO_7291?"))
    assert r6.intent == "CASE_INVESTIGATION"

    # 7. Exposure query
    r7 = engine.ask(AskLedgerMindRequest(query="How much money is currently at risk?"))
    assert r7.intent == "EXPOSURE_RISK"

    # 8. Follow-up pronoun resolution
    r8 = engine.ask(AskLedgerMindRequest(
        query="Which batch caused most of that?",
        history=[{"conversation_context": {"active_focus_batch": "SETL_DEMO_8812", "active_focus_payment": "PAY_DEMO_7291"}}]
    ))
    assert r8.intent == "FOLLOWUP"
    assert "SETL_DEMO_8812" in r8.direct_answer

    # 9. Follow-up show those payments
    r9 = engine.ask(AskLedgerMindRequest(
        query="Show those payments",
        history=[{"conversation_context": {"active_focus_batch": "SETL_DEMO_8812", "active_focus_payment": "PAY_DEMO_7291"}}]
    ))
    assert r9.intent == "FOLLOWUP"
    assert len(r9.evidence_citations) > 0

    # 10. Depth variants verification
    assert "executive" in r1.depth_variants
    assert "analyst" in r1.depth_variants
    assert "technical" in r1.depth_variants
