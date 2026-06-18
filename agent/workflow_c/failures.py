from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from agent.workflow_c.state import NodeValidationIssue, WorkflowNodeName


SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]+", re.IGNORECASE)


def redact_secrets(value: str) -> str:
    return SECRET_PATTERN.sub("[REDACTED]", value)


class MissingNodeDependencyError(Exception):
    def __init__(self, node_name: WorkflowNodeName, missing_fields: list[str]) -> None:
        self.node_name = node_name
        self.missing_fields = tuple(missing_fields)
        super().__init__(
            f"Node {node_name.value} is missing required state fields: {', '.join(missing_fields)}."
        )


class NodeContractViolationError(Exception):
    def __init__(
        self,
        *,
        message: str,
        unauthorized_fields: set[str] | None = None,
        missing_fields: set[str] | None = None,
    ) -> None:
        self.unauthorized_fields = frozenset(unauthorized_fields or set())
        self.missing_fields = frozenset(missing_fields or set())
        super().__init__(redact_secrets(message))


class NodeJSONParseError(Exception):
    def __init__(
        self,
        *,
        message: str,
        content_length: int,
        position: int | None = None,
    ) -> None:
        self.content_length = content_length
        self.position = position
        safe_message = redact_secrets(message)
        super().__init__(
            f"{safe_message} Content length={content_length}; position={position}."
        )


def validation_issues_from_error(error: ValidationError) -> list[NodeValidationIssue]:
    issues: list[NodeValidationIssue] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ())) or "<root>"
        raw_input = item.get("input")
        input_summary = None
        if raw_input is not None:
            input_summary = _safe_summary(raw_input)
        issues.append(
            NodeValidationIssue(
                location=location,
                error_type=str(item.get("type", "validation_error")),
                message=redact_secrets(str(item.get("msg", "Validation error."))),
                input_summary=input_summary,
            )
        )
    return issues


def _safe_summary(value: Any) -> str:
    summary = redact_secrets(repr(value))
    if len(summary) > 500:
        summary = f"{summary[:497]}..."
    return summary
