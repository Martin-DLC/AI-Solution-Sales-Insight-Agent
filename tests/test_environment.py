import subprocess
import sys
from pathlib import Path


def test_python_version_is_supported() -> None:
    assert sys.version_info.major == 3
    assert sys.version_info.minor >= 11


def test_run_entrypoint_executes() -> None:
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(project_root / "run.py")],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "AI Solution Sales Insight Agent" in result.stdout
    assert "Environment ready" in result.stdout

