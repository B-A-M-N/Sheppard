"""
Consolidation engine — merges similar atoms into Golden Atoms
and resolves contradictory claims.
"""
import json
import logging
import re
import uuid
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

CONSOLIDATION_THRESHOLD = 0.85  # cosine similarity for Golden Atom clustering
CONTRADICTION_CANDIDATE_THRESHOLD = 0.75  # lower threshold for contradiction candidates


class ConsolidationEngine:
    def __init__(self, pg_adapter, ollama_client):
        self.pg = pg_adapter
        self.ollama = ollama_client

    # ────────────────────────────────────────────────────────────
    # EXTRACT-03: Golden Atom Consolidation
    # ────────────────────────────────────────────────────────────

    async def consolidate_atoms(self, mission_id: str) -> dict:
        """
        Merge semantically similar atoms into Golden Atoms.

        Returns summary dict with counts.
        """
        # 1. Fetch all active atoms for this mission
        atoms = await self.pg.fetch_many(
            "knowledge.knowledge_atoms",
            where={"mission_id": mission_id},
            limit=500,
        )
        # Filter out already-obsolete atoms
        atoms = [a for a in atoms if not a.get("is_obsolete", False)]

        if len(atoms) < 2:
            return {
                "mission_id": mission_id,
                "total_atoms": len(atoms),
                "clusters": 0,
                "golden_atoms_created": 0,
                "atoms_obsoleted": 0,
            }

        # 2. Embed all atom statements
        statements = [a["statement"] for a in atoms]
        embeddings = await self._batch_embed(statements)

        # 3. Cluster by cosine similarity
        from src.utils.embedding_gates import _cluster_by_similarity
        cluster_indices = _cluster_by_similarity(
            list(range(len(atoms))), embeddings, threshold=CONSOLIDATION_THRESHOLD
        )

        # 4. Process clusters
        golden_count = 0
        obsolete_count = 0

        for cluster in cluster_indices:
            if len(cluster) < 2:
                continue  # Single-atom cluster — already unique

            cluster_atoms = [atoms[i] for i in cluster]

            # Pick representative: highest confidence
            rep = max(cluster_atoms, key=lambda a: a.get("confidence", 0))
            rep_id = rep["atom_id"]

            # Collect all source_ids from evidence
            all_source_ids = set()
            for atom in cluster_atoms:
                source_ids = await self._get_source_ids_for_atom(atom["atom_id"])
                all_source_ids.update(source_ids)

            # Update representative: mark as golden, set source_ids
            await self.pg.update_row(
                "knowledge.knowledge_atoms", "atom_id",
                {
                    "atom_id": rep_id,
                    "is_golden": True,
                    "source_ids": list(all_source_ids),
                }
            )
            golden_count += 1

            # Mark other atoms as obsolete
            for atom in cluster_atoms:
                if atom["atom_id"] != rep_id:
                    await self.pg.update_row(
                        "knowledge.knowledge_atoms", "atom_id",
                        {
                            "atom_id": atom["atom_id"],
                            "is_obsolete": True,
                            "obsolete_reason": "consolidated_into_golden",
                            "golden_atom_id": rep_id,
                        }
                    )
                    obsolete_count += 1

        logger.info(f"[Consolidation] Mission {mission_id[:8]}: "
                    f"{golden_count} golden atoms created, "
                    f"{obsolete_count} atoms obsoleted")

        return {
            "mission_id": mission_id,
            "total_atoms": len(atoms),
            "clusters": len(cluster_indices),
            "golden_atoms_created": golden_count,
            "atoms_obsoleted": obsolete_count,
        }

    # ────────────────────────────────────────────────────────────
    # EXTRACT-04: Contradiction Resolution
    # ────────────────────────────────────────────────────────────

    async def resolve_contradictions(self, mission_id: str) -> dict:
        """
        Detect and resolve contradictory claims.

        Returns summary dict.
        """
        from src.utils.embedding_gates import _cluster_by_similarity

        # 1. Fetch non-obsolete atoms
        atoms = await self.pg.fetch_many(
            "knowledge.knowledge_atoms",
            where={"mission_id": mission_id},
            limit=500,
        )
        atoms = [a for a in atoms if not a.get("is_obsolete", False)]

        if len(atoms) < 2:
            return {
                "mission_id": mission_id,
                "candidates": 0,
                "verified_contradictions": 0,
                "resolved": 0,
            }

        # 2. Find candidate pairs: embed + cluster at lower threshold
        statements = [a["statement"] for a in atoms]
        embeddings = await self._batch_embed(statements)

        cluster_indices = _cluster_by_similarity(
            list(range(len(atoms))), embeddings, threshold=CONTRADICTION_CANDIDATE_THRESHOLD
        )

        candidates = []
        for cluster in cluster_indices:
            if len(cluster) < 2:
                continue
            cluster_atoms = [atoms[i] for i in cluster]
            # Check for confidence divergence or differing claims
            for i in range(len(cluster_atoms)):
                for j in range(i + 1, len(cluster_atoms)):
                    a, b = cluster_atoms[i], cluster_atoms[j]
                    conf_diff = abs(a.get("confidence", 0) - b.get("confidence", 0))
                    if conf_diff > 0.15 or a.get("statement", "") != b.get("statement", ""):
                        candidates.append((a, b))

        # 3. LLM verification for each candidate
        verified = 0
        resolved = 0
        for atom_a, atom_b in candidates:
            is_contradiction, reason = await self._verify_contradiction(atom_a, atom_b)
            if is_contradiction:
                verified += 1
                # 4. Adjudicate: higher score wins
                score_a = self._compute_adjudication_score(atom_a)
                score_b = self._compute_adjudication_score(atom_b)

                if score_a >= score_b:
                    winner, loser = atom_a, atom_b
                else:
                    winner, loser = atom_b, atom_a

                # Mark loser as obsolete
                await self.pg.update_row(
                    "knowledge.knowledge_atoms", "atom_id",
                    {
                        "atom_id": loser["atom_id"],
                        "is_obsolete": True,
                        "obsolete_reason": "contradiction_resolved",
                        "golden_atom_id": winner["atom_id"],
                    }
                )
                resolved += 1

                # Record contradiction using V3 schema
                contradiction_set_id = f"contra-{uuid.uuid4().hex[:12]}"
                await self.pg.insert_row("knowledge.contradiction_sets", {
                    "contradiction_set_id": contradiction_set_id,
                    "topic_id": winner.get("topic_id", ""),
                    "summary": f"Contradiction: '{winner['statement'][:100]}' vs '{loser['statement'][:100]}'. Resolved: {reason}",
                    "resolution_status": "resolved",
                    "confidence_split_json": json.dumps({
                        "winner_id": winner["atom_id"],
                        "winner_score": round(score_a if score_a >= score_b else score_b, 3),
                        "loser_id": loser["atom_id"],
                        "loser_score": round(score_b if score_a >= score_b else score_a, 3),
                        "reason": reason,
                    }),
                })
                await self.pg.insert_row("knowledge.contradiction_members", {
                    "contradiction_set_id": contradiction_set_id,
                    "atom_id": winner["atom_id"],
                    "position_label": "accepted",
                })
                await self.pg.insert_row("knowledge.contradiction_members", {
                    "contradiction_set_id": contradiction_set_id,
                    "atom_id": loser["atom_id"],
                    "position_label": "rejected",
                })

        logger.info(f"[Contradictions] Mission {mission_id[:8]}: "
                    f"{verified} verified, {resolved} resolved")

        return {
            "mission_id": mission_id,
            "candidates": len(candidates),
            "verified_contradictions": verified,
            "resolved": resolved,
        }

    # ────────────────────────────────────────────────────────────
    # Internal helpers
    # ────────────────────────────────────────────────────────────

    async def _batch_embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts sequentially."""
        embeddings = []
        for text in texts:
            emb = await self.ollama.embed(text)
            embeddings.append(emb)
        return embeddings

    async def _get_source_ids_for_atom(self, atom_id: str) -> set:
        """Get all source_ids associated with an atom via atom_evidence."""
        rows = await self.pg.fetch_many(
            "knowledge.atom_evidence",
            where={"atom_id": atom_id},
        )
        return {r.get("source_id") for r in rows if r.get("source_id")}

    async def _verify_contradiction(self, atom_a: dict, atom_b: dict) -> tuple:
        """Use LLM to verify if two atoms contradict."""
        from src.llm.model_router import TaskType
        prompt = (
            f"Do these two statements contradict each other? "
            f"Answer YES or NO with a brief reason.\n\n"
            f"Statement A: {atom_a.get('statement', '')}\n"
            f"Statement B: {atom_b.get('statement', '')}\n\n"
            f'Respond in JSON format: {{"contradiction": true/false, "reason": "brief explanation"}}'
        )
        try:
            result = await self.ollama.complete(TaskType.EXTRACTION, prompt, max_tokens=200)
            cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', result.strip(), flags=re.DOTALL)
            data = json.loads(cleaned)
            return data.get("contradiction", False), data.get("reason", "")
        except Exception as e:
            logger.warning(f"[Contradiction] LLM verification failed: {e}")
            return False, ""

    def _compute_adjudication_score(self, atom: dict) -> float:
        """
        Simple scoring for contradiction adjudication.
        Uses atom confidence as proxy for source reliability + quality.
        """
        confidence = atom.get("confidence", 0.5)
        return confidence * 0.8  # Rough proxy — full formula needs source lookup
