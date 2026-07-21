from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import Field

from schemas.common_models import StrictBaseModel


class ReviewStatus(str, Enum):
    not_required = "not_required"
    pending = "pending"
    in_review = "in_review"
    approved = "approved"
    approved_with_changes = "approved_with_changes"
    rejected = "rejected"
    expired = "expired"


_TERMINAL = {
    ReviewStatus.approved,
    ReviewStatus.approved_with_changes,
    ReviewStatus.rejected,
    ReviewStatus.expired,
    ReviewStatus.not_required,
}


class ReviewQueueItem(StrictBaseModel):
    review_item_id: str = Field(default_factory=lambda: f"review-{uuid.uuid4().hex}")
    run_id: str
    trace_id: str
    evaluation_id: str
    trigger_reason: str
    priority: str = "medium"
    status: ReviewStatus = ReviewStatus.pending
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    assigned_to: str | None = None
    reviewed_at: datetime | None = None
    decision: str | None = None
    reviewer_notes: str | None = None


class ReviewQueueManager:
    def __init__(self) -> None:
        self._items: dict[str, ReviewQueueItem] = {}

    def create_item(
        self,
        *,
        run_id: str,
        trace_id: str,
        evaluation_id: str,
        trigger_reason: str,
        priority: str = "medium",
        assigned_to: str | None = None,
    ) -> ReviewQueueItem:
        item = ReviewQueueItem(
            run_id=run_id,
            trace_id=trace_id,
            evaluation_id=evaluation_id,
            trigger_reason=trigger_reason,
            priority=priority,
            assigned_to=assigned_to,
            status=ReviewStatus.pending,
        )
        self._items[item.review_item_id] = item
        return item

    def list_items(self, *, status: ReviewStatus | str | None = None) -> list[ReviewQueueItem]:
        items = list(self._items.values())
        if status is None:
            return items
        resolved = ReviewStatus(status)
        return [item for item in items if item.status is resolved]

    def get_item(self, review_item_id: str) -> ReviewQueueItem:
        try:
            return self._items[review_item_id]
        except KeyError as exc:
            raise KeyError(f"Unknown review_item_id: {review_item_id}") from exc

    def mark_in_review(self, review_item_id: str, *, assigned_to: str | None = None) -> ReviewQueueItem:
        item = self.get_item(review_item_id)
        self._ensure_not_terminal(item)
        return self._update(item, status=ReviewStatus.in_review, assigned_to=assigned_to or item.assigned_to)

    def approve(self, review_item_id: str, *, reviewer_notes: str | None = None) -> ReviewQueueItem:
        return self._terminal(review_item_id, status=ReviewStatus.approved, decision="approved", reviewer_notes=reviewer_notes)

    def approve_with_changes(self, review_item_id: str, *, reviewer_notes: str) -> ReviewQueueItem:
        return self._terminal(
            review_item_id,
            status=ReviewStatus.approved_with_changes,
            decision="approved_with_changes",
            reviewer_notes=reviewer_notes,
        )

    def reject(self, review_item_id: str, *, reviewer_notes: str) -> ReviewQueueItem:
        return self._terminal(review_item_id, status=ReviewStatus.rejected, decision="rejected", reviewer_notes=reviewer_notes)

    def expire(self, review_item_id: str, *, reviewer_notes: str | None = None) -> ReviewQueueItem:
        return self._terminal(review_item_id, status=ReviewStatus.expired, decision="expired", reviewer_notes=reviewer_notes)

    def _terminal(
        self,
        review_item_id: str,
        *,
        status: ReviewStatus,
        decision: str,
        reviewer_notes: str | None,
    ) -> ReviewQueueItem:
        item = self.get_item(review_item_id)
        self._ensure_not_terminal(item)
        return self._update(
            item,
            status=status,
            reviewed_at=datetime.now(UTC),
            decision=decision,
            reviewer_notes=reviewer_notes,
        )

    def _update(self, item: ReviewQueueItem, **updates: object) -> ReviewQueueItem:
        updated = item.model_copy(update=updates)
        self._items[item.review_item_id] = updated
        return updated

    def _ensure_not_terminal(self, item: ReviewQueueItem) -> None:
        if item.status in _TERMINAL:
            raise ValueError(f"Review item is already terminal: {item.status.value}")
