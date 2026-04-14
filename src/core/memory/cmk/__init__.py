"""
Cognitive Memory Kernel (CMK) v1

Replaces blind vector-dump retrieval with:
  intent → plan → weighted evidence → structured context → constrained reasoning

Two-tier architecture:
  Tier 1 (v1): Intent → Evidence Plan → Dynamic Scoring → Evidence Pack → LLM
  Tier 2 (v2+): Concept clustering → Concept-level retrieval → Atom expansion → Evidence Pack

Modules:
  v1 Pipeline:
    - intent_profiler: Classifies query intent type + depth
    - evidence_planner: Generates retrieval instructions from intent
    - atom_scorer: Dynamic, context-sensitive atom scoring
    - evidence_pack: Assembles atoms into confidence-tiered blocks
    - contradiction_detector: Identifies conflicting atoms
    - feedback_loop: Post-response atom weight updates

  v2+ Concept Layer:
    - types: CMKAtom + Concept data structures
    - embedder: Ollama embedding wrapper
    - clustering: KMeans (default) + HDBSCAN (optional)
    - concepts: Concept construction from atom clusters
    - builder: Full pipeline: atoms → embeddings → clusters → concepts
    - retrieval: Concept-level retrieval → atom expansion
"""

from .intent_profiler import IntentProfiler, IntentProfile
from .evidence_planner import EvidencePlanner, EvidencePlan
from .atom_scorer import AtomScorer, score_atom
from .evidence_pack import EvidencePackBuilder, EvidencePack
from .contradiction_detector import ContradictionDetector
from .feedback_loop import FeedbackLoop

from .types import CMKAtom, Concept
from .embedder import OllamaEmbedder
from .builder import ConceptBuilder
from .retrieval import CMKRetriever
from .prompt_contract import build_cmk_prompt, build_summary_prompt
from .grounding import (
    deduplicate_by_similarity,
    check_abstraction_eligibility,
    check_definition_support,
    analyze_novelty,
    build_evidence_locked_context,
    AbstractionGate,
    EvidenceItem,
)
from .scoring import score_atom as score_atom_weighted, score_atoms_batch
from .loop_governor import (
    LoopGovernor,
    NoveltyGate,
    SemanticDecayTracker,
    CrossSessionLoopDetector,
    diversify_retrieval,
    compress_context,
    detect_sentence_repetition,
    check_hard_stop,
    truncate_to_limit,
    GovernorDecision,
    CompressedContext,
    StopCondition,
)

from .config import CMKConfig
from .store import CMKStore
from .runtime import CMKRuntime
from .integration import CMKIntegration

__all__ = [
    # v1 Pipeline
    "IntentProfiler",
    "IntentProfile",
    "EvidencePlanner",
    "EvidencePlan",
    "AtomScorer",
    "score_atom",
    "EvidencePackBuilder",
    "EvidencePack",
    "ContradictionDetector",
    "FeedbackLoop",

    # Prompt
    "build_cmk_prompt",
    "build_summary_prompt",

    # Grounding (anti-hallucination)
    "deduplicate_by_similarity",
    "check_abstraction_eligibility",
    "check_definition_support",
    "analyze_novelty",
    "build_evidence_locked_context",
    "AbstractionGate",
    "EvidenceItem",

    # Scoring
    "score_atom_weighted",
    "score_atoms_batch",

    # Loop Governor
    "LoopGovernor",
    "NoveltyGate",
    "SemanticDecayTracker",
    "CrossSessionLoopDetector",
    "diversify_retrieval",
    "compress_context",
    "detect_sentence_repetition",
    "check_hard_stop",
    "truncate_to_limit",
    "GovernorDecision",
    "CompressedContext",
    "StopCondition",

    # v2+ Concept Layer
    "CMKAtom",
    "Concept",
    "OllamaEmbedder",
    "ConceptBuilder",
    "CMKRetriever",

    # Config + Store + Runtime + Integration
    "CMKConfig",
    "CMKStore",
    "CMKRuntime",
    "CMKIntegration",
]
