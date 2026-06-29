from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_lexical_baseline_files_exist_and_are_json_serializable() -> None:
    config = json.loads(Path("data/evaluation/retrieval/lexical_baseline_config.v1.json").read_text(encoding="utf-8"))
    summary = json.loads(Path("data/evaluation/retrieval/lexical_baseline_summary.v1.json").read_text(encoding="utf-8"))
    results = [
        json.loads(line)
        for line in Path("data/evaluation/retrieval/lexical_baseline_results.v1.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert config["baseline_version"] == "lexical_v1"
    assert summary["case_count"] == 16
    assert len(results) == 16


def test_lexical_baseline_check_mode_succeeds() -> None:
    completed = subprocess.run(
        [".venv/bin/python", "scripts/run_lexical_retrieval_baseline.py", "--check"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "up to date" in completed.stdout
