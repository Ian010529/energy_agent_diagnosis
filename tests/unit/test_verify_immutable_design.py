from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_immutable_design import sha256_file, verify


def test_sha256_file_hashes_raw_bytes(tmp_path: Path) -> None:
    candidate = tmp_path / "design.md"
    candidate.write_bytes(b"immutable\r\nbytes\n")

    assert sha256_file(candidate) == (
        "15903916a185c3f97355f2b07189e63330a6b0cf5d1854c66e5d47dcb858accc"
    )


def test_verify_rejects_mismatch(tmp_path: Path) -> None:
    candidate = tmp_path / "design.md"
    candidate.write_bytes(b"changed")

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        verify(candidate, "0" * 64)


def test_verify_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="is missing"):
        verify(tmp_path / "missing.md", "0" * 64)
