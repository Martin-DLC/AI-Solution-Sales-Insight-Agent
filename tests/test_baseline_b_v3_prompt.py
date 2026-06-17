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
SYSTEM_V2_SHA256 = "b04dd599ffccc3150a8449282eaf0ea5f5f4aef0cab5713dbdec6abec5a72b69"
USER_V2_SHA256 = "ca24b2e7b13c3ffdcb1b93d3d49edcb9c1937e03515717d8ba224a04f4885045"


def dev_01_case():
    return load_runtime_cases("data/evaluation/development_cases.jsonl")[0]


def sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def v3_combined_template() -> str:
    system_template, user_template = load_baseline_b_templates("baseline_b_v3")
    return system_template + user_template


def test_baseline_b_v3_templates_load() -> None:
    system_template, user_template = load_baseline_b_templates("baseline_b_v3")

    assert system_template
    assert user_template


def test_baseline_b_v1_and_v2_files_are_not_modified() -> None:
    assert sha256_file("evaluation/baselines/prompts/baseline_b_system_v1.txt") == SYSTEM_V1_SHA256
    assert sha256_file("evaluation/baselines/prompts/baseline_b_user_v1.txt") == USER_V1_SHA256
    assert sha256_file("evaluation/baselines/prompts/baseline_b_system_v2.txt") == SYSTEM_V2_SHA256
    assert sha256_file("evaluation/baselines/prompts/baseline_b_user_v2.txt") == USER_V2_SHA256


def test_v3_lists_all_information_gap_recommended_owner_values() -> None:
    combined = v3_combined_template()

    for value in ('"sales"', '"presales"', '"customer"', '"it"', '"security"', '"management"', '"unknown"'):
        assert value in combined
    assert "InformationGap.recommended_owner唯一允许" in combined


def test_v3_forbids_joint_for_information_gap_owner() -> None:
    combined = v3_combined_template()

    assert "禁止在InformationGap.recommended_owner中使用" in combined
    assert '"joint"' in combined


def test_v3_allows_joint_for_next_best_action_owner() -> None:
    combined = v3_combined_template()

    assert "NextBestAction.owner允许" in combined
    assert '"joint"' in combined


def test_v3_states_owner_fields_must_not_be_mixed() -> None:
    combined = v3_combined_template()

    assert "合法枚举不同，不得混用" in combined


def test_v3_states_risk_impact_minimum_length() -> None:
    combined = v3_combined_template()

    assert "risks_and_objections[*].impact至少10个字符" in combined


def test_v3_states_next_best_action_expected_output_minimum_length() -> None:
    combined = v3_combined_template()

    assert "expected_output至少8个字符" in combined


def test_v3_states_next_best_action_other_text_minimum_lengths() -> None:
    combined = v3_combined_template()

    assert "objective至少8个字符" in combined
    assert "success_criteria至少8个字符" in combined
    assert "reasoning_summary至少8个字符" in combined


def test_v3_keeps_v2_claim_type_rules() -> None:
    combined = v3_combined_template()

    assert 'explicit_needs[*].claim_type必须始终为"fact"' in combined
    assert 'underlying_pains[*].claim_type只能是"inference"或"assumption"' in combined


def test_v3_keeps_v2_deal_score_fixed_weight_rules() -> None:
    combined = v3_combined_template()
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
        assert f"{dimension}: max_score必须为{max_score}" in combined


def test_v3_does_not_contain_hard_failure_traps() -> None:
    assert "hard_failure_traps" not in v3_combined_template()


def test_v3_does_not_contain_solution_blacklist() -> None:
    assert "solution_blacklist" not in v3_combined_template()


def test_v3_does_not_contain_scoring_notes() -> None:
    assert "scoring_notes" not in v3_combined_template()


def test_v3_does_not_contain_reference_pack() -> None:
    assert "Reference Pack" not in v3_combined_template()


def test_v1_v2_and_v3_prompt_sha256_are_all_different() -> None:
    case = dev_01_case()
    hashes = {
        calculate_messages_sha256(list(render_baseline_b_messages(case, version=version)))
        for version in ("baseline_b_v1", "baseline_b_v2", "baseline_b_v3")
    }

    assert len(hashes) == 3


def test_v3_sha256_is_stable() -> None:
    case = dev_01_case()

    first = calculate_messages_sha256(list(render_baseline_b_messages(case, version="baseline_b_v3")))
    second = calculate_messages_sha256(list(render_baseline_b_messages(case, version="baseline_b_v3")))

    assert first == second


def test_v3_rendered_prompt_contains_full_dev_01_transcript() -> None:
    case = dev_01_case()
    _, user_message = render_baseline_b_messages(case, version="baseline_b_v3")

    assert case.meeting.transcript in user_message.content


def test_v3_rendering_returns_system_and_user_messages_only() -> None:
    messages = render_baseline_b_messages(dev_01_case(), version="baseline_b_v3")

    assert len(messages) == 2
    assert messages[0].role.value == "system"
    assert messages[1].role.value == "user"
