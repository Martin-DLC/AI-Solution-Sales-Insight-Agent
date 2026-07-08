from __future__ import annotations

from agent.skills import BaseSkill, SkillInput, SkillRegistry


class EchoSkill(BaseSkill):
    name = "echo"

    def run(self, skill_input: SkillInput):
        return "success", {"seen_query": skill_input.user_query}, []


class AppendSkill(BaseSkill):
    name = "append"

    def run(self, skill_input: SkillInput):
        previous = skill_input.previous_outputs.get("echo", {})
        return "success", {"message": f"{previous.get('seen_query', '')}-done"}, []


class FailingSkill(BaseSkill):
    name = "failing"

    def run(self, skill_input: SkillInput):
        raise RuntimeError("boom")


def test_registry_registers_and_lists_skills() -> None:
    registry = SkillRegistry()
    registry.register(EchoSkill())
    registry.register(AppendSkill())

    assert registry.list_skills() == ["echo", "append"]


def test_duplicate_skill_name_raises() -> None:
    registry = SkillRegistry()
    registry.register(EchoSkill())

    try:
        registry.register(EchoSkill())
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected duplicate registration to fail.")


def test_execute_sequence_is_stable_and_accumulates_previous_outputs() -> None:
    registry = SkillRegistry()
    registry.register(EchoSkill())
    registry.register(AppendSkill())

    previous_outputs, outputs, trace = registry.execute_sequence(
        ["echo", "append"],
        SkillInput(request_id="req-1", user_query="hello"),
    )

    assert [item.skill_name for item in outputs] == ["echo", "append"]
    assert previous_outputs["append"]["message"] == "hello-done"
    assert trace.executed_skills == ["echo", "append"]
    assert trace.failed_skill_count == 0


def test_skill_exception_becomes_failed_output() -> None:
    registry = SkillRegistry()
    registry.register(FailingSkill())

    previous_outputs, outputs, trace = registry.execute_sequence(
        ["failing"],
        SkillInput(request_id="req-2", user_query="hello"),
    )

    assert outputs[0].status == "failed"
    assert outputs[0].error_summary == "RuntimeError: boom"
    assert previous_outputs["failing"] == {}
    assert trace.failed_skill_count == 1
