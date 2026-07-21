from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import Field

from schemas.common_models import StrictBaseModel


class CompensationStatus(str, Enum):
    not_required = "not_required"
    planned = "planned"
    executed = "executed"
    failed = "failed"
    manual_required = "manual_required"


class CompensationPlan(StrictBaseModel):
    compensation_id: str = Field(default_factory=lambda: f"compensation-{uuid.uuid4().hex}")
    run_id: str
    tool_name: str
    original_action: str
    compensation_action: str
    reason: str
    status: CompensationStatus = CompensationStatus.planned
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    executed_at: datetime | None = None
    notes: list[str] = Field(default_factory=list)
