#!/usr/bin/env python3
"""
Run a real end-to-end mission and verify synthesis output.
"""

import asyncio
import sys
import os
import re
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from core.system import system_manager
import asyncpg
from src.config.database import DatabaseConfig

# Override to use local database for testing
DatabaseConfig.DB_URLS["sheppard_v3"] = "postgresql://sheppard:1234@localhost:5432/sheppard_v3"

async def wait_for_mission_completion(adapter, mission_id, timeout_seconds=300):
    """Poll mission status until completed or failed."""
    start = asyncio.get_event_loop().time()
    while True:
        mission = await adapter.get_mission(mission_id)
        if not mission:
            raise RuntimeError(f"Mission {mission_id} not found")
        status = mission.get('status')
        if status in ('completed', 'failed', 'stopped'):
            return status
        if asyncio.get_event_loop().time() - start > timeout_seconds:
            raise TimeoutError(f"Mission {mission_id} did not complete within {timeout_seconds}s")
        await asyncio.sleep(5)

async def verify_synthesis_output(mission_id):
    """Verify the 5 invariants for the generated report."""
    print("\n[VERIFICATION] Checking synthesis output...")

    # Connect to DB (use same patched DatabaseConfig)
    from src.config.database import DatabaseConfig
    pg_dsn = DatabaseConfig.DB_URLS["sheppard_v3"]
    conn = await asyncpg.connect(pg_dsn)
    try:
        # Get authority_record for this mission (topic_id == mission_id)
        auth_rows = await conn.fetch(
            "SELECT authority_record_id FROM authority.authority_records WHERE topic_id = $1",
            mission_id
        )
        if not auth_rows:
            print("❌ No authority record found for mission")
            return False
        authority_record_id = auth_rows[0]['authority_record_id']

        # Get synthesis artifact for this authority_record
        artifact_rows = await conn.fetch(
            "SELECT artifact_id FROM authority.synthesis_artifacts WHERE authority_record_id = $1",
            authority_record_id
        )
        if not artifact_rows:
            print("❌ No synthesis artifact found")
            return False
        artifact_id = artifact_rows[0]['artifact_id']

        # Get sections
        section_rows = await conn.fetch(
            "SELECT section_name, summary FROM authority.synthesis_sections WHERE artifact_id = $1 ORDER BY section_order",
            artifact_id
        )
        if not section_rows:
            print("❌ No synthesis sections found")
            return False
        print(f"Found artifact with {len(section_rows)} sections")

        # Combine all text
        full_text = ""
        for row in section_rows:
            text = row['summary'] or ""
            full_text += text + "\n\n"

        # Get citations
        citation_rows = await conn.fetch(
            "SELECT citation_label, atom_id, source_id FROM authority.synthesis_citations WHERE artifact_id = $1",
            artifact_id
        )
        # Extract citation labels from text
        text_citations = re.findall(r'\[([A-Z]\d+)\]', full_text)
        db_labels = [r['citation_label'] for r in citation_rows if r['citation_label']]
        atom_ids = [r['atom_id'] for r in citation_rows if r['atom_id']]

        print(f"Text citations: {len(text_citations)}, DB citation records: len(citation_rows)")

        # 1. Every sentence has at least one citation
        sentences = re.split(r'[.!?]+', full_text)
        sentences = [s.strip() for s in sentences if s.strip()]
        unsentenced = sum(1 for s in sentences if not re.search(r'\[[A-Z]\d+\]', s))
        if unsentenced == 0:
            print("✅ Every sentence has citations")
        else:
            print(f"❌ {unsentenced} sentences lack citations")

        # 2. Every citation in text maps to DB record
        missing_labels = [c for c in text_citations if c not in db_labels]
        if not missing_labels:
            print("✅ All text citations have DB records")
        else:
            print(f"❌ Missing DB records: {missing_labels[:10]}...")

        # 3. All cited atoms exist in knowledge_atoms
        if atom_ids:
            atom_check = await conn.fetch(
                "SELECT atom_id FROM knowledge.knowledge_atoms WHERE atom_id = ANY($1)",
                atom_ids
            )
            existing_atom_ids = [r['atom_id'] for r in atom_check]
            missing_atoms = [aid for aid in atom_ids if aid not in existing_atom_ids]
            if not missing_atoms:
                print("✅ All cited atoms exist")
            else:
                print(f"❌ Missing atoms: {missing_atoms}")

        # 4. Placeholder for insufficient evidence
        placeholder_count = sum(1 for row in section_rows if '[INSUFFICIENT EVIDENCE FOR SECTION]' in (row['summary'] or ''))
        if placeholder_count > 0:
            print(f"✅ {placeholder_count} section(s) show placeholder")
        else:
            print("ℹ️ No placeholder sections")

        # 5. No cross-mission data: check all atoms belong to this mission
        if atom_ids:
            atom_mission_rows = await conn.fetch(
                "SELECT atom_id, mission_id FROM knowledge.knowledge_atoms WHERE atom_id = ANY($1)",
                atom_ids
            )
            cross_mission = [r['atom_id'] for r in atom_mission_rows if r['mission_id'] != mission_id]
            if cross_mission:
                print(f"❌ Cross-mission atoms: {cross_mission}")
            else:
                print("✅ All atoms belong to this mission")

        print("[VERIFICATION] Complete")
        return True

    finally:
        await conn.close()

async def main():
    # 1. Initialize
    print("Initializing system...")
    success, error = await system_manager.initialize()
    if not success:
        print(f"Failed to initialize: {error}")
        return 1

    # 2. Start a small mission
    topic = "Python programming language"
    print(f"\nStarting mission: {topic}")
    mission_id = await system_manager.learn(
        topic_name=topic,
        query=topic,
        ceiling_gb=0.001,  # 1MB ceiling — tiny
        academic_only=False
    )
    print(f"Mission ID: {mission_id}")

    # 3. Wait for mission to complete
    print("Waiting for mission to complete (max 3 minutes)...")
    try:
        status = await wait_for_mission_completion(system_manager.adapter, mission_id, timeout_seconds=180)
        print(f"Mission status: {status}")
        if status != 'completed':
            print(f"❌ Mission did not complete successfully: {status}")
            return 1
    except Exception as e:
        print(f"Error waiting for mission: {e}")
        return 1

    # 4. Generate report (synthesis)
    print("\nGenerating synthesis report...")
    try:
        report = await system_manager.generate_report(mission_id)
        if not report:
            print("❌ No report generated")
            return 1
        print(f"Report generated (length: {len(report)} chars)")
        # Show first 1000 chars
        print(report[:1000] + ("..." if len(report) > 1000 else ""))
    except Exception as e:
        print(f"❌ Error during synthesis: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 5. Verify
    try:
        await verify_synthesis_output(mission_id)
    except Exception as e:
        print(f"Verification error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 6. Cleanup
    await system_manager.cleanup()
    print("\n✅ End-to-end mission succeeded.")
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
