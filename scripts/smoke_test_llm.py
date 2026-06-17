from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llm import LLMMessage, LLMRequestError, LLMResponseError, LLMRole, create_llm_client  # noqa: E402
from llm.config import LLMConfig  # noqa: E402
from llm.errors import LLMConfigurationError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a safe LLM connectivity smoke test.")
    parser.add_argument("--live", action="store_true", help="Allow a real API call.")
    args = parser.parse_args(argv)

    if not args.live:
        print("Live API call is disabled. Re-run with --live to continue.")
        return 0

    try:
        config = LLMConfig.from_env()
        print("LLM config:")
        print(json.dumps(config.redacted_summary(), ensure_ascii=False, indent=2))

        client = create_llm_client(config)
        model_ids = client.list_model_ids()
        print("Available model IDs:")
        for model_id in model_ids:
            print(f"- {model_id}")

        if config.model not in model_ids:
            print(f"Configured model {config.model!r} is not available.", file=sys.stderr)
            return 1

        response = client.complete_json(
            [
                LLMMessage(
                    role=LLMRole.system,
                    content="You are an API connectivity test. Return only a valid JSON object.",
                ),
                LLMMessage(
                    role=LLMRole.user,
                    content='Return this JSON object exactly: {"status":"ok","message":"PONG"}',
                ),
            ],
            max_tokens=128,
        )

        print(f"configured model: {config.model}")
        print(f"response model: {response.model}")
        print(f"response id present: {response.response_id is not None}")
        print(f"finish reason: {response.finish_reason}")
        print(f"latency_ms: {response.latency_ms}")
        print(f"prompt tokens: {response.usage.prompt_tokens}")
        print(f"completion tokens: {response.usage.completion_tokens}")
        print(f"total tokens: {response.usage.total_tokens}")
        print("parsed JSON:")
        print(json.dumps(response.parsed_json, ensure_ascii=False, indent=2))

        if response.parsed_json != {"status": "ok", "message": "PONG"}:
            print("Smoke test response JSON did not match expected PONG payload.", file=sys.stderr)
            return 1

        print("LLM smoke test passed.")
        return 0
    except (LLMConfigurationError, LLMRequestError, LLMResponseError) as exc:
        print(f"LLM smoke test failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
