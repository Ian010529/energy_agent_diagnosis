"""验证阶段 3 RAG 离线评估入口。"""

import json
import subprocess
import sys


def test_rag_evaluation_script_outputs_passing_metrics() -> None:
    """离线评估脚本应返回 JSON 指标并通过三类典型告警。"""
    result = subprocess.run(
        [sys.executable, "scripts/evaluate_rag.py"],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)

    assert report["total"] == 3
    assert report["failed"] == 0
    assert report["pass_rate"] == 1.0
