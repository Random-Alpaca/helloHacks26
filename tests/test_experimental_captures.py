"""Synthetic JSON shapes only: no live account or endpoint is implied."""
import pytest

from hub import captures


def test_moodle_capture_reuses_existing_mapping_and_rejects_foreign_url():
    capture = {
        "source": "moodle", "origin": "https://moodle.example.edu",
        "courses": [{"shortname": "CPSC101", "fullname": "Intro"}],
        "events": [{"id": 9, "name": "Quiz", "modulename": "quiz",
                    "timesort": 1798000000, "url": "", "course": {"shortname": "CPSC101"}}],
    }
    model = captures.normalize(capture)
    assert model["courses"][0]["code"] == "CPSC101"
    assert model["items"][0]["kind"] == "quiz"
    assert model["items"][0]["url"] == "https://moodle.example.edu/calendar/event.php?id=9"
    capture["events"][0]["url"] = "https://other.example/steal"
    with pytest.raises(ValueError, match="unsafe"):
        captures.normalize(capture)


def test_blackboard_capture_reuses_course_mapper_without_inventing_tasks():
    model = captures.normalize({"source": "blackboard", "courses": [
        {"id": "_1_1", "courseId": "BIOL101", "name": "Biology",
         "term": {"name": "Fall 2026"}}]})
    assert model["courses"][0]["code"] == "BIOL101"
    assert model["items"] == []


def test_piazza_capture_reuses_pinned_post_mapper():
    model = captures.normalize({"source": "piazza", "networks": [{
        "id": "abc123", "course_number": "CPSC 121", "name": "Models", "term": "Fall 2026",
        "posts": [{"id": "post123", "tags": ["pin"], "bucket_name": "Pinned",
                   "history": [{"subject": "Quiz room"}]}]
    }]})
    assert model["courses"][0]["code"] == "CPSC 121"
    assert model["items"][0]["title"] == "Quiz room"
    assert model["items"][0]["source"] == "piazza"
