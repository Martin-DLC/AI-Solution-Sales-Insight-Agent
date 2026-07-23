from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from agent.model_providers.openai_compatible import (
    OpenAICompatibleProviderConfig,
    build_openai_compatible_provider,
    load_maas_provider_configs,
)
from agent.recovery.decision import RecoveryDecisionEngine
from agent.recovery.models import ErrorType
from evaluation.multi_maas.models import (
    MULTI_MAAS_BOUNDARY_NOTE,
    MultiMaaSEvaluationCase,
    MultiMaaSEvaluationReport,
    MultiMaaSEvaluationResult,
    MultiMaaSEvaluationSummary,
    ProviderModelTarget,
    ProviderSummary,
)
from evaluation.multi_maas.scoring import score_output


DEFAULT_CASES_PATH = Path("evaluation/multi_maas/cases.jsonl")
DEFAULT_MAAS_CONFIG_PATH = Path("config/maas_providers.yaml")


class MultiMaaSEvaluationRunner:
    def __init__(
        self,
        *,
        cases_path: str | Path = DEFAULT_CASES_PATH,
        config_path: str | Path = DEFAULT_MAAS_CONFIG_PATH,
        recovery_engine: RecoveryDecisionEngine | None = None,
    ) -> None:
        self.cases_path = Path(cases_path)
        self.config_path = Path(config_path)
        self.recovery_engine = recovery_engine or RecoveryDecisionEngine()

    def run(
        self,
        *,
        provider_name: str | None = None,
        model_name: str | None = None,
        dry_run: bool = True,
    ) -> MultiMaaSEvaluationReport:
        created_at = datetime.now(UTC).isoformat()
        run_id = f"multi-maas-eval-{created_at}"
        cases = load_cases(self.cases_path)
        targets = self._resolve_targets(provider_name=provider_name, model_name=model_name, dry_run=dry_run)
        results = [
            self._run_case(run_id=run_id, created_at=created_at, case=case, target=target)
            for target in targets
            for case in cases
        ]
        summary = build_summary(
            run_id=run_id,
            created_at=created_at,
            cases=cases,
            targets=targets,
            results=results,
        )
        return MultiMaaSEvaluationReport(
            run_id=run_id,
            created_at=created_at,
            dry_run=dry_run,
            targets=targets,
            cases=cases,
            summary=summary,
            results=results,
        )

    def _resolve_targets(
        self,
        *,
        provider_name: str | None,
        model_name: str | None,
        dry_run: bool,
    ) -> list[ProviderModelTarget]:
        configs = load_maas_provider_configs(self.config_path)
        if provider_name:
            configs = [config for config in configs if config.provider_name == provider_name]
        if not configs:
            raise KeyError(f"Unknown MaaS provider: {provider_name}")
        return [
            ProviderModelTarget(
                provider_name=config.provider_name,
                model_name=model_name or config.resolved_model_name,
                adapter_type=config.adapter_type,
                verification_status=config.verification_status,
                api_key_env=config.api_key_env,
                dry_run=dry_run,
            )
            for config in configs
        ]

    def _run_case(
        self,
        *,
        run_id: str,
        created_at: str,
        case: MultiMaaSEvaluationCase,
        target: ProviderModelTarget,
    ) -> MultiMaaSEvaluationResult:
        provider = build_openai_compatible_provider(
            target.provider_name,
            path=self.config_path,
            model_name=target.model_name,
        )
        response = provider.generate(case.input_text, dry_run=target.dry_run)
        payload = dict(response.parsed_json)
        provider_status = str(payload.get("status") or "failed")
        status = _normalize_status(provider_status, str(payload.get("error_type") or ""))
        output_text = payload.get("output_text")
        output_text_value = output_text if isinstance(output_text, str) else None
        score = score_output(case, output_text_value) if status == "success" else score_output(case, None)
        error_type = payload.get("error_type")
        recommended = payload.get("recommended_recovery_action")
        if recommended is None and error_type:
            recommended = self._recommended_action(str(error_type))
        human_review = case.risk_level == "high" and status in {"schema_invalid", "provider_unavailable", "timeout", "failed"}
        return MultiMaaSEvaluationResult(
            run_id=run_id,
            case_id=case.case_id,
            provider_name=target.provider_name,
            model_name=target.model_name,
            adapter_type=target.adapter_type,
            verification_status=target.verification_status,
            status=status,
            output_preview=_preview(output_text_value),
            latency_ms=int(payload.get("latency_ms") or 0),
            usage=response.parsed_json.get("usage", {}),
            usage_available=bool(payload.get("usage_available")),
            estimated_cost=response.estimated_cost,
            schema_valid=score.schema_valid,
            expected_fields_present=score.expected_fields_present,
            answer_quality_score=score.answer_quality_score if status == "success" else None,
            evidence_grounding_score=score.evidence_grounding_score if status == "success" else None,
            fallback_triggered=str(recommended) == "fallback",
            human_review_triggered=human_review or str(recommended) == "human_review",
            error_type=str(error_type) if error_type else None,
            error_message=str(payload.get("error_message")) if payload.get("error_message") else None,
            recommended_recovery_action=str(recommended) if recommended else None,
            boundary_note=MULTI_MAAS_BOUNDARY_NOTE,
            created_at=created_at,
        )

    def _recommended_action(self, error_type: str) -> str:
        try:
            return self.recovery_engine.decide(error_type=ErrorType(error_type), current_retry_count=0).decision.value
        except ValueError:
            return self.recovery_engine.decide(error_type=ErrorType.unknown_error, current_retry_count=0).decision.value


def run_multi_maas_evaluation(
    *,
    provider_name: str | None = None,
    model_name: str | None = None,
    cases_path: str | Path = DEFAULT_CASES_PATH,
    config_path: str | Path = DEFAULT_MAAS_CONFIG_PATH,
    dry_run: bool = True,
) -> MultiMaaSEvaluationReport:
    return MultiMaaSEvaluationRunner(cases_path=cases_path, config_path=config_path).run(
        provider_name=provider_name,
        model_name=model_name,
        dry_run=dry_run,
    )


def load_cases(path: str | Path = DEFAULT_CASES_PATH) -> list[MultiMaaSEvaluationCase]:
    cases = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        cases.append(MultiMaaSEvaluationCase.model_validate(json.loads(line)))
    return cases


def build_summary(
    *,
    run_id: str,
    created_at: str,
    cases: list[MultiMaaSEvaluationCase],
    targets: list[ProviderModelTarget],
    results: list[MultiMaaSEvaluationResult],
) -> MultiMaaSEvaluationSummary:
    total_runs = len(results)
    success_count = sum(1 for result in results if result.status == "success")
    skipped_count = sum(1 for result in results if result.status.startswith("skipped"))
    failed_count = total_runs - success_count - skipped_count
    return MultiMaaSEvaluationSummary(
        run_id=run_id,
        created_at=created_at,
        total_cases=len(cases),
        total_targets=len(targets),
        total_runs=total_runs,
        success_count=success_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        schema_valid_rate=_rate([result.schema_valid for result in results if result.status == "success"]),
        usage_available_rate=_bool_rate([result.usage_available for result in results if result.status == "success"]),
        average_latency_ms=_average([result.latency_ms for result in results if result.status == "success"]),
        average_estimated_cost=None,
        provider_error_rate=_bool_rate([result.status in {"failed", "provider_unavailable"} for result in results]),
        timeout_rate=_bool_rate([result.status == "timeout" for result in results]),
        retry_recommended_count=sum(1 for result in results if result.recommended_recovery_action == "retry"),
        fallback_recommended_count=sum(1 for result in results if result.recommended_recovery_action == "fallback"),
        human_review_trigger_count=sum(1 for result in results if result.human_review_triggered),
        provider_summaries=_provider_summaries(results),
    )


def _provider_summaries(results: list[MultiMaaSEvaluationResult]) -> list[ProviderSummary]:
    summaries = []
    grouped: dict[tuple[str, str], list[MultiMaaSEvaluationResult]] = {}
    for result in results:
        grouped.setdefault((result.provider_name, result.model_name), []).append(result)
    for (provider_name, model_name), provider_results in grouped.items():
        total = len(provider_results)
        success = sum(1 for result in provider_results if result.status == "success")
        skipped = sum(1 for result in provider_results if result.status.startswith("skipped"))
        failed = total - success - skipped
        summaries.append(
            ProviderSummary(
                provider_name=provider_name,
                model_name=model_name,
                total_runs=total,
                success_count=success,
                skipped_count=skipped,
                failed_count=failed,
                schema_valid_rate=_rate(
                    [result.schema_valid for result in provider_results if result.status == "success"]
                ),
                usage_available_rate=_bool_rate(
                    [result.usage_available for result in provider_results if result.status == "success"]
                ),
                average_latency_ms=_average(
                    [result.latency_ms for result in provider_results if result.status == "success"]
                ),
                provider_error_rate=_bool_rate(
                    [result.status in {"failed", "provider_unavailable"} for result in provider_results]
                ),
            )
        )
    return summaries


def _normalize_status(provider_status: str, error_type: str) -> str:
    if provider_status == "success":
        return "success"
    if provider_status == "skipped_dry_run":
        return "skipped_dry_run"
    if provider_status == "skipped_missing_api_key":
        return "skipped_missing_api_key"
    if error_type == "model_timeout":
        return "timeout"
    if error_type == "model_schema_invalid":
        return "schema_invalid"
    if error_type == "model_unavailable":
        return "provider_unavailable"
    return "failed"


def _rate(values: list[bool | None]) -> float | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return round(sum(1 for value in usable if value) / len(usable), 4)


def _bool_rate(values: list[bool]) -> float | None:
    if not values:
        return None
    return round(sum(1 for value in values if value) / len(values), 4)


def _average(values: list[int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _preview(output_text: str | None) -> str | None:
    if output_text is None:
        return None
    return output_text[:240]
