from __future__ import annotations

import json
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from evaluation.baselines.models import (
    BaselineArchitecture,
    BaselineRunStatus,
    StructuredBaselineRunRecord,
)
from evaluation.baselines.prompt_loader import (
    calculate_messages_sha256,
    render_baseline_b_messages,
)
from llm import LLMClient, LLMConfig, LLMUsage
from llm.errors import LLMJSONDecodeError
from schemas import EvaluationCaseInput, SalesInsightReport


class BaselineBRunner:
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
        prompt_version: str = "baseline_b_v1",
    ) -> StructuredBaselineRunRecord:
        started_at = datetime.now(UTC)
        run_id = self._generate_run_id(case.case_id, started_at)
        output_directory = self.output_root / run_id
        output_directory.mkdir(parents=True, exist_ok=False)

        input_file = output_directory / "input_case.json"
        system_prompt_file = output_directory / "system_prompt.txt"
        user_prompt_file = output_directory / "user_prompt.txt"
        raw_response_file = output_directory / "raw_response.json"
        raw_response_text_file = output_directory / "raw_response.txt"
        parsed_report_file = output_directory / "parsed_report.json"
        validation_error_file = output_directory / "validation_error.json"
        json_parse_error_file = output_directory / "json_parse_error.json"
        metadata_file = output_directory / "run_metadata.json"

        input_file.write_text(
            json.dumps(case.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        system_message, user_message = render_baseline_b_messages(case, version=prompt_version)
        system_prompt_file.write_text(system_message.content, encoding="utf-8")
        user_prompt_file.write_text(user_message.content, encoding="utf-8")
        messages = [system_message, user_message]
        prompt_sha256 = calculate_messages_sha256(messages)
        git_commit = _read_git_commit()

        try:
            response = self.llm_client.complete_json(messages)
            raw_response_file.write_text(response.content, encoding="utf-8")
            report = SalesInsightReport.model_validate(response.parsed_json)
        except LLMJSONDecodeError as exc:
            completed_at = datetime.now(UTC)
            raw_response_text_file.write_text(exc.raw_content, encoding="utf-8")
            json_error_payload = {
                "error_type": "invalid_json",
                "content_length": exc.content_length,
                "json_error_message": exc.json_error_message,
                "json_error_position": exc.json_error_position,
                "case_id": case.case_id,
                "schema_version": "1.0",
            }
            json_parse_error_file.write_text(
                json.dumps(json_error_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            record = self._failed_record(
                run_id=run_id,
                case=case,
                prompt_version=prompt_version,
                prompt_sha256=prompt_sha256,
                started_at=started_at,
                completed_at=completed_at,
                usage=LLMUsage(),
                output_directory=output_directory,
                input_file=input_file,
                system_prompt_file=system_prompt_file,
                user_prompt_file=user_prompt_file,
                raw_response_file=raw_response_text_file,
                validation_error_file=None,
                json_parse_error_file=json_parse_error_file,
                error_type="invalid_json",
                error_message=self._safe_error_message(exc),
                git_commit=git_commit,
            )
            _write_metadata(metadata_file, record)
            return record
        except ValidationError as exc:
            completed_at = datetime.now(UTC)
            validation_payload = {
                "error_count": len(exc.errors()),
                "errors": exc.errors(),
                "schema_version": "1.0",
                "case_id": case.case_id,
            }
            validation_error_file.write_text(
                json.dumps(validation_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            record = self._failed_record(
                run_id=run_id,
                case=case,
                prompt_version=prompt_version,
                prompt_sha256=prompt_sha256,
                started_at=started_at,
                completed_at=completed_at,
                usage=locals().get("response", None).usage if "response" in locals() else LLMUsage(),
                output_directory=output_directory,
                input_file=input_file,
                system_prompt_file=system_prompt_file,
                user_prompt_file=user_prompt_file,
                raw_response_file=raw_response_file if raw_response_file.exists() else None,
                validation_error_file=validation_error_file,
                json_parse_error_file=None,
                error_type="schema_validation",
                error_message=self._safe_error_message(exc),
                git_commit=git_commit,
            )
            _write_metadata(metadata_file, record)
            return record
        except Exception as exc:
            completed_at = datetime.now(UTC)
            record = self._failed_record(
                run_id=run_id,
                case=case,
                prompt_version=prompt_version,
                prompt_sha256=prompt_sha256,
                started_at=started_at,
                completed_at=completed_at,
                usage=LLMUsage(),
                output_directory=output_directory,
                input_file=input_file,
                system_prompt_file=system_prompt_file,
                user_prompt_file=user_prompt_file,
                raw_response_file=raw_response_file if raw_response_file.exists() else None,
                validation_error_file=None,
                json_parse_error_file=None,
                error_type=exc.__class__.__name__,
                error_message=self._safe_error_message(exc),
                git_commit=git_commit,
            )
            _write_metadata(metadata_file, record)
            return record

        parsed_report_file.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        completed_at = datetime.now(UTC)
        record = StructuredBaselineRunRecord(
            run_id=run_id,
            architecture=BaselineArchitecture.B,
            case_id=case.case_id,
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
            schema_version="1.0",
            model=response.model,
            provider=self.config.provider,
            started_at=started_at,
            completed_at=completed_at,
            latency_ms=response.latency_ms,
            status=BaselineRunStatus.success,
            usage=response.usage,
            output_directory=str(output_directory),
            input_file=str(input_file),
            system_prompt_file=str(system_prompt_file),
            user_prompt_file=str(user_prompt_file),
            raw_response_file=str(raw_response_file),
            parsed_report_file=str(parsed_report_file),
            validation_error_file=None,
            json_parse_error_file=None,
            error_type=None,
            error_message=None,
            git_commit=git_commit,
        )
        _write_metadata(metadata_file, record)
        return record

    def _failed_record(
        self,
        *,
        run_id: str,
        case: EvaluationCaseInput,
        prompt_version: str,
        prompt_sha256: str,
        started_at: datetime,
        completed_at: datetime,
        usage: LLMUsage,
        output_directory: Path,
        input_file: Path,
        system_prompt_file: Path,
        user_prompt_file: Path,
        raw_response_file: Path | None,
        validation_error_file: Path | None,
        json_parse_error_file: Path | None,
        error_type: str,
        error_message: str,
        git_commit: str | None,
    ) -> StructuredBaselineRunRecord:
        return StructuredBaselineRunRecord(
            run_id=run_id,
            architecture=BaselineArchitecture.B,
            case_id=case.case_id,
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
            schema_version="1.0",
            model=self.config.model,
            provider=self.config.provider,
            started_at=started_at,
            completed_at=completed_at,
            latency_ms=max(0, int((completed_at - started_at).total_seconds() * 1000)),
            status=BaselineRunStatus.failed,
            usage=usage,
            output_directory=str(output_directory),
            input_file=str(input_file),
            system_prompt_file=str(system_prompt_file),
            user_prompt_file=str(user_prompt_file),
            raw_response_file=str(raw_response_file) if raw_response_file is not None else None,
            parsed_report_file=None,
            validation_error_file=str(validation_error_file) if validation_error_file is not None else None,
            json_parse_error_file=str(json_parse_error_file) if json_parse_error_file is not None else None,
            error_type=error_type,
            error_message=error_message,
            git_commit=git_commit,
        )

    def _safe_error_message(self, error: Exception) -> str:
        message = str(error) or error.__class__.__name__
        secret = self.config.api_key.get_secret_value()
        if secret:
            message = message.replace(secret, "[REDACTED]")
        return message

    @staticmethod
    def _generate_run_id(case_id: str, started_at: datetime) -> str:
        timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
        return f"B-{case_id}-{timestamp}-{secrets.token_hex(4)}"


def _write_metadata(path: Path, record: StructuredBaselineRunRecord) -> None:
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
