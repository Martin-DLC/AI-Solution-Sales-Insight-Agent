from __future__ import annotations

import json
from typing import Any

from agent.workflow_c.contracts import NodeContract, NodeFailurePolicy
from agent.workflow_c.failures import NodeBusinessRuleError, NodeJSONParseError
from agent.workflow_c.node_outputs import BuyingIntentNodeOutput
from agent.workflow_c.prompt_loader import render_buying_intent_messages
from agent.workflow_c.state import (
    ContextSufficiencyResult,
    FactExtractionResult,
    NodeValidationIssue,
    SourceIndexResult,
    WorkflowNodeName,
)
from schemas.common_models import ContextQuality, IntentLevel
from schemas.insight_models import BusinessImpact, BuyingIntent, ExplicitNeed, UnderlyingPain


class BuyingIntentNode:
    contract = NodeContract(
        name=WorkflowNodeName.buying_intent,
        required_state_fields=(
            "source_index",
            "context_sufficiency",
            "fact_extraction",
            "explicit_needs",
            "underlying_pains",
            "business_impacts",
        ),
        produced_state_fields=("buying_intent",),
        output_model=BuyingIntentNodeOutput,
        failure_policy=NodeFailurePolicy.require_human_review,
        prompt_version="buying_intent_v1",
    )

    def run(self, state: dict[str, Any], services: Any) -> dict[str, Any]:
        source_index: SourceIndexResult = state["source_index"]
        context_sufficiency: ContextSufficiencyResult = state["context_sufficiency"]
        fact_extraction: FactExtractionResult = state["fact_extraction"]
        explicit_needs: list[ExplicitNeed] = state["explicit_needs"]
        underlying_pains: list[UnderlyingPain] = state["underlying_pains"]
        business_impacts: list[BusinessImpact] = state["business_impacts"]
        messages = render_buying_intent_messages(
            source_index,
            context_sufficiency,
            fact_extraction,
            explicit_needs,
            underlying_pains,
            business_impacts,
        )
        result = services.llm.complete_json_for_node(WorkflowNodeName.buying_intent, messages)
        parsed = result.parsed_json
        if parsed is None:
            try:
                parsed = json.loads(result.content)
            except json.JSONDecodeError as exc:
                raise NodeJSONParseError(
                    message="Buying intent analysis returned invalid JSON.",
                    content_length=len(result.content),
                    position=exc.pos,
                ) from exc

        output = BuyingIntentNodeOutput.model_validate(parsed)
        _validate_buying_intent_rules(output.buying_intent, context_sufficiency)
        return {"buying_intent": output.buying_intent}


def _validate_buying_intent_rules(
    buying_intent: BuyingIntent,
    context_sufficiency: ContextSufficiencyResult,
) -> None:
    issues: list[NodeValidationIssue] = []
    if context_sufficiency.context_quality is ContextQuality.insufficient:
        issues.append(
            NodeValidationIssue(
                location="context_sufficiency.context_quality",
                error_type="business_rule",
                message="Buying intent must not run when context quality is insufficient.",
            )
        )
    if (
        context_sufficiency.context_quality is ContextQuality.partially_sufficient
        and buying_intent.intent_level is IntentLevel.high
    ):
        issues.append(
            NodeValidationIssue(
                location="buying_intent.intent_level",
                error_type="business_rule",
                message="Partially sufficient context cannot support high buying intent.",
            )
        )
    if (
        buying_intent.intent_level in {IntentLevel.high, IntentLevel.medium_high}
        and not buying_intent.positive_signals
    ):
        issues.append(
            NodeValidationIssue(
                location="buying_intent.positive_signals",
                error_type="business_rule",
                message="High or medium-high intent must include at least one positive signal.",
            )
        )
    signal_text = " ".join(
        buying_intent.positive_signals
        + buying_intent.negative_signals
        + buying_intent.unknown_factors
        + [buying_intent.reasoning_summary]
    )
    if "SOLUTION-" in signal_text:
        issues.append(
            NodeValidationIssue(
                location="buying_intent",
                error_type="business_rule",
                message="Buying intent must not use solution_library evidence.",
            )
        )
    if "REFERENCE" in signal_text.upper():
        issues.append(
            NodeValidationIssue(
                location="buying_intent",
                error_type="business_rule",
                message="Buying intent must not use reference_case evidence.",
            )
        )
    if (
        buying_intent.intent_level in {IntentLevel.high, IntentLevel.medium_high}
        and "NOTE-" in " ".join(buying_intent.positive_signals + [buying_intent.reasoning_summary])
        and "MTG-" not in signal_text
        and "PROFILE-" not in signal_text
    ):
        issues.append(
            NodeValidationIssue(
                location="buying_intent.positive_signals",
                error_type="business_rule",
                message="High or medium-high intent must not rely only on unverified salesperson notes.",
            )
        )
    if issues:
        raise NodeBusinessRuleError(
            node_name=WorkflowNodeName.buying_intent,
            message="Buying intent failed business validation.",
            issues=issues,
        )
