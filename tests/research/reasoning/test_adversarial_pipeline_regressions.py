import pytest

from src.research.reasoning.analyst import AnalystOutput, AnalystSynthAdapter
from src.research.reasoning.adversarial_critic import CriticOutput
from src.research.reasoning.assembler import EvidencePacket
from src.research.reasoning.problem_frame import ProblemFrame
from src.research.reasoning.retriever import RetrievedItem
from src.research.reasoning.v3_retriever import V3Retriever


class _FakeOllama:
    def __init__(self, responses):
        self._responses = list(responses)

    async def complete(self, *args, **kwargs):
        if not self._responses:
            raise AssertionError("No fake LLM responses remaining")
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_canonical_mode_surfaces_authoritative_older_atom():
    retriever = V3Retriever(adapter=None)
    old_canonical = RetrievedItem(
        content="Postgres uses MVCC for concurrency control.",
        source="authority",
        strategy="structural",
        relevance_score=0.72,
        trust_score=0.95,
        recency_days=3200,
        tech_density=0.8,
        metadata={"atom_id": "old", "is_core_atom": True, "authority_state": "canonical"},
    )
    new_weak = RetrievedItem(
        content="A recent blog speculates about locking behavior.",
        source="recent",
        strategy="semantic",
        relevance_score=0.74,
        trust_score=0.40,
        recency_days=2,
        tech_density=0.3,
        metadata={"atom_id": "new"},
    )
    ranked = retriever._rerank([new_weak, old_canonical], limit=2, retrieval_mode="canonical")
    assert ranked[0].metadata["atom_id"] == "old"


@pytest.mark.asyncio
async def test_refinement_changes_output_in_response_to_critic_feedback():
    ollama = _FakeOllama([
        "Revised reasoning draft mentioning contradiction [A2] and narrowing the claim.",
        """
        {
          "diagnosis": "The latency spike is likely queue contention during deploy windows [A1][A2].",
          "confidence": 0.61,
          "reasoning": "The revision addresses the contradictory packet-loss atom [A2] and narrows the claim [A1][A2].",
          "alternatives": [],
          "recommendation": "Measure queue contention and packet loss together.",
          "recommendation_rationale": "The critic identified an overclaim and a missed contradiction.",
          "risks": ["Packet loss may still be primary."],
          "open_questions": ["Do deploy windows correlate with drops?"],
          "key_atoms": ["[A1]", "[A2]"],
          "tensions": ["Queue contention evidence conflicts with packet-loss evidence."],
          "unresolved_uncertainties": ["Whether queue contention is primary."],
          "assumption_dependencies": ["Deploy timing is causal."],
          "best_counterargument": "Packet loss alone could explain the spike."
        }
        """,
    ])
    adapter = AnalystSynthAdapter(ollama)
    packet = EvidencePacket(
        topic_name="latency",
        section_title="analysis",
        section_objective="objective",
        atoms=[
            {"global_id": "[A1]", "text": "Queue contention increased during deployment windows.", "type": "claim"},
            {"global_id": "[A2]", "text": "Packet loss also increased during the same period.", "type": "contradiction"},
        ],
        contradictions=[{"description": "conflict", "claim_a": "Queue contention is primary.", "claim_b": "Packet loss is primary.", "type": "direct"}],
    )
    frame = ProblemFrame(raw_statement="Why is latency spiking?", retrieval_queries=["latency spike causes"])
    prior = AnalystOutput(
        diagnosis="Queue contention is the cause [A1].",
        confidence=0.82,
        reasoning="Only [A1] was considered.",
        recommendation="Reduce contention immediately.",
        key_atoms=["[A1]"],
    )
    critic = CriticOutput(
        strongest_objection="You ignored contradictory packet-loss evidence [A2].",
        overclaims=["The draft claimed queue contention was definitively primary."],
        overlooked_atoms=["[A2]"],
        hidden_assumptions=["Queue contention dominates packet loss."],
        required_revisions=["Address the contradictory atom [A2].", "Narrow the diagnosis confidence."],
    )

    refined = await adapter.refine(packet, frame, prior, critic)

    assert refined.diagnosis != prior.diagnosis
    assert "[A2]" in refined.diagnosis or "[A2]" in refined.reasoning
    assert refined.revisions_applied == critic.required_revisions
    assert refined.confidence < prior.confidence
