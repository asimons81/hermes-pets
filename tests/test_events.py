import pytest

from hermes_pet.events import PetEventError, build_event, normalize_event


def test_build_event_normalizes_type_and_defaults() -> None:
    event = build_event("job-finished", "  Tests passed  ")

    assert event["schema"] == "hermes.pet.event.v1"
    assert event["type"] == "job_finished"
    assert event["text"] == "Tests passed"
    assert event["severity"] == "success"
    assert event["id"]
    assert event["created_at"].endswith("Z")


def test_build_event_rejects_unknown_type() -> None:
    with pytest.raises(PetEventError):
        build_event("surprise", "hello")


def test_normalize_message_event_builds_fallback_text() -> None:
    event = normalize_event({"type": "message_received", "source": "telegram", "sender": "Ada"})

    assert event["type"] == "message_received"
    assert event["text"] == "telegram from Ada"
    assert event["source"] == "telegram"
    assert event["sender"] == "Ada"
