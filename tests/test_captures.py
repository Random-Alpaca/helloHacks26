import pytest

from hub import captures


def test_capture_dispatch_uses_existing_canvas_model_mapper():
    courses, items = captures.parse({
        "source": "canvas",
        "courses": [{"id": 7, "course_code": "CPSC 121", "name": "Models"}],
        "planner": [{"course_id": 7, "plannable_type": "quiz",
                     "plannable_date": "2026-09-30T06:59:00Z",
                     "plannable": {"title": "Quiz 2"},
                     "html_url": "https://canvas.ubc.ca/courses/7/quizzes/3"}],
        "undated": [],
    })
    assert [c.code for c in courses] == ["CPSC 121"]
    assert [(i.source, i.kind, i.course) for i in items] == [
        ("canvas", "quiz", "CPSC 121")
    ]


def test_normalize_returns_json_safe_identity_deduped_shared_rows():
    planner = {"course_id": 7, "plannable_type": "quiz",
               "plannable_date": "2026-09-30T06:59:00Z",
               "plannable": {"title": "Quiz 2"},
               "html_url": "https://canvas.ubc.ca/courses/7/quizzes/3"}
    result = captures.normalize({
        "source": "canvas", "courses": [{"id": 7, "course_code": "CPSC 121", "name": "Models"}],
        "planner": [planner, planner], "undated": []})
    assert result["stored"] is False
    assert len(result["items"]) == 1
    assert result["items"][0]["due"] == "2026-09-30T06:59:00+00:00"
    assert result["courses"][0]["code"] == "CPSC 121"


@pytest.mark.parametrize("capture", [None, [], {"source": "../db"},
                                            {"source": "missing_provider"}, {"source": "site"}])
def test_capture_dispatch_rejects_unverified_sources(capture):
    with pytest.raises(ValueError):
        captures.parse(capture)
