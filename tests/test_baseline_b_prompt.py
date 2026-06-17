from __future__ import annotations

from dataio.runtime_cases import load_runtime_cases
from evaluation.baselines import (
    calculate_messages_sha256,
    load_baseline_b_templates,
    render_baseline_b_messages,
)


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def test_baseline_b_templates_load() -> None:
    system_template, user_template = load_baseline_b_templates()

    assert system_template
    assert user_template


def test_system_template_has_one_schema_placeholder() -> None:
    system_template, _ = load_baseline_b_templates()

    assert system_template.count("{{OUTPUT_SCHEMA_JSON}}") == 1


def test_user_template_has_one_case_placeholder() -> None:
    _, user_template = load_baseline_b_templates()

    assert user_template.count("{{CASE_JSON}}") == 1


def test_rendered_user_prompt_contains_full_transcript() -> None:
    case = dev_01_case()
    _, user_message = render_baseline_b_messages(case)

    assert case.meeting.transcript in user_message.content


def test_rendered_system_prompt_contains_sales_insight_report_schema() -> None:
    system_message, _ = render_baseline_b_messages(dev_01_case())

    assert "SalesInsightReport JSON Schema" in system_message.content
    assert "schema_version" in system_message.content


def test_rendered_system_prompt_contains_claim_type_terms() -> None:
    system_message, _ = render_baseline_b_messages(dev_01_case())

    for term in ("fact", "inference", "assumption", "unknown"):
        assert term in system_message.content


def test_rendered_prompt_says_salesperson_notes_are_unverified() -> None:
    system_message, user_message = render_baseline_b_messages(dev_01_case())

    combined = system_message.content + user_message.content
    assert "未经客户确认" in combined


def test_rendered_prompt_requires_human_review_true() -> None:
    system_message, _ = render_baseline_b_messages(dev_01_case())

    assert "human_review_required=true" in system_message.content


def test_rendered_prompt_limits_solutions_to_available_library() -> None:
    system_message, user_message = render_baseline_b_messages(dev_01_case())

    assert "available_solution_library" in system_message.content
    assert "available_solution_library" in user_message.content


def test_rendered_prompt_does_not_contain_hard_failure_traps() -> None:
    system_message, user_message = render_baseline_b_messages(dev_01_case())

    assert "hard_failure_traps" not in system_message.content + user_message.content


def test_rendered_prompt_does_not_contain_solution_blacklist() -> None:
    system_message, user_message = render_baseline_b_messages(dev_01_case())

    assert "solution_blacklist" not in system_message.content + user_message.content


def test_rendered_prompt_does_not_contain_scoring_notes() -> None:
    system_message, user_message = render_baseline_b_messages(dev_01_case())

    assert "scoring_notes" not in system_message.content + user_message.content


def test_message_roles_are_system_and_user() -> None:
    system_message, user_message = render_baseline_b_messages(dev_01_case())

    assert system_message.role.value == "system"
    assert user_message.role.value == "user"


def test_messages_sha256_is_stable_and_64_chars() -> None:
    messages = list(render_baseline_b_messages(dev_01_case()))

    first = calculate_messages_sha256(messages)
    second = calculate_messages_sha256(messages)

    assert first == second
    assert len(first) == 64


def test_message_content_change_changes_sha256() -> None:
    messages = list(render_baseline_b_messages(dev_01_case()))
    changed_messages = list(render_baseline_b_messages(dev_01_case()))
    changed_messages[1].content += "\nextra"

    assert calculate_messages_sha256(messages) != calculate_messages_sha256(changed_messages)
