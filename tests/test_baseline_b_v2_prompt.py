from __future__ import annotations

import hashlib
from pathlib import Path

from dataio.runtime_cases import load_runtime_cases
from evaluation.baselines import (
    calculate_messages_sha256,
    load_baseline_b_templates,
    render_baseline_b_messages,
)


SYSTEM_V1_SHA256 = "4d81944aa0715b52898c2810fe5770e67d1990b8e05294a46ef62a477e581ed8"
USER_V1_SHA256 = "45eaa4c2419c6183b2efddd84685047dc800ca40287b68f221ebd9b63986e295"


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_baseline_b_v2_templates_load() -> None:
    system_template, user_template = load_baseline_b_templates("baseline_b_v2")

    assert system_template
    assert user_template


def test_baseline_b_v1_files_are_not_modified() -> None:
    assert sha256_file("evaluation/baselines/prompts/baseline_b_system_v1.txt") == SYSTEM_V1_SHA256
    assert sha256_file("evaluation/baselines/prompts/baseline_b_user_v1.txt") == USER_V1_SHA256


def test_v2_states_explicit_needs_must_be_fact() -> None:
    system_template, _ = load_baseline_b_templates("baseline_b_v2")

    assert 'explicit_needs[*].claim_type必须始终为"fact"' in system_template


def test_v2_states_underlying_pains_claim_types() -> None:
    system_template, _ = load_baseline_b_templates("baseline_b_v2")

    assert 'underlying_pains[*].claim_type只能是"inference"或"assumption"' in system_template


def test_v2_contains_all_deal_score_fixed_max_scores() -> None:
    system_template, _ = load_baseline_b_templates("baseline_b_v2")
    expected = {
        "business_need": 20,
        "business_value": 15,
        "budget": 15,
        "authority": 15,
        "timeline": 10,
        "solution_fit": 15,
        "delivery_readiness": 10,
    }

    for dimension, max_score in expected.items():
        assert f"{dimension}: max_score必须为{max_score}" in system_template


def test_each_fixed_dimension_weight_line_appears_once() -> None:
    system_template, _ = load_baseline_b_templates("baseline_b_v2")

    for dimension in (
        "business_need",
        "business_value",
        "budget",
        "authority",
        "timeline",
        "solution_fit",
        "delivery_readiness",
    ):
        assert system_template.count(f"{dimension}: max_score") == 1


def test_v2_states_dimensions_must_be_exactly_seven() -> None:
    system_template, _ = load_baseline_b_templates("baseline_b_v2")

    assert "dimensions必须正好7条" in system_template


def test_v2_states_total_score_equals_sum() -> None:
    system_template, _ = load_baseline_b_templates("baseline_b_v2")

    assert "total_score必须等于7个score之和" in system_template


def test_v2_states_objective_minimum_length() -> None:
    system_template, _ = load_baseline_b_templates("baseline_b_v2")

    assert "objective至少8个字符" in system_template


def test_v2_states_p0_requires_related_gap_id() -> None:
    system_template, _ = load_baseline_b_templates("baseline_b_v2")

    assert "P0行动必须关联至少一个related_gap_id" in system_template


def test_v2_does_not_contain_hard_failure_traps() -> None:
    system_template, user_template = load_baseline_b_templates("baseline_b_v2")

    assert "hard_failure_traps" not in system_template + user_template


def test_v2_does_not_contain_solution_blacklist() -> None:
    system_template, user_template = load_baseline_b_templates("baseline_b_v2")

    assert "solution_blacklist" not in system_template + user_template


def test_v2_does_not_contain_scoring_notes() -> None:
    system_template, user_template = load_baseline_b_templates("baseline_b_v2")

    assert "scoring_notes" not in system_template + user_template


def test_v2_does_not_contain_reference_pack() -> None:
    system_template, user_template = load_baseline_b_templates("baseline_b_v2")

    assert "Reference Pack" not in system_template + user_template


def test_v1_and_v2_prompt_sha256_are_different() -> None:
    case = dev_01_case()
    v1_messages = list(render_baseline_b_messages(case, version="baseline_b_v1"))
    v2_messages = list(render_baseline_b_messages(case, version="baseline_b_v2"))

    assert calculate_messages_sha256(v1_messages) != calculate_messages_sha256(v2_messages)


def test_v2_sha256_is_stable() -> None:
    case = dev_01_case()

    first = calculate_messages_sha256(list(render_baseline_b_messages(case, version="baseline_b_v2")))
    second = calculate_messages_sha256(list(render_baseline_b_messages(case, version="baseline_b_v2")))

    assert first == second


def test_v2_rendered_prompt_contains_full_dev_01_transcript() -> None:
    case = dev_01_case()
    _, user_message = render_baseline_b_messages(case, version="baseline_b_v2")

    assert case.meeting.transcript in user_message.content


def test_v2_rendering_returns_system_and_user_messages_only() -> None:
    messages = render_baseline_b_messages(dev_01_case(), version="baseline_b_v2")

    assert len(messages) == 2
    assert messages[0].role.value == "system"
    assert messages[1].role.value == "user"
