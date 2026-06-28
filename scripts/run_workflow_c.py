from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.workflow_c.failures import redact_secrets  # noqa: E402
from agent.workflow_c.model_routing import (  # noqa: E402
    DEFAULT_MODEL_CONFIGS_PATH,
    DEFAULT_ROUTING_MATRIX_PATH,
    ModelRoutingError,
    RoutedWorkflowLLMClient,
    format_model_routing_plan,
    load_model_routing_policy,
)
from agent.workflow_c.real_llm import RealWorkflowLLMClient  # noqa: E402
from agent.workflow_c.runtime import ArchitectureCRunError, ArchitectureCRunner  # noqa: E402
from dataio.runtime_cases import load_runtime_cases  # noqa: E402
from llm import LLMConfig, create_llm_client  # noqa: E402


DEFAULT_CASES_FILE = PROJECT_ROOT / "data" / "evaluation" / "development_cases.jsonl"
WORKFLOW_VERSION = "c_skeleton_v1"
EXPECTED_LLM_NODES = [
    "fact_extraction",
    "explicit_need",
    "underlying_pain",
    "business_impact",
    "buying_intent",
    "stakeholder",
    "information_gap",
    "ai_opportunity",
    "solution_recommendation",
    "risk",
    "next_best_action",
]
EXPECTED_DETERMINISTIC_NODES = [
    "input_validation",
    "source_indexing",
    "context_sufficiency",
    "solution_retrieval",
    "deal_score",
    "report_composer",
    "final_validation",
    "human_review_gate",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Architecture C workflow.")
    parser.add_argument("--case", default="DEV-01", dest="case_id")
    parser.add_argument("--cases-file", default=str(DEFAULT_CASES_FILE))
    parser.add_argument("--output-root", default="data/runtime/workflow_c_runs")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--model-routing", action="store_true")
    parser.add_argument("--routing-matrix", default=DEFAULT_ROUTING_MATRIX_PATH)
    parser.add_argument("--model-configs", default=DEFAULT_MODEL_CONFIGS_PATH)
    args = parser.parse_args(argv)

    try:
        cases = load_runtime_cases(Path(args.cases_file))
    except Exception as exc:
        print(f"Failed to load runtime cases: {exc}", file=sys.stderr)
        return 1
    case = next((item for item in cases if item.case_id == args.case_id), None)
    if case is None:
        print(f"Case ID not found: {args.case_id}", file=sys.stderr)
        return 1

    routing_policy = None
    if args.model_routing:
        try:
            routing_policy = load_model_routing_policy(
                matrix_path=args.routing_matrix,
                config_path=args.model_configs,
            )
        except ModelRoutingError as exc:
            print(f"Model routing setup failed: {exc}", file=sys.stderr)
            return 1

    if not args.live:
        print(f"Case ID: {case.case_id}")
        print("Architecture: C")
        print(f"Workflow version: {WORKFLOW_VERSION}")
        print(f"Expected LLM nodes: {', '.join(EXPECTED_LLM_NODES)}")
        print(f"Expected deterministic nodes: {', '.join(EXPECTED_DETERMINISTIC_NODES)}")
        if routing_policy is not None:
            print(format_model_routing_plan(routing_policy))
        print("Live model call is disabled. Re-run with --live to continue.")
        return 0

    try:
        config = LLMConfig.from_env()
        llm_client = create_llm_client(config)
        if routing_policy is not None:
            workflow_llm = RoutedWorkflowLLMClient(
                default_client=llm_client,
                default_config=config,
                policy=routing_policy,
            )
        else:
            workflow_llm = RealWorkflowLLMClient(llm_client=llm_client, config=config)
        runner = ArchitectureCRunner(workflow_llm, output_root=args.output_root)
        result = runner.run_case(case)
    except ModelRoutingError as exc:
        print(f"Model routing setup failed: {exc}", file=sys.stderr)
        return 1
    except ArchitectureCRunError as exc:
        metadata = exc.result.metadata
        print(f"Architecture C run failed: {metadata.error_type}: {metadata.error_message}", file=sys.stderr)
        print(f"Output directory: {metadata.output_directory}")
        return 1
    except Exception as exc:
        print(f"Architecture C run failed: {_safe_error_message(exc)}", file=sys.stderr)
        return 1

    metadata = result.metadata
    print(f"Run ID: {metadata.run_id}")
    print(f"Case ID: {metadata.case_id}")
    print(f"Architecture: {metadata.architecture}")
    print(f"Workflow status: {metadata.workflow_status}")
    print(f"Final validation passed: {metadata.final_validation_passed}")
    print(f"Final report available: {metadata.final_report_available}")
    print(f"LLM calls: {metadata.llm_call_count}")
    print(f"Latency: {metadata.latency_ms} ms")
    print(f"Prompt tokens: {metadata.prompt_tokens}")
    print(f"Completion tokens: {metadata.completion_tokens}")
    print(f"Total tokens: {metadata.total_tokens}")
    print(f"Configured model: {metadata.configured_model}")
    print(f"Response models: {', '.join(metadata.response_models)}")
    print(f"Model routing enabled: {metadata.model_routing_enabled}")
    print(f"Fallback calls: {metadata.fallback_call_count}")
    print(f"Models used: {', '.join(metadata.models_used)}")
    print(f"Output directory: {metadata.output_directory}")
    print(f"Run status: {metadata.status.value}")
    return 0


def _safe_error_message(error: Exception) -> str:
    message = redact_secrets(str(error) or error.__class__.__name__)
    if len(message) > 1000:
        return f"{message[:997]}..."
    return message


if __name__ == "__main__":
    raise SystemExit(main())
