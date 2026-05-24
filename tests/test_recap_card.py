from __future__ import annotations

from pathlib import Path

from PIL import Image

from hermes_pet.recap_card import AVATAR_RECT, CANVAS_SIZE, DEFAULT_FOOTER, _source_window_label, render_recap_card


def _make_payload(image_path: Path | None = None) -> dict[str, object]:
    pet: dict[str, object] = {
        "name_or_label": "Hermes",
        "species": "cat",
        "level": 3,
        "rarity": "common",
        "variant": "normal",
    }
    if image_path is not None:
        pet["image_path"] = str(image_path)
    return {
        "pet": pet,
        "dominant_moment": {
            "type": "job_finished",
            "headline": "Hermes kept the local state tidy, shipped the recap, and didn't leak a damn thing",
            "safe_summary": "One clean wrapped job, two safe proof points, and a shareable card without telemetry cosplay.",
        },
        "proof_points": [
            "1 successful wrapped job",
            "0 urgent events, 0 secrets, 0 bullshit",
        ],
        "caption": "Tiny operator, sharp receipts, no bullshit.",
        "footer": DEFAULT_FOOTER,
        "generated_at": "2026-05-23T23:15:00Z",
        "source_window": "24h",
    }


def test_source_window_label_formats_window_dict() -> None:
    assert _source_window_label({"since": "24h", "lookback_seconds": 86400}) == "Last 24h"
    assert _source_window_label("Last 7d") == "Last 7d"


def test_render_recap_card_is_deterministic_and_uses_supplied_image(tmp_path) -> None:
    image_path = tmp_path / "pet.png"
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(image_path)

    payload = _make_payload(image_path)
    output_a = tmp_path / "first" / "recap-card.png"
    output_b = tmp_path / "second" / "recap-card.png"

    result = render_recap_card(payload, output_a)
    render_recap_card(payload, output_b)

    assert result == output_a
    assert output_a.read_bytes() == output_b.read_bytes()

    rendered = Image.open(output_a).convert("RGBA")
    assert rendered.size == CANVAS_SIZE
    center = ((AVATAR_RECT[0] + AVATAR_RECT[2]) // 2, (AVATAR_RECT[1] + AVATAR_RECT[3]) // 2)
    assert rendered.getpixel(center) == (255, 0, 0, 255)


def test_render_recap_card_falls_back_without_pet_image(tmp_path) -> None:
    payload = _make_payload(None)
    output = tmp_path / "fallback" / "recap-card.png"

    render_recap_card(payload, output)

    rendered = Image.open(output).convert("RGBA")
    center = ((AVATAR_RECT[0] + AVATAR_RECT[2]) // 2, (AVATAR_RECT[1] + AVATAR_RECT[3]) // 2)
    outside = (AVATAR_RECT[0] - 16, AVATAR_RECT[1] + 24)

    assert rendered.size == CANVAS_SIZE
    assert rendered.getpixel(center) != rendered.getpixel(outside)
