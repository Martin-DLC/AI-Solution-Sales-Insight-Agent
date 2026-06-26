from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from agent.workflow_c.failures import NodeBusinessRuleError, NodeJSONParseError
from agent.workflow_c.retrieval_models import SolutionRetrievalResult
from agent.workflow_c.nodes import (
    FactExtractionNode,
    InformationGapNode,
    SolutionRecommendationNode,
    UnderlyingPainNode,
)
from agent.workflow_c.services import WorkflowServices
from agent.workflow_c.state import AnalysisMode, WorkflowNodeName
from agent.workflow_c.state import (
    ContextSufficiencyResult,
    FactExtractionResult,
    SourceIndexResult,
)
from evaluation.model_benchmark.assertions import (
    BenchmarkAssertionContext,
    evaluate_benchmark_assertions,
)
from evaluation.model_benchmark.dataset import load_node_input_fixture
from evaluation.model_benchmark.models import (
    BenchmarkAssertionResult,
    BenchmarkCaseRunArtifact,
    BenchmarkRunStatus,
    ModelBenchmarkConfig,
    NodeBenchmarkCase,
    NodeBenchmarkRunResult,
    NodeExecutionObservation,
)
from llm.errors import LLMRequestError
from schemas.common_models import EvidenceSourceType
from schemas.input_models import EvaluationCaseInput
from schemas.insight_models import (
    BusinessImpact,
    BuyingIntent,
    ExplicitNeed,
    InformationGap,
    Stakeholder,
    UnderlyingPain,
)
from schemas.solution_models import AIOpportunity


_DEFAULT_NODE_REGISTRY: dict[WorkflowNodeName, Any] = {
    WorkflowNodeName.fact_extraction: FactExtractionNode(),
    WorkflowNodeName.underlying_pain: UnderlyingPainNode(),
    WorkflowNodeName.information_gap: InformationGapNode(),
    WorkflowNodeName.solution_recommendation: SolutionRecommendationNode(),
}


@dataclass(frozen=True)
class BenchmarkCaseExecution:
    artifact: BenchmarkCaseRunArtifact
    call_records: list[Any]


@dataclass(frozen=True)
class _ContextSufficiencyBenchmarkAdapter:
    data: dict[str, Any]
    analysis_mode: AnalysisMode
    blocking_gaps: list[str]

    def model_dump(self, *, mode: str = "json") -> dict[str, Any]:
        return dict(self.data)


class NodeModelBenchmarkExecutor:
    def __init__(
        self,
        *,
        node_registry: dict[WorkflowNodeName, Any] | None = None,
    ) -> None:
        self.node_registry = node_registry or dict(_DEFAULT_NODE_REGISTRY)

    def execute_case(
        self,
        case: NodeBenchmarkCase,
        model_config: ModelBenchmarkConfig,
        *,
        client: Any,
        run_id: str,
    ) -> BenchmarkCaseExecution:
        fixture = load_node_input_fixture(case.input_fixture)
        state = _hydrate_state(dict(fixture["state"]))
        services = WorkflowServices(llm=client)
        node = self.node_registry[case.node_name]

        started_at = datetime.now(UTC)
        execution_error: Exception | None = None
        node_output: dict[str, Any] | None = None
        try:
            node_output = node.run(state, services)
        except Exception as exc:  # noqa: BLE001
            execution_error = exc
        completed_at = datetime.now(UTC)

        call_records = list(getattr(client, "call_records", []))
        call_record = call_records[-1] if call_records else None
        observation = self._build_observation(
            case=case,
            model_config=model_config,
            node_name=case.node_name,
            fixture=fixture,
            state=state,
            execution_error=execution_error,
            node_output=node_output,
            started_at=started_at,
            completed_at=completed_at,
            call_record=call_record,
        )
        assertion_results = evaluate_benchmark_assertions(
            case.assertions,
            BenchmarkAssertionContext(
                fixture=fixture,
                state=state,
                node_output=_dump_node_output(node_output) if node_output is not None else _parsed_payload(call_record),
                observation=observation,
            ),
        )
        run_result = self._build_run_result(
            run_id=run_id,
            case=case,
            model_config=model_config,
            observation=observation,
            assertion_results=assertion_results,
            execution_error=execution_error,
        )
        return BenchmarkCaseExecution(
            artifact=BenchmarkCaseRunArtifact(
                benchmark_case_id=case.benchmark_case_id,
                model_config_id=model_config.config_id,
                node_name=case.node_name,
                observation=observation,
                assertion_results=assertion_results,
                run_result=run_result,
                artifact_dir=None,
            ),
            call_records=call_records,
        )

    def _build_observation(
        self,
        *,
        case: NodeBenchmarkCase,
        model_config: ModelBenchmarkConfig,
        node_name: WorkflowNodeName,
        fixture: dict[str, Any],
        state: dict[str, Any],
        execution_error: Exception | None,
        node_output: dict[str, Any] | None,
        started_at: datetime,
        completed_at: datetime,
        call_record: Any | None,
    ) -> NodeExecutionObservation:
        parsed_payload = _dump_node_output(node_output) if node_output is not None else _parsed_payload(call_record)
        if execution_error is None:
            request_succeeded = True
            json_parse_success = True
            schema_validation_success = True
            business_rule_success = True
            error_type = None
            error_message = None
        elif isinstance(execution_error, LLMRequestError):
            request_succeeded = False
            json_parse_success = False
            schema_validation_success = False
            business_rule_success = False
            error_type = getattr(call_record, "error_type", None) or "request_error"
            error_message = getattr(call_record, "error_message", None) or str(execution_error)
            parsed_payload = None
        elif isinstance(execution_error, NodeJSONParseError):
            request_succeeded = True
            json_parse_success = False
            schema_validation_success = False
            business_rule_success = False
            error_type = "json_parse_error"
            error_message = str(execution_error)
        elif isinstance(execution_error, ValidationError):
            request_succeeded = True
            json_parse_success = True
            schema_validation_success = False
            business_rule_success = False
            error_type = "schema_validation_error"
            error_message = str(execution_error)
        elif isinstance(execution_error, NodeBusinessRuleError):
            request_succeeded = True
            json_parse_success = True
            schema_validation_success = True
            business_rule_success = False
            error_type = "business_rule_error"
            error_message = str(execution_error)
        else:
            request_succeeded = True
            json_parse_success = True
            schema_validation_success = False
            business_rule_success = False
            error_type = execution_error.__class__.__name__
            error_message = str(execution_error)

        if call_record is not None:
            latency_ms = getattr(call_record, "latency_ms", 0)
            usage = getattr(call_record, "usage", None)
        else:
            latency_ms = max(0, int((completed_at - started_at).total_seconds() * 1000))
            usage = None

        return NodeExecutionObservation(
            benchmark_case_id=case.benchmark_case_id,
            model_config_id=model_config.config_id,
            node_name=node_name,
            request_succeeded=request_succeeded,
            json_parse_success=json_parse_success,
            schema_validation_success=schema_validation_success,
            business_rule_success=business_rule_success,
            evidence_reference_valid=_evidence_reference_valid(node_name, state, parsed_payload),
            candidate_boundary_valid=_candidate_boundary_valid(node_name, state, parsed_payload),
            parsed_output=parsed_payload,
            latency_ms=latency_ms,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            total_tokens=getattr(usage, "total_tokens", None),
            estimated_cost=None,
            error_type=error_type,
            error_message=error_message,
        )

    def _build_run_result(
        self,
        *,
        run_id: str,
        case: NodeBenchmarkCase,
        model_config: ModelBenchmarkConfig,
        observation: NodeExecutionObservation,
        assertion_results: list[BenchmarkAssertionResult],
        execution_error: Exception | None,
    ) -> NodeBenchmarkRunResult:
        passed = execution_error is None and all(result.passed for result in assertion_results)
        if isinstance(execution_error, LLMRequestError):
            status = BenchmarkRunStatus.request_error
            error_type = observation.error_type or "request_error"
            error_message = observation.error_message
        elif passed:
            status = BenchmarkRunStatus.passed
            error_type = None
            error_message = None
        else:
            status = BenchmarkRunStatus.failed
            if execution_error is None:
                failed_result = next((result for result in assertion_results if not result.passed), None)
                error_type = "assertion_failure"
                error_message = failed_result.failure_reason if failed_result is not None else "Benchmark assertion failed."
            else:
                error_type = observation.error_type
                error_message = observation.error_message
        return NodeBenchmarkRunResult(
            run_id=run_id,
            benchmark_case_id=case.benchmark_case_id,
            model_config_id=model_config.config_id,
            node_name=case.node_name,
            status=status,
            json_parse_success=observation.json_parse_success,
            schema_validation_success=observation.schema_validation_success,
            business_rule_success=observation.business_rule_success,
            evidence_reference_valid=observation.evidence_reference_valid,
            candidate_boundary_valid=observation.candidate_boundary_valid,
            assertion_pass_count=sum(1 for result in assertion_results if result.passed),
            assertion_fail_count=sum(1 for result in assertion_results if not result.passed),
            blocking_failure_count=sum(
                1 for result in assertion_results if not result.passed and result.blocking
            ),
            latency_ms=observation.latency_ms,
            prompt_tokens=observation.prompt_tokens,
            completion_tokens=observation.completion_tokens,
            total_tokens=observation.total_tokens,
            estimated_cost=observation.estimated_cost,
            error_type=error_type,
            error_message=error_message,
        )


def _parsed_payload(call_record: Any | None) -> dict[str, Any] | None:
    if call_record is None:
        return None
    parsed_json = getattr(call_record, "parsed_json", None)
    return parsed_json if isinstance(parsed_json, dict) else None


def _dump_node_output(node_output: dict[str, Any]) -> dict[str, Any]:
    dumped: dict[str, Any] = {}
    for key, value in node_output.items():
        if hasattr(value, "model_dump"):
            dumped[key] = value.model_dump(mode="json")
        elif isinstance(value, list):
            dumped[key] = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in value
            ]
        else:
            dumped[key] = value
    return dumped


def _hydrate_state(state: dict[str, Any]) -> dict[str, Any]:
    hydrated = dict(state)
    if isinstance(hydrated.get("validated_case"), dict):
        hydrated["validated_case"] = EvaluationCaseInput.model_validate(hydrated["validated_case"])
    if isinstance(hydrated.get("source_index"), dict):
        _normalize_benchmark_solution_sources(hydrated)
        hydrated["source_index"] = SourceIndexResult.model_validate(hydrated["source_index"])
    if isinstance(hydrated.get("fact_extraction"), dict):
        hydrated["fact_extraction"] = FactExtractionResult.model_validate(hydrated["fact_extraction"])
    if isinstance(hydrated.get("context_sufficiency"), dict):
        try:
            hydrated["context_sufficiency"] = ContextSufficiencyResult.model_validate(
                hydrated["context_sufficiency"]
            )
        except ValidationError:
            context_data = hydrated["context_sufficiency"]
            hydrated["context_sufficiency"] = _ContextSufficiencyBenchmarkAdapter(
                data=context_data,
                analysis_mode=AnalysisMode(context_data["analysis_mode"]),
                blocking_gaps=list(context_data.get("blocking_gaps", [])),
            )
    if isinstance(hydrated.get("retrieved_solutions"), dict):
        hydrated["retrieved_solutions"] = SolutionRetrievalResult.model_validate(
            hydrated["retrieved_solutions"]
        )
    _hydrate_list(hydrated, "explicit_needs", ExplicitNeed)
    _hydrate_list(hydrated, "underlying_pains", UnderlyingPain)
    _hydrate_list(hydrated, "business_impacts", BusinessImpact)
    _hydrate_list(hydrated, "stakeholder_map", Stakeholder)
    _hydrate_list(hydrated, "information_gaps", InformationGap)
    _hydrate_list(hydrated, "ai_opportunities", AIOpportunity)
    if isinstance(hydrated.get("buying_intent"), dict):
        hydrated["buying_intent"] = BuyingIntent.model_validate(hydrated["buying_intent"])
    return hydrated


def _hydrate_list(
    state: dict[str, Any],
    field_name: str,
    model_type: type[Any],
) -> None:
    values = state.get(field_name)
    if isinstance(values, list):
        state[field_name] = [
            model_type.model_validate(value) if isinstance(value, dict) else value
            for value in values
        ]


def _normalize_benchmark_solution_sources(state: dict[str, Any]) -> None:
    source_index = state.get("source_index")
    validated_case = state.get("validated_case")
    if not isinstance(source_index, dict) or validated_case is None:
        return
    available_solutions = set(getattr(validated_case, "available_solution_library", []))
    if not available_solutions:
        return
    items = source_index.get("items")
    if not isinstance(items, list):
        return
    normalized_items: list[Any] = []
    changed = False
    existing_solution_titles: set[str] = set()
    for item in items:
        if isinstance(item, dict) and item.get("source_type") == EvidenceSourceType.solution_library.value:
            title = item.get("title")
            if isinstance(title, str):
                existing_solution_titles.add(title)
                if title in available_solutions and item.get("content") != title:
                    item = dict(item)
                    item["content"] = title
                    changed = True
        normalized_items.append(item)
    next_order = len(normalized_items) + 1
    for solution_name in getattr(validated_case, "available_solution_library", []):
        if solution_name in existing_solution_titles:
            continue
        normalized_items.append(
            {
                "source_id": f"SOL-BENCH-{next_order:02d}",
                "source_type": EvidenceSourceType.solution_library.value,
                "source_order": next_order,
                "title": solution_name,
                "content": solution_name,
                "verified": True,
            }
        )
        next_order += 1
        changed = True
    if changed:
        source_index["items"] = normalized_items
        source_index["source_count"] = len(normalized_items)


def _evidence_reference_valid(
    node_name: WorkflowNodeName,
    state: dict[str, Any],
    parsed_payload: dict[str, Any] | None,
) -> bool:
    if node_name not in {WorkflowNodeName.fact_extraction, WorkflowNodeName.underlying_pain}:
        return True
    if parsed_payload is None:
        return False

    source_index = _as_dict(state.get("source_index"))
    allowed_source_ids = {
        item.get("source_id")
        for item in source_index.get("items", [])
        if isinstance(item, dict)
    }
    allowed_source_types = {
        item.get("source_id"): item.get("source_type")
        for item in source_index.get("items", [])
        if isinstance(item, dict)
    }
    if node_name is WorkflowNodeName.fact_extraction:
        payload = _as_dict(parsed_payload.get("fact_extraction") or parsed_payload)
        items = payload.get("facts", [])
    else:
        items = parsed_payload.get("underlying_pains", [])
    return _all_evidence_references_valid(items, allowed_source_ids, allowed_source_types)


def _candidate_boundary_valid(
    node_name: WorkflowNodeName,
    state: dict[str, Any],
    parsed_payload: dict[str, Any] | None,
) -> bool:
    if node_name is not WorkflowNodeName.solution_recommendation:
        return True
    if parsed_payload is None:
        return False

    retrieved_solutions = _as_dict(state.get("retrieved_solutions"))
    candidate_by_solution_id = {
        candidate.get("solution_id"): candidate
        for candidate in retrieved_solutions.get("candidates", [])
        if isinstance(candidate, dict)
    }
    source_id_by_solution_id = {
        candidate.get("solution_id"): candidate.get("source_id")
        for candidate in retrieved_solutions.get("candidates", [])
        if isinstance(candidate, dict)
    }
    recommendations = parsed_payload.get("solution_recommendations", [])
    for recommendation in recommendations:
        if not isinstance(recommendation, dict):
            return False
        solution_id = recommendation.get("solution_id")
        candidate = candidate_by_solution_id.get(solution_id)
        if candidate is None:
            return False
        candidate_source_id = source_id_by_solution_id.get(solution_id)
        knowledge_references = recommendation.get("knowledge_references", [])
        if candidate_source_id is None or not isinstance(knowledge_references, list) or not knowledge_references:
            return False
        if not any(
            isinstance(reference, dict)
            and reference.get("source_type") == EvidenceSourceType.solution_library.value
            and reference.get("source_id") == candidate_source_id
            for reference in knowledge_references
        ):
            return False
    return True


def _all_evidence_references_valid(
    items: list[Any],
    allowed_source_ids: set[Any],
    allowed_source_types: dict[Any, Any],
) -> bool:
    for item in items:
        if not isinstance(item, dict):
            return False
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list) or not evidence:
            return False
        for reference in evidence:
            if not isinstance(reference, dict):
                return False
            source_id = reference.get("source_id")
            source_type = reference.get("source_type")
            if source_id not in allowed_source_ids:
                return False
            if allowed_source_types.get(source_id) != source_type:
                return False
    return True


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    return {}
