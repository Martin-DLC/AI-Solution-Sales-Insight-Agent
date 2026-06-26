from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import secrets
from pathlib import Path
from typing import Any

from evaluation.model_benchmark.clients import BenchmarkClientFactory
from evaluation.model_benchmark.dataset import validate_node_benchmark_dataset
from evaluation.model_benchmark.executor import NodeModelBenchmarkExecutor
from evaluation.model_benchmark.metrics import summarize_node_model_results
from evaluation.model_benchmark.models import (
    BenchmarkExecutionMode,
    BenchmarkRunManifest,
    BenchmarkRunReport,
    BenchmarkRunStatus,
    ModelBenchmarkConfig,
    NodeBenchmarkCase,
    NodeBenchmarkRunResult,
    ThinkingMode,
)
from evaluation.model_benchmark.pricing import estimate_request_cost, get_pricing_profile
from evaluation.model_benchmark.storage import write_benchmark_run_report


@dataclass(frozen=True)
class BenchmarkPlan:
    selected_case_count: int
    selected_model_count: int
    planned_run_count: int
    cases_per_node: dict[str, int]
    source_case_ids: list[str]


def format_benchmark_plan(plan: BenchmarkPlan) -> str:
    lines = [
        "Node Model Benchmark Plan",
        f"  Selected cases: {plan.selected_case_count}",
        f"  Selected models: {plan.selected_model_count}",
        f"  Planned runs: {plan.planned_run_count}",
        "  Cases per node:",
    ]
    for node_name, count in sorted(plan.cases_per_node.items()):
        lines.append(f"    - {node_name}: {count}")
    lines.append(f"  Source cases: {', '.join(plan.source_case_ids)}")
    return "\n".join(lines)


class NodeModelBenchmarkRunner:
    def __init__(
        self,
        *,
        cases: list[NodeBenchmarkCase],
        model_configs: list[ModelBenchmarkConfig],
        client_factory: BenchmarkClientFactory,
        output_root: str | Path = "data/runtime/model_benchmark_runs",
        node_registry: dict[Any, Any] | None = None,
        capture_debug_artifacts: bool = True,
    ) -> None:
        self.cases = cases
        self.model_configs = model_configs
        self.client_factory = client_factory
        self.output_root = Path(output_root)
        self.capture_debug_artifacts = capture_debug_artifacts
        self.executor = NodeModelBenchmarkExecutor(node_registry=node_registry)

    def plan(self) -> BenchmarkPlan:
        cases_per_node: dict[str, int] = defaultdict(int)
        source_case_ids: list[str] = []
        for case in self.cases:
            cases_per_node[case.node_name.value] += 1
            if case.source_case_id not in source_case_ids:
                source_case_ids.append(case.source_case_id)
        return BenchmarkPlan(
            selected_case_count=len(self.cases),
            selected_model_count=len(self.model_configs),
            planned_run_count=len(self.cases) * len(self.model_configs),
            cases_per_node=dict(cases_per_node),
            source_case_ids=source_case_ids,
        )

    def validate(self, project_root: str | Path) -> dict[str, Any]:
        validate_node_benchmark_dataset(cases=self.cases, project_root=project_root)
        return {
            "total_cases": len(self.cases),
            "total_models": len(self.model_configs),
            "planned_runs": len(self.cases) * len(self.model_configs),
        }

    def run(
        self,
        *,
        case_ids: list[str] | None = None,
        model_config_ids: list[str] | None = None,
        fail_fast: bool = False,
        execution_mode: BenchmarkExecutionMode = BenchmarkExecutionMode.replay,
        max_budget_cny: Decimal | None = None,
        live_confirmed: bool = False,
        max_unknown_cost_runs: int = 1,
    ) -> BenchmarkRunReport:
        execution_mode = BenchmarkExecutionMode(execution_mode)
        selected_cases = self._filter_cases(case_ids)
        selected_models = self._filter_model_configs(model_config_ids)
        started_at = datetime.now(UTC)
        run_id = self._generate_run_id(started_at)

        run_results: list[NodeBenchmarkRunResult] = []
        case_artifacts: list[tuple[Any, list[Any]]] = []
        accumulated_cost = Decimal("0")
        unknown_cost_run_count = 0
        stopped_by_budget = False
        stop_reason: str | None = None

        for case in selected_cases:
            for model_config in selected_models:
                if max_budget_cny is not None and accumulated_cost >= max_budget_cny:
                    stopped_by_budget = True
                    stop_reason = "budget"
                    break
                if execution_mode is BenchmarkExecutionMode.live and unknown_cost_run_count > max_unknown_cost_runs:
                    stop_reason = "unknown_cost_limit"
                    break
                client = self.client_factory(model_config, case)
                execution = self.executor.execute_case(
                    case,
                    model_config,
                    client=client,
                    run_id=self._case_run_id(run_id, case, model_config),
                )
                artifact_dir = self._artifact_dir(run_id, execution.artifact)
                artifact = execution.artifact.model_copy(
                    update={
                        "artifact_dir": str(artifact_dir),
                        "observation": self._annotate_observation(
                            execution.artifact.observation,
                            model_config=model_config,
                            call_records=execution.call_records,
                        ),
                    }
                )
                artifact = artifact.model_copy(
                    update={
                        "run_result": self._annotate_run_result(
                            artifact.run_result,
                            model_config=model_config,
                            call_records=execution.call_records,
                        )
                    }
                )
                run_results.append(artifact.run_result)
                case_artifacts.append((artifact, execution.call_records))
                if execution_mode is BenchmarkExecutionMode.live:
                    if artifact.run_result.estimated_cost is None:
                        unknown_cost_run_count += 1
                    else:
                        accumulated_cost += artifact.run_result.estimated_cost
                if fail_fast and artifact.run_result.status is not BenchmarkRunStatus.passed:
                    stop_reason = "fail_fast"
                    break
            if fail_fast and run_results and run_results[-1].status is not BenchmarkRunStatus.passed:
                break
            if stopped_by_budget:
                break
            if stop_reason == "unknown_cost_limit":
                break

        completed_at = datetime.now(UTC)
        manifest = BenchmarkRunManifest(
            run_id=run_id,
            started_at=started_at,
            completed_at=completed_at,
            execution_mode=execution_mode,
            selected_case_count=len(selected_cases),
            selected_model_count=len(selected_models),
            planned_run_count=len(selected_cases) * len(selected_models),
            completed_run_count=len(run_results),
            passed_count=sum(1 for result in run_results if result.status is BenchmarkRunStatus.passed),
            failed_count=sum(1 for result in run_results if result.status is BenchmarkRunStatus.failed),
            request_error_count=sum(
                1 for result in run_results if result.status is BenchmarkRunStatus.request_error
            ),
            provider_names=_unique_preserve_order([config.provider for config in selected_models]),
            pricing_snapshot_ids=_unique_preserve_order(
                [config.pricing_profile_id for config in selected_models if config.pricing_profile_id]
            ),
            max_budget_cny=max_budget_cny,
            estimated_cost_cny=accumulated_cost if execution_mode is BenchmarkExecutionMode.live else None,
            unknown_cost_run_count=unknown_cost_run_count if execution_mode is BenchmarkExecutionMode.live else 0,
            stopped_by_budget=stopped_by_budget,
            stop_reason=stop_reason,
            live_confirmed=live_confirmed,
            selected_model_details=[
                {
                    "config_id": config.config_id,
                    "provider": config.provider,
                    "model": config.model,
                    "tier": config.tier.value,
                    "thinking_mode": config.thinking_mode.value,
                    "reasoning_effort": config.reasoning_effort.value if config.reasoning_effort else None,
                }
                for config in selected_models
            ],
            capture_debug_artifacts=self.capture_debug_artifacts,
            output_directory=str(Path(self.output_root) / run_id),
        )

        summaries = []
        grouped_results: dict[tuple[str, str], list[NodeBenchmarkRunResult]] = defaultdict(list)
        for result in run_results:
            grouped_results[(result.node_name.value, result.model_config_id)].append(result)
        for results in grouped_results.values():
            summaries.append(summarize_node_model_results(results))

        report = BenchmarkRunReport(
            manifest=manifest,
            model_configs=selected_models,
            selected_cases=selected_cases,
            run_results=run_results,
            summaries=summaries,
            case_artifacts=[artifact for artifact, _ in case_artifacts],
        )
        root = write_benchmark_run_report(
            output_root=self.output_root,
            manifest=manifest,
            report=report,
            case_artifacts=case_artifacts,
        )
        report = report.model_copy(
            update={
                "manifest": manifest.model_copy(update={"output_directory": str(root)}),
            }
        )
        return report

    def _annotate_observation(self, observation: Any, *, model_config: ModelBenchmarkConfig, call_records: list[Any]) -> Any:
        return observation.model_copy(
            update={
                "estimated_cost": self._estimate_cost(model_config, call_records),
                "model": model_config.model,
                "thinking_mode": model_config.thinking_mode,
            }
        )

    def _annotate_run_result(self, run_result: NodeBenchmarkRunResult, *, model_config: ModelBenchmarkConfig, call_records: list[Any]) -> NodeBenchmarkRunResult:
        return run_result.model_copy(update={"estimated_cost": self._estimate_cost(model_config, call_records)})

    @staticmethod
    def _estimate_cost(model_config: ModelBenchmarkConfig, call_records: list[Any]) -> Decimal | None:
        if not model_config.pricing_profile_id or not call_records:
            return None
        usage = getattr(call_records[-1], "usage", None)
        if usage is None:
            return None
        return estimate_request_cost(
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            pricing_profile=get_pricing_profile(model_config.pricing_profile_id),
        )

    def _filter_cases(self, case_ids: list[str] | None) -> list[NodeBenchmarkCase]:
        if not case_ids:
            return list(self.cases)
        selected = [case for case in self.cases if case.benchmark_case_id in set(case_ids)]
        if not selected:
            raise ValueError("No benchmark cases matched the requested filters.")
        return selected

    def _filter_model_configs(self, model_config_ids: list[str] | None) -> list[ModelBenchmarkConfig]:
        if not model_config_ids:
            return list(self.model_configs)
        selected = [config for config in self.model_configs if config.config_id in set(model_config_ids)]
        if not selected:
            raise ValueError("No benchmark model configs matched the requested filters.")
        return selected

    @staticmethod
    def _generate_run_id(started_at: datetime) -> str:
        timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
        return f"MB-{timestamp}-{secrets.token_hex(4)}"

    @staticmethod
    def _case_run_id(run_id: str, case: NodeBenchmarkCase, model_config: ModelBenchmarkConfig) -> str:
        return f"{run_id}:{case.benchmark_case_id}:{model_config.config_id}:{case.node_name.value}"

    def _artifact_dir(
        self,
        run_id: str,
        artifact: Any,
    ) -> Path:
        return (
            Path(self.output_root)
            / run_id
            / "cases"
            / artifact.benchmark_case_id
            / artifact.model_config_id
            / artifact.node_name.value
        )


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
