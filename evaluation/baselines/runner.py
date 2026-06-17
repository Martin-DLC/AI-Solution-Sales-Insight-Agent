from __future__ import annotations

import json
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from evaluation.baselines.models import (
    BaselineArchitecture,
    BaselineRunRecord,
    BaselineRunStatus,
)
from evaluation.baselines.prompt_loader import (
    calculate_prompt_sha256,
    render_baseline_a_prompt,
)
from llm import LLMClient, LLMConfig, LLMMessage, LLMRole, LLMUsage
from schemas import EvaluationCaseInput


class BaselineARunner:
    def __init__(
        self,
        llm_client: LLMClient,
        config: LLMConfig,
        output_root: str | Path = "data/runtime/baseline_runs",
    ) -> None:
        self.llm_client = llm_client
        self.config = config
        self.output_root = Path(output_root)

    def run_case(
        self,
        case: EvaluationCaseInput,
        *,
        prompt_version: str = "baseline_a_v1",
    ) -> BaselineRunRecord:
        started_at = datetime.now(UTC)
        run_id = self._generate_run_id(case.case_id, started_at)
        output_directory = self.output_root / run_id
        output_directory.mkdir(parents=True, exist_ok=False)

        input_file = output_directory / "input_case.json"
        prompt_file = output_directory / "rendered_prompt.txt"
        raw_response_file = output_directory / "raw_response.txt"
        metadata_file = output_directory / "run_metadata.json"

        input_file.write_text(
            json.dumps(case.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        prompt = render_baseline_a_prompt(case, version=prompt_version)
        prompt_file.write_text(prompt, encoding="utf-8")
        prompt_sha256 = calculate_prompt_sha256(prompt)
        git_commit = _read_git_commit()

        try:
            response = self.llm_client.complete_text(
                [LLMMessage(role=LLMRole.user, content=prompt)]
            )
        except Exception as exc:
            completed_at = datetime.now(UTC)
            record = BaselineRunRecord(
                run_id=run_id,
                architecture=BaselineArchitecture.A,
                case_id=case.case_id,
                prompt_version=prompt_version,
                prompt_sha256=prompt_sha256,
                model=self.config.model,
                provider=self.config.provider,
                started_at=started_at,
                completed_at=completed_at,
                latency_ms=max(0, int((completed_at - started_at).total_seconds() * 1000)),
                status=BaselineRunStatus.failed,
                usage=LLMUsage(),
                output_directory=str(output_directory),
                input_file=str(input_file),
                prompt_file=str(prompt_file),
                raw_response_file=None,
                error_type=exc.__class__.__name__,
                error_message=self._safe_error_message(exc),
                git_commit=git_commit,
            )
            _write_metadata(metadata_file, record)
            return record

        raw_response_file.write_text(response.content, encoding="utf-8")
        completed_at = datetime.now(UTC)
        record = BaselineRunRecord(
            run_id=run_id,
            architecture=BaselineArchitecture.A,
            case_id=case.case_id,
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
            model=response.model,
            provider=self.config.provider,
            started_at=started_at,
            completed_at=completed_at,
            latency_ms=response.latency_ms,
            status=BaselineRunStatus.success,
            usage=response.usage,
            output_directory=str(output_directory),
            input_file=str(input_file),
            prompt_file=str(prompt_file),
            raw_response_file=str(raw_response_file),
            error_type=None,
            error_message=None,
            git_commit=git_commit,
        )
        _write_metadata(metadata_file, record)
        return record

    def _safe_error_message(self, error: Exception) -> str:
        message = str(error) or error.__class__.__name__
        secret = self.config.api_key.get_secret_value()
        if secret:
            message = message.replace(secret, "[REDACTED]")
        return message

    @staticmethod
    def _generate_run_id(case_id: str, started_at: datetime) -> str:
        timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
        return f"A-{case_id}-{timestamp}-{secrets.token_hex(4)}"


def _write_metadata(path: Path, record: BaselineRunRecord) -> None:
    path.write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _read_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    commit = result.stdout.strip()
    return commit or None
