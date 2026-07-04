from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status

from agent import SolutionInsightRequest, SolutionInsightResponse, SolutionInsightService


APP_NAME = "solution-insight-agent"

app = FastAPI(title="AI Solution Sales Insight Agent", version="1.0.0")


@lru_cache(maxsize=1)
def get_solution_insight_service() -> SolutionInsightService:
    return SolutionInsightService.from_defaults()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": APP_NAME}


@app.post("/solution-insight", response_model=SolutionInsightResponse)
def solution_insight(
    request: SolutionInsightRequest,
    service: Annotated[SolutionInsightService, Depends(get_solution_insight_service)],
) -> SolutionInsightResponse:
    try:
        return service.generate_insight(request)
    except Exception as exc:  # pragma: no cover - defensive safety net
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="solution insight generation failed",
        ) from exc
