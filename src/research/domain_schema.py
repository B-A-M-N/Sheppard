"""
domain_schema.py

Universal abstractions for the Domain Authority Foundry.
Defines the strict contracts for extraction, synthesis, and application.
Includes serialization methods for the Triad (Postgres, Chroma, Redis).
"""

from typing import List, Dict, Optional, Any, Sequence
from datetime import datetime, timezone
import uuid
import json
from pydantic import BaseModel, Field

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# ──────────────────────────────────────────────────────────────
# 1. DOMAIN PROFILE (The Refinery Tuning Knob)
# ──────────────────────────────────────────────────────────────

class SourcePreferences(BaseModel):
    preferred_classes: List[str] = Field(default_factory=list)
    discouraged_classes: List[str] = Field(default_factory=list)
    minimum_source_diversity: int = 3

class TrustPolicy(BaseModel):
    ranking_model: str = "profile_weighted"
    weights: Dict[str, float] = Field(default_factory=dict)
    recency_weight: float = 0.5
    authority_weight: float = 0.8
    corroboration_weight: float = 0.9
    specificity_weight: float = 0.7

class RecencyPolicy(BaseModel):
    sensitivity: str = "medium"  # low|medium|high
    stale_after_days: int = 365
    version_sensitivity: str = "medium"

class ExtractionPolicy(BaseModel):
    prioritize_atom_types: List[str] = Field(default_factory=list)
    require_version_qualifiers: bool = False
    require_environment_qualifiers: bool = False

class SynthesisPolicy(BaseModel):
    default_sections: List[str] = Field(default_factory=list)
    style: str = "objective"
    contradiction_required: bool = True

class DomainProfile(BaseModel):
    profile_id: str
    name: str
    description: str
    domain_type: str
    subtypes: List[str] = Field(default_factory=list)
    source_preferences: SourcePreferences = Field(default_factory=SourcePreferences)
    trust_policy: TrustPolicy = Field(default_factory=TrustPolicy)
    recency_policy: RecencyPolicy = Field(default_factory=RecencyPolicy)
    extraction_policy: ExtractionPolicy = Field(default_factory=ExtractionPolicy)
    synthesis_policy: SynthesisPolicy = Field(default_factory=SynthesisPolicy)
    application_modes: List[str] = Field(default_factory=list)

    def to_pg_row(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "domain_type": self.domain_type,
            "description": self.description,
            "config_json": self.model_dump_json(exclude={"profile_id", "name", "domain_type", "description"}),
            "version": 1
        }

    def to_runtime_cache(self) -> Dict[str, Any]:
        return json.loads(self.model_dump_json())


# ──────────────────────────────────────────────────────────────
# 1b. MISSION & NODE
# ──────────────────────────────────────────────────────────────

class ResearchMission(BaseModel):
    mission_id: str
    topic_id: str
    domain_profile_id: str
    title: str
    objective: str
    status: str = "created"
    depth_target: Optional[str] = None
    budget_bytes: int = 0
    bytes_ingested: int = 0
    source_count: int = 0
    stop_reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)

    def to_pg_row(self) -> Dict[str, Any]:
        row = self.model_dump(exclude={"metadata"})
        row["metadata_json"] = json.dumps(self.metadata)
        return row

    def to_runtime_cache(self) -> Dict[str, Any]:
        return json.loads(self.model_dump_json())

class MissionNode(BaseModel):
    node_id: str
    mission_id: str
    parent_node_id: Optional[str] = None
    label: str
    concept_form: str
    surface_forms: List[str] = Field(default_factory=list)
    artifact_forms: List[str] = Field(default_factory=list)
    adjacency_forms: List[str] = Field(default_factory=list)
    status: str = "underexplored"
    priority: float = 0.0
    coverage_score: float = 0.0
    gain_score: float = 0.0
    failure_signature: Optional[str] = None
    exhausted_modes: List[str] = Field(default_factory=list)
    notes: Dict[str, Any] = Field(default_factory=dict)

    def to_pg_row(self) -> Dict[str, Any]:
        row = self.model_dump(exclude={"surface_forms", "artifact_forms", "adjacency_forms", "notes", "exhausted_modes"})
        row["surface_forms_json"] = json.dumps(self.surface_forms)
        row["artifact_forms_json"] = json.dumps(self.artifact_forms)
        row["adjacency_forms_json"] = json.dumps(self.adjacency_forms)
        row["notes_json"] = json.dumps(self.notes)
        row["exhausted_modes_json"] = json.dumps(self.exhausted_modes)
        return row

    def to_runtime_cache(self) -> Dict[str, Any]:
        return json.loads(self.model_dump_json())


# ──────────────────────────────────────────────────────────────
# 1c. CORPUS (Source & Chunk)
# ──────────────────────────────────────────────────────────────

class Source(BaseModel):
    source_id: str
    mission_id: str
    topic_id: str
    url: str
    normalized_url: str
    normalized_url_hash: str
    title: Optional[str] = None
    source_class: str = "web"
    mime_type: Optional[str] = None
    language: Optional[str] = "en"
    trust_score: float = 0.5
    quality_score: float = 0.5
    canonical_text_ref: Optional[str] = None
    content_hash: Optional[str] = None
    status: str = "discovered"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_pg_row(self) -> Dict[str, Any]:
        row = self.model_dump(exclude={"metadata"})
        row["metadata_json"] = json.dumps(self.metadata)
        return row

    def to_runtime_cache(self) -> Dict[str, Any]:
        return json.loads(self.model_dump_json())

class Chunk(BaseModel):
    chunk_id: str
    source_id: str
    mission_id: str
    topic_id: str
    cluster_id: Optional[str] = None
    chunk_index: int
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    token_count: Optional[int] = None
    chunk_hash: str
    text_ref: Optional[str] = None
    inline_text: Optional[str] = None
    quality_score: float = 0.5
    boilerplate_score: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_pg_row(self) -> Dict[str, Any]:
        row = self.model_dump(exclude={"metadata"})
        row["metadata_json"] = json.dumps(self.metadata)
        return row

    def to_chroma_document(self) -> str:
        return str(self.inline_text or "").strip()

    def to_chroma_metadata(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "mission_id": self.mission_id,
            "topic_id": self.topic_id,
            "cluster_id": self.cluster_id or "",
            "quality_score": self.quality_score
        }

    def to_runtime_cache(self) -> Dict[str, Any]:
        return json.loads(self.model_dump_json())


# ──────────────────────────────────────────────────────────────
# 1. KNOWLEDGE UNIT — Canonical Schema Contract
# ──────────────────────────────────────────────────────────────
#
# SINGLE SCHEMA across ALL pipeline stages:
#   Distillery → KnowledgeUnit
#   LLM compression → KnowledgeUnit
#   Fallback → KnowledgeUnit
#   Refinery → KnowledgeUnit
#   Embedding layer → KnowledgeUnit.text
#
# Replaces: atoms, claims, summary_claim (all unified here)


class KnowledgeUnit(BaseModel):
    """
    The single canonical knowledge representation.

    Every pipeline stage produces and consumes this exact structure.
    No more schema drift between atoms, claims, and fallbacks.
    """
    id: str = Field(description="Unique identifier, e.g. 'ku_001' or sha256 hash")
    text: str = Field(description="The knowledge content — complete sentence, standalone")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = Field(default="", description="Origin: URL, filename, or 'fallback_truncation'")
    tags: List[str] = Field(default_factory=list, description="Classification: claim, definition, mechanism, compressed, fallback, etc.")

    # Optional rich metadata (not required for basic pipeline flow)
    topic: str = Field(default="")
    atom_type: str = Field(default="claim", description="claim, definition, mechanism, constraint, tradeoff, failure_mode, contradiction, example, metric")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    novelty: float = Field(default=0.5, ge=0.0, le=1.0)
    stability: str = Field(default="medium")
    lineage: Dict[str, Any] = Field(default_factory=dict)
    scoring: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_embedding_text(self) -> str:
        """Return text suitable for embedding — just the content."""
        return self.text

    def to_dict(self) -> Dict[str, Any]:
        """Export as plain dict for legacy compatibility."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KnowledgeUnit":
        """
        Create KnowledgeUnit from any legacy dict format.
        Handles: atom format, claim format, compressed format, fallback format.
        """
        # Extract text from various field names
        text = (
            d.get("text")
            or d.get("content")
            or d.get("statement")
            or d.get("fact", "")
        )

        # Extract type from various field names
        unit_type = (
            d.get("atom_type")
            or d.get("type")
            or d.get("item_type")
            or "claim"
        )

        # Extract confidence
        confidence = float(d.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))  # Clamp

        # Build ID
        unit_id = d.get("id") or d.get("atom_id") or d.get("unit_id", "")
        if not unit_id:
            import hashlib
            unit_id = "ku_" + hashlib.sha256(text.encode()).hexdigest()[:12]

        # Extract source
        source = d.get("source", "")
        if not source:
            lineage = d.get("lineage", {})
            if isinstance(lineage, dict):
                source = lineage.get("source_url", "")
            elif isinstance(lineage, AtomLineage):
                source = ""

        # Extract tags
        tags = list(d.get("tags", []))
        if not tags:
            tags = [unit_type]
        if d.get("compressed"):
            tags.append("compressed")
        if unit_type not in tags:
            tags.insert(0, unit_type)

        return cls(
            id=unit_id,
            text=text,
            confidence=confidence,
            source=source,
            tags=tags,
            topic=d.get("topic", d.get("topic_id", "")),
            atom_type=unit_type,
            importance=float(d.get("importance", 0.5)),
            novelty=float(d.get("novelty", 0.5)),
            stability=d.get("stability", "medium"),
            lineage=d.get("lineage", {}),
            scoring=d.get("scoring", {}),
            metadata=d.get("metadata", {}),
        )


# ──────────────────────────────────────────────────────────────
# 2. KNOWLEDGE ATOM (Legacy — backward compatibility layer)
# ──────────────────────────────────────────────────────────────
# New code should use KnowledgeUnit. KnowledgeAtom remains for
# existing database records and rich-metadata workflows.

class AtomScope(BaseModel):
    applies_to: List[str] = Field(default_factory=list)
    does_not_apply_to: List[str] = Field(default_factory=list)
    jurisdiction: Optional[str] = None
    environment: List[str] = Field(default_factory=list)
    time_range: Dict[str, Optional[str]] = Field(default_factory=dict)
    version_range: List[str] = Field(default_factory=list)

class AtomQualifiers(BaseModel):
    version_notes: List[str] = Field(default_factory=list)
    temporal_notes: List[str] = Field(default_factory=list)
    caveats: List[str] = Field(default_factory=list)
    counterpoints: List[str] = Field(default_factory=list)

class AtomLineage(BaseModel):
    created_by: str = "extraction_engine"
    created_at: str = Field(default_factory=_utcnow_iso)
    mission_id: str
    extraction_mode: str
    parent_objects: List[str] = Field(default_factory=list)

class AtomReuse(BaseModel):
    tags: List[str] = Field(default_factory=list)
    application_modes: List[str] = Field(default_factory=list)
    retrieval_priority: float = 0.5

class KnowledgeAtom(BaseModel):
    atom_id: str
    topic_id: str
    authority_record_id: Optional[str] = None
    domain_profile_id: str
    atom_type: str # definition, claim, mechanism, constraint, tradeoff, failure_mode, contradiction, example, metric
    title: str
    statement: str
    summary: Optional[str] = None
    confidence: float = 0.7
    importance: float = 0.5
    novelty: float = 0.5
    stability: str = "medium"
    
    scope: AtomScope = Field(default_factory=AtomScope)
    qualifiers: AtomQualifiers = Field(default_factory=AtomQualifiers)
    lineage: AtomLineage
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_pg_row(self) -> Dict[str, Any]:
        row = self.model_dump(exclude={"scope", "qualifiers", "lineage", "metadata"})
        row["mission_id"] = self.lineage.mission_id
        row["scope_json"] = self.scope.model_dump_json()
        row["qualifiers_json"] = self.qualifiers.model_dump_json()
        row["lineage_json"] = self.lineage.model_dump_json()
        row["metadata_json"] = json.dumps(self.metadata)
        return row

    def to_chroma_document(self) -> str:
        parts = [self.title, self.statement, self.summary or ""]
        if self.qualifiers.caveats:
            parts.append("Caveats: " + " | ".join(map(str, self.qualifiers.caveats[:5])))
        if self.qualifiers.counterpoints:
            parts.append("Counterpoints: " + " | ".join(map(str, self.qualifiers.counterpoints[:5])))
        return "\n".join(p for p in parts if p).strip()

    def to_chroma_metadata(self) -> Dict[str, Any]:
        return {
            "atom_id": self.atom_id,
            "authority_record_id": self.authority_record_id or "",
            "topic_id": self.topic_id,
            "domain_profile_id": self.domain_profile_id,
            "atom_type": self.atom_type,
            "confidence": self.confidence,
            "importance": self.importance,
            "stability": self.stability
        }

    def to_runtime_cache(self) -> Dict[str, Any]:
        return json.loads(self.model_dump_json())


# ──────────────────────────────────────────────────────────────
# 3. EVIDENCE BUNDLE (For Synthesis)
# ──────────────────────────────────────────────────────────────

class BundleCoverage(BaseModel):
    coverage_density: float = 0.0
    source_diversity: int = 0
    contradiction_density: float = 0.0
    recency_balance: float = 0.0

class EvidenceBundle(BaseModel):
    bundle_id: str
    bundle_type: str
    topic_id: str
    authority_record_id: Optional[str] = None
    objective: str
    section_name: Optional[str] = None
    
    coverage_status: BundleCoverage = Field(default_factory=BundleCoverage)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    assembly_metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_pg_row(self) -> Dict[str, Any]:
        row = self.model_dump(exclude={"coverage_status", "constraints", "assembly_metadata"})
        row["coverage_status_json"] = self.coverage_status.model_dump_json()
        row["constraints_json"] = json.dumps(self.constraints)
        row["assembly_metadata_json"] = json.dumps(self.assembly_metadata)
        return row

    def to_runtime_cache(self) -> Dict[str, Any]:
        return json.loads(self.model_dump_json())


# ──────────────────────────────────────────────────────────────
# 3b. SYNTHESIS ARTIFACT
# ──────────────────────────────────────────────────────────────

class SynthesisArtifact(BaseModel):
    artifact_id: str
    authority_record_id: str
    artifact_type: str
    title: str
    abstract: Optional[str] = None
    content_ref: Optional[str] = None
    freshness_state: str = "current"
    version: int = 1
    metadata: Dict[str, Any] = Field(default_factory=dict)
    mission_id: Optional[str] = None  # V3 mission isolation

    # Optional loaded content for indexing
    inline_text: Optional[str] = None

    def to_pg_row(self) -> Dict[str, Any]:
        row = self.model_dump(exclude={"metadata", "inline_text"})
        row["metadata_json"] = json.dumps(self.metadata)
        return row

    def to_chroma_document(self) -> str:
        parts = [self.title, self.abstract or "", self.inline_text or ""]
        return "\n".join(p for p in parts if p).strip()

    def to_chroma_metadata(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "authority_record_id": self.authority_record_id,
            "artifact_type": self.artifact_type,
            "freshness_state": self.freshness_state
        }

    def to_runtime_cache(self) -> Dict[str, Any]:
        return json.loads(self.model_dump_json())


# ──────────────────────────────────────────────────────────────
# 4. DOMAIN AUTHORITY RECORD (The Durable Bank)
# ──────────────────────────────────────────────────────────────

class AuthorityScope(BaseModel):
    included: List[str] = Field(default_factory=list)
    excluded: List[str] = Field(default_factory=list)
    framing_statement: str

class AuthorityStatus(BaseModel):
    maturity: str = "forming" # forming, active, saturated, legacy
    freshness: str = "current"
    confidence: float = 0.0

class FrontierSummary(BaseModel):
    coverage_density: float
    source_count: int
    source_class_distribution: Dict[str, int]
    known_sparse_areas: List[str] = Field(default_factory=list)
    known_dense_areas: List[str] = Field(default_factory=list)
    global_gain_flattened: bool = False

class DomainAuthorityRecord(BaseModel):
    authority_record_id: str
    topic_id: str
    title: str
    canonical_title: str
    domain_profile_id: str
    
    scope: AuthorityScope
    status: AuthorityStatus
    frontier_summary: FrontierSummary
    
    corpus_layer: Dict[str, Any] = Field(default_factory=dict)
    atom_layer: Dict[str, Any] = Field(default_factory=dict)
    synthesis_layer: Dict[str, Any] = Field(default_factory=dict)
    advisory_layer: Dict[str, Any] = Field(default_factory=dict)
    lineage_layer: Dict[str, str] = Field(default_factory=dict)
    reuse: Dict[str, Any] = Field(default_factory=dict)

    def to_pg_row(self) -> Dict[str, Any]:
        row = self.model_dump(exclude={
            "scope", "status", "frontier_summary", 
            "corpus_layer", "atom_layer", "synthesis_layer", 
            "advisory_layer", "lineage_layer", "reuse"
        })
        row["scope_json"] = self.scope.model_dump_json()
        row["status_json"] = self.status.model_dump_json()
        row["frontier_summary_json"] = self.frontier_summary.model_dump_json()
        row["corpus_layer_json"] = json.dumps(self.corpus_layer)
        row["atom_layer_json"] = json.dumps(self.atom_layer)
        row["synthesis_layer_json"] = json.dumps(self.synthesis_layer)
        row["advisory_layer_json"] = json.dumps(self.advisory_layer)
        row["lineage_layer_json"] = json.dumps(self.lineage_layer)
        row["reuse_json"] = json.dumps(self.reuse)
        return row

    def to_chroma_document(self) -> str:
        parts = [self.title, self.scope.framing_statement]
        if self.scope.included:
            parts.append("Scope: " + " | ".join(map(str, self.scope.included[:10])))
        decision_rules = self.advisory_layer.get("decision_rules", [])
        if decision_rules:
            parts.append("Decision rules: " + " | ".join(map(str, decision_rules[:10])))
        transfer = self.advisory_layer.get("transferability_notes", [])
        if transfer:
            parts.append("Transferability: " + " | ".join(map(str, transfer[:10])))
        return "\n".join(p for p in parts if p).strip()

    def to_chroma_metadata(self) -> Dict[str, Any]:
        return {
            "authority_record_id": self.authority_record_id,
            "topic_id": self.topic_id,
            "domain_profile_id": self.domain_profile_id,
            "maturity": self.status.maturity,
            "confidence": self.status.confidence,
            "freshness": self.status.freshness,
            "core_atom_count": len(self.atom_layer.get("core_atom_ids", [])),
        }

    def to_runtime_cache(self) -> Dict[str, Any]:
        return json.loads(self.model_dump_json())


# ──────────────────────────────────────────────────────────────
# 5. APPLICATION QUERY (Future Reasoning Entrypoint)
# ──────────────────────────────────────────────────────────────

class AppQueryContext(BaseModel):
    project_id: Optional[str] = None
    system_refs: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    desired_outputs: List[str] = Field(default_factory=list)

class AppQueryInputs(BaseModel):
    candidate_authority_record_ids: List[str] = Field(default_factory=list)
    required_atom_types: List[str] = Field(default_factory=list)
    contradictions_required: bool = True

class ApplicationQuery(BaseModel):
    application_query_id: str
    query_type: str
    title: str
    problem_statement: str
    
    payload: Dict[str, Any] = Field(default_factory=dict)
    
    def to_pg_row(self) -> Dict[str, Any]:
        row = self.model_dump(exclude={"payload"})
        row["payload_json"] = json.dumps(self.payload)
        return row

    def to_runtime_cache(self) -> Dict[str, Any]:
        return json.loads(self.model_dump_json())
