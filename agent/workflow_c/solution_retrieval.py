from __future__ import annotations

import re
import unicodedata

from agent.workflow_c.retrieval_models import (
    RetrievedSolutionCandidate,
    SolutionRetrievalMethod,
    SolutionRetrievalResult,
)
from agent.workflow_c.solution_validation import build_solution_catalog
from agent.workflow_c.state import SourceIndexResult
from schemas.common_models import EvidenceSourceType, OpportunitySuitability
from schemas.input_models import EvaluationCaseInput
from schemas.insight_models import BusinessImpact, UnderlyingPain
from schemas.solution_models import AIOpportunity


NO_ELIGIBLE_AI_OPPORTUNITY_QUERY = "NO_ELIGIBLE_AI_OPPORTUNITY"

_ELIGIBLE_SUITABILITY = {
    OpportunitySuitability.suitable_now,
    OpportunitySuitability.suitable_for_poc,
    OpportunitySuitability.suitable_after_prerequisites,
}

_STOPWORDS = {
    "客户",
    "方案",
    "系统",
    "能力",
    "需要",
    "进行",
    "the",
    "and",
    "for",
}

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+")


def normalize_retrieval_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def tokenize_retrieval_text(value: str) -> list[str]:
    normalized = normalize_retrieval_text(value)
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(normalized):
        part = match.group(0)
        if _is_cjk(part):
            if 2 <= len(part) <= 6:
                tokens.append(part)
            if len(part) >= 2:
                tokens.extend(part[index : index + 2] for index in range(len(part) - 1))
        elif len(part) >= 2:
            tokens.append(part)
    return _deduplicate([token for token in tokens if token not in _STOPWORDS])


def build_solution_retrieval_query(
    ai_opportunities: list[AIOpportunity],
    underlying_pains: list[UnderlyingPain],
    business_impacts: list[BusinessImpact],
) -> tuple[str, list[str]]:
    pains_by_id = {pain.pain_id: pain for pain in underlying_pains}
    eligible = [
        opportunity
        for opportunity in ai_opportunities
        if opportunity.suitability in _ELIGIBLE_SUITABILITY
    ]
    if not eligible:
        return NO_ELIGIBLE_AI_OPPORTUNITY_QUERY, []

    parts: list[str] = []
    for opportunity in eligible:
        parts.extend(
            [
                opportunity.name,
                opportunity.reasoning_summary,
                " ".join(opportunity.required_data),
                " ".join(opportunity.required_integrations),
                " ".join(value.value for value in opportunity.business_value),
            ]
        )
        for pain_id in opportunity.related_pain_ids:
            pain = pains_by_id.get(pain_id)
            if pain is not None:
                parts.append(pain.description)
    parts.extend(impact.description for impact in business_impacts)
    query_text = " ".join(part for part in parts if part)
    return query_text, [opportunity.opportunity_id for opportunity in eligible]


def score_solution_candidate(query_text: str, solution_text: str) -> tuple[float, list[str]]:
    query_tokens = tokenize_retrieval_text(query_text)
    solution_tokens = tokenize_retrieval_text(solution_text)
    query_set = set(query_tokens)
    solution_set = set(solution_tokens)
    intersection = query_set & solution_set
    if not intersection:
        return 0.0, []

    overlap = len(intersection) / min(len(query_set), len(solution_set))
    jaccard = len(intersection) / len(query_set | solution_set)
    exact_bonus = 1.0 if normalize_retrieval_text(solution_text) in normalize_retrieval_text(query_text) else 0.0
    score = min(1.0, max(0.0, (0.50 * overlap) + (0.30 * jaccard) + (0.20 * exact_bonus)))
    matched_terms = [token for token in query_tokens if token in intersection]
    return score, _deduplicate(matched_terms)


def retrieve_solution_candidates(
    *,
    case: EvaluationCaseInput,
    source_index: SourceIndexResult,
    ai_opportunities: list[AIOpportunity],
    underlying_pains: list[UnderlyingPain],
    business_impacts: list[BusinessImpact],
    top_k: int = 5,
    min_score: float = 0.05,
) -> SolutionRetrievalResult:
    query_text, eligible_opportunity_ids = build_solution_retrieval_query(
        ai_opportunities,
        underlying_pains,
        business_impacts,
    )
    if not eligible_opportunity_ids:
        return SolutionRetrievalResult(
            retrieval_method=SolutionRetrievalMethod.lexical_v1,
            query_text=query_text,
            eligible_opportunity_ids=[],
            top_k=top_k,
            candidate_count=0,
            candidates=[],
        )

    catalog = build_solution_catalog(case, source_index)
    scored: list[tuple[int, float, list[str], str, object]] = []
    for index, (solution_id, item) in enumerate(catalog.items()):
        if item.source_type is not EvidenceSourceType.solution_library:
            continue
        score, matched_terms = score_solution_candidate(query_text, item.content)
        if score >= min_score:
            scored.append((index, score, matched_terms, solution_id, item))

    scored.sort(key=lambda entry: (-entry[1], entry[0]))
    candidates = [
        RetrievedSolutionCandidate(
            solution_id=solution_id,
            source_id=item.source_id,
            source_type=item.source_type,
            content=item.content,
            score=score,
            rank=rank,
            matched_terms=matched_terms,
        )
        for rank, (_index, score, matched_terms, solution_id, item) in enumerate(
            scored[:top_k],
            start=1,
        )
    ]
    return SolutionRetrievalResult(
        retrieval_method=SolutionRetrievalMethod.lexical_v1,
        query_text=query_text,
        eligible_opportunity_ids=eligible_opportunity_ids,
        top_k=top_k,
        candidate_count=len(candidates),
        candidates=candidates,
    )


def _is_cjk(value: str) -> bool:
    return all("\u4e00" <= char <= "\u9fff" for char in value)


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
