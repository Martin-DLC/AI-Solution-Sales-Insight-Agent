from __future__ import annotations

import argparse
import json
import platform
from typing import Any

from agent import SolutionInsightRequest, SolutionInsightService


PROJECT_NAME = "AI Solution Sales Insight Agent"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=PROJECT_NAME)
    subparsers = parser.add_subparsers(dest="command")

    insight = subparsers.add_parser("solution-insight", help="Generate a structured solution insight response.")
    insight.add_argument("--query", required=True)
    insight.add_argument("--industry")
    insight.add_argument("--company-size")
    insight.add_argument("--current-system", action="append", dest="current_systems", default=[])
    insight.add_argument("--target-goal")
    insight.add_argument("--constraint", action="append", dest="constraints", default=[])
    insight.add_argument("--shadow", action="store_true")
    insight.add_argument("--llm-mode", choices=["deterministic", "auto"], default="deterministic")

    args = parser.parse_args(argv)
    if args.command != "solution-insight":
        print(PROJECT_NAME)
        print(f"Python {platform.python_version()}")
        print("Environment ready")
        return 0

    request = SolutionInsightRequest(
        user_query=args.query,
        industry=args.industry,
        company_size=args.company_size,
        current_systems=list(args.current_systems),
        target_goal=args.target_goal,
        constraints=list(args.constraints),
        enable_shadow_retrieval=args.shadow,
        llm_mode=args.llm_mode,
    )
    service = SolutionInsightService.from_defaults(
        enable_shadow_retrieval=args.shadow,
        llm_mode=args.llm_mode,
    )
    response = service.generate_insight(request)
    print(json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
