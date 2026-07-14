#!/usr/bin/env python3
"""Write an ignored, profile-specific Milvus auth config without logging secrets."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / ".runtime"
ALLOWED_PROFILES = {"full", "staging", "production"}


def write_config(profile: str, password: str) -> Path:
    if profile not in ALLOWED_PROFILES:
        raise RuntimeError(f"unsupported Milvus profile: {profile}")
    if len(password.strip()) < 8:
        raise RuntimeError("MILVUS_ROOT_PASSWORD is missing or too short")
    RUNTIME_DIR.mkdir(exist_ok=True)
    destination = RUNTIME_DIR / f"milvus-{profile}.yaml"
    destination.write_text(
        "common:\n"
        "  security:\n"
        "    authorizationEnabled: true\n"
        f"    defaultRootPassword: {password}\n",
        encoding="utf-8",
    )
    destination.chmod(0o600)
    return destination


def main() -> int:
    profile = sys.argv[1] if len(sys.argv) == 2 else ""
    try:
        destination = write_config(profile, os.getenv("MILVUS_ROOT_PASSWORD", ""))
    except RuntimeError as error:
        print(f"FAIL: {error}")
        return 1
    print(f"OK: wrote ignored Milvus config for {profile} at {destination.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
