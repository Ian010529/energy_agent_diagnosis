from __future__ import annotations

import json
import re
from pathlib import Path

from energy_agent.core.canonicalization import canonical_digest

ROOT = Path(__file__).resolve().parents[2]


def test_committed_descriptors_cover_complete_mysql_structure() -> None:
    for schema in ("control", "ops"):
        descriptor = json.loads(
            (ROOT / f"schema/descriptor/{schema}-v1.json").read_text(encoding="utf-8")
        )
        assert descriptor["schema"] == schema
        assert descriptor["canonicalization_version"] == 2
        assert descriptor["tables"]
        assert descriptor["columns"]
        assert descriptor["indexes"]
        assert descriptor["constraints"]
        assert descriptor["checks"]
        assert descriptor["foreign_keys"]
        assert all(table["engine"] == "InnoDB" for table in descriptor["tables"])
        assert all(
            table["table_collation"] == "utf8mb4_0900_ai_ci"
            for table in descriptor["tables"]
        )
        assert re.fullmatch(r"[0-9a-f]{64}", canonical_digest(descriptor))


def test_manifest_has_no_generated_fk_or_check_names() -> None:
    for schema in ("control", "ops"):
        descriptor = json.loads(
            (ROOT / f"schema/descriptor/{schema}-v1.json").read_text(encoding="utf-8")
        )
        names = {row["constraint_name"] for row in descriptor["constraints"]}
        assert not any(
            name.startswith(("asset_", "diagnosis_")) and name.endswith("_ibfk_1")
            for name in names
        )
        assert not any(name.endswith("_chk_1") for name in names)


def test_m1_ci_job_is_required_after_quality_and_keeps_m0() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "  m0-full:" in workflow
    job = workflow.split("  m1-real:\n", 1)[1]
    assert "needs: quality" in job
    assert "runs-on: [self-hosted, linux, x64, m1-real]" in job
    assert "make gate-m1" in job
    assert "if-no-files-found: error" in job
    assert "allow_failure" not in job
