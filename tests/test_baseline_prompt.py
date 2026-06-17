from __future__ import annotations

from dataio.runtime_cases import load_runtime_cases
from evaluation.baselines import (
    calculate_prompt_sha256,
    load_prompt_template,
    render_baseline_a_prompt,
)


def dev_01_case():
    cases = load_runtime_cases("data/evaluation/development_cases.jsonl")
    return next(case for case in cases if case.case_id == "DEV-01")


def test_baseline_a_v1_template_loads() -> None:
    assert load_prompt_template("baseline_a_v1")


def test_template_has_exactly_one_placeholder() -> None:
    assert load_prompt_template("baseline_a_v1").count("{{CASE_JSON}}") == 1


def test_rendered_prompt_contains_dev_01() -> None:
    assert "DEV-01" in render_baseline_a_prompt(dev_01_case())


def test_rendered_prompt_contains_full_transcript() -> None:
    case = dev_01_case()

    assert case.meeting.transcript in render_baseline_a_prompt(case)


def test_rendered_prompt_contains_salesperson_notes() -> None:
    prompt = render_baseline_a_prompt(dev_01_case())

    assert "承诺替代30%以上的客服人员" in prompt


def test_rendered_prompt_contains_available_solution_library() -> None:
    prompt = render_baseline_a_prompt(dev_01_case())

    assert "AI客服知识问答方案" in prompt


def test_rendered_prompt_does_not_contain_hard_failure_traps() -> None:
    assert "hard_failure_traps" not in render_baseline_a_prompt(dev_01_case())


def test_rendered_prompt_does_not_contain_solution_blacklist() -> None:
    assert "solution_blacklist" not in render_baseline_a_prompt(dev_01_case())


def test_rendered_prompt_does_not_contain_scoring_notes() -> None:
    assert "scoring_notes" not in render_baseline_a_prompt(dev_01_case())


def test_prompt_does_not_contain_top_sales() -> None:
    assert "Top Sales" not in load_prompt_template("baseline_a_v1")


def test_prompt_does_not_contain_sales_insight_report() -> None:
    assert "SalesInsightReport" not in load_prompt_template("baseline_a_v1")


def test_sha256_is_stable_and_64_chars() -> None:
    prompt = render_baseline_a_prompt(dev_01_case())

    first = calculate_prompt_sha256(prompt)
    second = calculate_prompt_sha256(prompt)

    assert first == second
    assert len(first) == 64
