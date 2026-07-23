import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_module_boundaries() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_module_boundaries.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
