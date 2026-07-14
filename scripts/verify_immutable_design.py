#!/usr/bin/env python3
"""Fail closed when the immutable detailed design differs from its frozen hash."""

from __future__ import annotations

import hashlib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = REPOSITORY_ROOT / "docs/immutable/能源设备运维诊断Agent_详细设计.md"
EXPECTED_SHA256 = "c559a530387de5fc1afced506e406967e74c18ed76e659b4b062c2051b615a11"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path = DESIGN_PATH, expected_sha256: str = EXPECTED_SHA256) -> None:
    if not path.is_file():
        raise RuntimeError(f"immutable design is missing: {path}")
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            "immutable design checksum mismatch: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )


def main() -> int:
    try:
        verify()
    except RuntimeError as error:
        print(f"FAIL: {error}")
        return 1
    print(f"OK: immutable design SHA-256 {EXPECTED_SHA256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
