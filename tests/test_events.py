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


def test_build_event_accepts_phase4_context_fields() -> None:
    event = build_event(
        "approval-needed",
        "Review deploy plan",
        source="github",
        source_id="issue-16",
        urgency="important",
        project_id="hermes-pet",
        project_path="/home/tony/projects/hermes-pet",
        session_id="session-1",
        session_label="Phase 4",
        action_label="Open issue",
        action_command="gh issue view 16",
        action_url="https://github.com/asimons81/hermes-pets/issues/16",
        privacy_summary="No message body stored.",
        unexpected="do not persist",
    )

    assert event["schema"] == "hermes.pet.event.v1"
    assert event["urgency"] == "important"
    assert event["source"] == "github"
    assert event["source_id"] == "issue-16"
    assert event["project_id"] == "hermes-pet"
    assert event["project_path"] == "/home/tony/projects/hermes-pet"
    assert event["session_id"] == "session-1"
    assert event["session_label"] == "Phase 4"
    assert event["action_label"] == "Open issue"
    assert event["action_command"] == "gh issue view 16"
    assert event["action_url"].startswith("https://github.com/")
    assert event["privacy_summary"] == "No message body stored."
    assert "unexpected" not in event


def test_urgent_boolean_preserves_existing_renderer_behavior() -> None:
    event = build_event("message_received", "Ping", urgent=True)

    assert event["urgent"] is True
    assert event["urgency"] == "urgent"


def test_build_event_rejects_invalid_urgency_and_action_url() -> None:
    with pytest.raises(PetEventError, match="urgency"):
        build_event("status", "hello", urgency="soon")

    with pytest.raises(PetEventError, match="action_url"):
        build_event("status", "hello", action_url="javascript:alert(1)")
