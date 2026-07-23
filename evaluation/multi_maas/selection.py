from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from evaluation.multi_maas.models import MULTI_MAAS_BOUNDARY_NOTE, MultiMaaSEvaluationResult
from schemas.common_models import StrictBaseModel


DEFAULT_SELECTION_POLICY_PATH = Path("config/maas_selection_policies.yaml")
SELECTION_BOUNDARY_NOTE = (
    "Provider selection is evaluation-only; skipped and dry-run data cannot establish model quality, "
    "fallback provider recommendation is not production routing, not_verified is not completed integration, "
    "and estimated cost is not real billing."
)


class ProviderSelectionPolicy(StrictBaseModel):
    policy_name: str
    mode: str
    primary_selection_rules: str
    fallback_selection_rules: str
    stop_conditions: str
    human_review_conditions: str
    metric_weights: dict[str, float] = Field(default_factory=dict)
    boundary_note: str
    not_production_routing: bool = True
    recommendations_only: bool = True


class ProviderSelectionCandidate(StrictBaseModel):
    provider_name: str
    model_name: str
    verification_status: str
    status: str
    schema_valid_rate: float | None = None
    provider_error_rate: float | None = None
    timeout_rate: float | None = None
    average_latency_ms: float | None = None
    average_estimated_cost: float | None = None
    usage_available_rate: float | None = None
    human_review_trigger_rate: float | None = None
    fallback_recommended_count: int = 0
    retry_recommended_count: int = 0
    score: float | None = None
    ranking_note: str = SELECTION_BOUNDARY_NOTE


RecommendationStatus = Literal[
    "recommended",
    "insufficient_data",
    "skipped_all_targets",
    "no_fallback_available",
]


class ProviderSelectionRecommendation(StrictBaseModel):
    policy_name: str
    primary_provider: str | None = None
    primary_model: str | None = None
    fallback_provider: str | None = None
    fallback_model: str | None = None
    recommendation_status: RecommendationStatus
    selection_reason: str
    fallback_reason: str | None = None
    risk_notes: list[str] = Field(default_factory=list)
    candidate_ranking: list[ProviderSelectionCandidate] = Field(default_factory=list)
    boundary_note: str = SELECTION_BOUNDARY_NOTE
    created_at: str


def build_provider_selection_recommendation(
    results: list[MultiMaaSEvaluationResult],
    *,
    policy_name: str = "conservative_eval_policy",
    policy_path: str | Path = DEFAULT_SELECTION_POLICY_PATH,
) -> ProviderSelectionRecommendation:
    policy = get_selection_policy(policy_name, policy_path)
    candidates = build_selection_candidates(results, policy=policy)
    created_at = datetime.now(UTC).isoformat()
    if not candidates:
        return ProviderSelectionRecommendation(
            policy_name=policy.policy_name,
            recommendation_status="insufficient_data",
            selection_reason="No provider candidates were available.",
            risk_notes=[policy.boundary_note],
            candidate_ranking=[],
            boundary_note=SELECTION_BOUNDARY_NOTE,
            created_at=created_at,
        )
    if all(candidate.status in {"skipped_dry_run", "skipped_missing_api_key"} for candidate in candidates):
        return ProviderSelectionRecommendation(
            policy_name=policy.policy_name,
            recommendation_status="skipped_all_targets",
            selection_reason="All provider targets were skipped or dry-run; no model quality primary can be recommended.",
            fallback_reason="No fallback provider is recommended from skipped/dry-run-only data.",
            risk_notes=[
                "Skipped and dry-run data cannot be used for model quality ranking.",
                policy.boundary_note,
            ],
            candidate_ranking=candidates,
            boundary_note=SELECTION_BOUNDARY_NOTE,
            created_at=created_at,
        )
    eligible = [candidate for candidate in candidates if candidate.status == "success" and candidate.score is not None]
    if not eligible:
        return ProviderSelectionRecommendation(
            policy_name=policy.policy_name,
            recommendation_status="insufficient_data",
            selection_reason="No successful provider results were available for evaluation-only ranking.",
            fallback_reason="No fallback provider can be selected without a successful comparison target.",
            risk_notes=[policy.boundary_note],
            candidate_ranking=candidates,
            boundary_note=SELECTION_BOUNDARY_NOTE,
            created_at=created_at,
        )
    primary = eligible[0]
    fallback = eligible[1] if len(eligible) > 1 else None
    return ProviderSelectionRecommendation(
        policy_name=policy.policy_name,
        primary_provider=primary.provider_name,
        primary_model=primary.model_name,
        fallback_provider=None if fallback is None else fallback.provider_name,
        fallback_model=None if fallback is None else fallback.model_name,
        recommendation_status="recommended" if fallback is not None else "no_fallback_available",
        selection_reason=(
            f"Selected {primary.provider_name}/{primary.model_name} using evaluation-only policy "
            f"{policy.policy_name}; score={primary.score}."
        ),
        fallback_reason=(
            "No eligible fallback candidate was available."
            if fallback is None
            else f"Fallback candidate is {fallback.provider_name}/{fallback.model_name}; score={fallback.score}."
        ),
        risk_notes=[policy.boundary_note],
        candidate_ranking=candidates,
        boundary_note=SELECTION_BOUNDARY_NOTE,
        created_at=created_at,
    )


def build_selection_candidates(
    results: list[MultiMaaSEvaluationResult],
    *,
    policy: ProviderSelectionPolicy,
) -> list[ProviderSelectionCandidate]:
    grouped: dict[tuple[str, str], list[MultiMaaSEvaluationResult]] = {}
    for result in results:
        grouped.setdefault((result.provider_name, result.model_name), []).append(result)
    candidates = [
        _candidate_from_results(provider_results, policy=policy)
        for provider_results in grouped.values()
        if provider_results
    ]
    candidates.sort(key=lambda candidate: candidate.score if candidate.score is not None else float("-inf"), reverse=True)
    return candidates


def load_selection_policies(path: str | Path = DEFAULT_SELECTION_POLICY_PATH) -> list[ProviderSelectionPolicy]:
    return [ProviderSelectionPolicy.model_validate(item) for item in _parse_policy_yaml(Path(path).read_text(encoding="utf-8"))]


def get_selection_policy(
    policy_name: str,
    path: str | Path = DEFAULT_SELECTION_POLICY_PATH,
) -> ProviderSelectionPolicy:
    for policy in load_selection_policies(path):
        if policy.policy_name == policy_name:
            return policy
    raise KeyError(f"Unknown MaaS selection policy: {policy_name}")


def _candidate_from_results(
    provider_results: list[MultiMaaSEvaluationResult],
    *,
    policy: ProviderSelectionPolicy,
) -> ProviderSelectionCandidate:
    first = provider_results[0]
    success_results = [result for result in provider_results if result.status == "success"]
    status = _candidate_status(provider_results)
    schema_valid_rate = _bool_rate([result.schema_valid for result in success_results if result.schema_valid is not None])
    provider_error_rate = _bool_rate([result.status in {"failed", "provider_unavailable"} for result in provider_results])
    timeout_rate = _bool_rate([result.status == "timeout" for result in provider_results])
    average_latency_ms = _average([result.latency_ms for result in success_results])
    usage_available_rate = _bool_rate([result.usage_available for result in success_results])
    human_review_trigger_rate = _bool_rate([result.human_review_triggered for result in provider_results])
    average_estimated_cost = _average_float([_to_float(result.estimated_cost) for result in success_results])
    score = None
    if success_results:
        score = _score_candidate(
            policy=policy,
            schema_valid_rate=schema_valid_rate,
            provider_error_rate=provider_error_rate,
            timeout_rate=timeout_rate,
            average_latency_ms=average_latency_ms,
            average_estimated_cost=average_estimated_cost,
            usage_available_rate=usage_available_rate,
            human_review_trigger_rate=human_review_trigger_rate,
        )
    return ProviderSelectionCandidate(
        provider_name=first.provider_name,
        model_name=first.model_name,
        verification_status=first.verification_status,
        status=status,
        schema_valid_rate=schema_valid_rate,
        provider_error_rate=provider_error_rate,
        timeout_rate=timeout_rate,
        average_latency_ms=average_latency_ms,
        average_estimated_cost=average_estimated_cost,
        usage_available_rate=usage_available_rate,
        human_review_trigger_rate=human_review_trigger_rate,
        fallback_recommended_count=sum(1 for result in provider_results if result.recommended_recovery_action == "fallback"),
        retry_recommended_count=sum(1 for result in provider_results if result.recommended_recovery_action == "retry"),
        score=score,
    )


def _score_candidate(
    *,
    policy: ProviderSelectionPolicy,
    schema_valid_rate: float | None,
    provider_error_rate: float | None,
    timeout_rate: float | None,
    average_latency_ms: float | None,
    average_estimated_cost: float | None,
    usage_available_rate: float | None,
    human_review_trigger_rate: float | None,
) -> float:
    metrics = {
        "schema_valid_rate": schema_valid_rate,
        "provider_error_rate": provider_error_rate,
        "timeout_rate": timeout_rate,
        "average_latency_ms": _normalize_lower_is_better(average_latency_ms),
        "average_estimated_cost": _normalize_lower_is_better(average_estimated_cost),
        "usage_available_rate": usage_available_rate,
        "human_review_trigger_rate": human_review_trigger_rate,
    }
    score = 0.0
    for metric_name, weight in policy.metric_weights.items():
        value = metrics.get(metric_name)
        if value is None:
            continue
        score += weight * value
    return round(score, 6)


def _candidate_status(results: list[MultiMaaSEvaluationResult]) -> str:
    statuses = {result.status for result in results}
    if statuses == {"skipped_dry_run"}:
        return "skipped_dry_run"
    if statuses == {"skipped_missing_api_key"}:
        return "skipped_missing_api_key"
    if "success" in statuses:
        return "success"
    if "timeout" in statuses:
        return "timeout"
    if "provider_unavailable" in statuses:
        return "provider_unavailable"
    if "schema_invalid" in statuses:
        return "schema_invalid"
    return "failed"


def _bool_rate(values: list[bool | None]) -> float | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return round(sum(1 for value in usable if value) / len(usable), 4)


def _average(values: list[int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _average_float(values: list[float | None]) -> float | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return round(sum(usable) / len(usable), 6)


def _normalize_lower_is_better(value: float | None) -> float | None:
    if value is None:
        return None
    if value <= 0:
        return 1.0
    return round(1 / (1 + value), 6)


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_policy_yaml(content: str) -> list[dict[str, Any]]:
    policies: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_map_key: str | None = None
    for raw_line in content.splitlines():
        if not raw_line.strip() or raw_line.strip().startswith("#") or raw_line.strip() == "policies:":
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if line.startswith("- "):
            if current is not None:
                policies.append(current)
            current = {}
            current_map_key = None
            line = line[2:].strip()
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if indent >= 6 and current_map_key:
            current[current_map_key][key] = _parse_scalar(value)
            continue
        if value == "":
            current[key] = {}
            current_map_key = key
            continue
        current[key] = _parse_scalar(value)
        current_map_key = None
    if current is not None:
        policies.append(current)
    return policies


def _parse_scalar(value: str) -> Any:
    if value.casefold() == "true":
        return True
    if value.casefold() == "false":
        return False
    try:
        return float(value) if "." in value or value.startswith("-") else int(value)
    except ValueError:
        return value.strip('"').strip("'")
