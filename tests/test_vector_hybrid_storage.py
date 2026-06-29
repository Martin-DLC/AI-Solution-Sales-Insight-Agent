from __future__ import annotations

from evaluation.retrieval.storage import diff_json_objects_ignoring_paths, write_many_atomic


def test_write_many_atomic_writes_all_files(tmp_path) -> None:
    first = tmp_path / "a.json"
    second = tmp_path / "b.jsonl"

    write_many_atomic([(first, '{"ok":1}\n'), (second, '{"ok":2}\n')])

    assert first.read_text(encoding="utf-8") == '{"ok":1}\n'
    assert second.read_text(encoding="utf-8") == '{"ok":2}\n'


def test_diff_json_objects_ignoring_paths_ignores_allowed_fields() -> None:
    expected = {"latency_ms": 1, "score": 0.5}
    actual = {"latency_ms": 9, "score": 0.5}

    assert diff_json_objects_ignoring_paths(expected, actual, ignored_suffixes={"latency_ms"}) == []


def test_diff_json_objects_ignoring_paths_keeps_score_difference() -> None:
    expected = {"latency_ms": 1, "score": 0.5}
    actual = {"latency_ms": 9, "score": 0.8}

    assert diff_json_objects_ignoring_paths(expected, actual, ignored_suffixes={"latency_ms"}) == ["score"]


def test_diff_json_objects_ignoring_paths_ignores_cache_hit_and_miss_counts() -> None:
    expected = {"cache_hit_count": 0, "cache_miss_count": 40, "score": 0.5}
    actual = {"cache_hit_count": 40, "cache_miss_count": 0, "score": 0.5}

    assert (
        diff_json_objects_ignoring_paths(
            expected,
            actual,
            ignored_suffixes={"cache_hit_count", "cache_miss_count"},
        )
        == []
    )
