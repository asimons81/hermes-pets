"""Static recap card renderer for Hermes Pets.

This module is intentionally boring in the good way: it takes an already
sanitized payload, turns it into a single deterministic 1200x630 PNG, and
returns the output path. No state lookup, no network, no side effects beyond
writing the file you asked for.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

CANVAS_SIZE = (1200, 630)
CARD_RECT = (38, 38, 1162, 592)
LEFT_COLUMN_X = 74
RIGHT_COLUMN_X = 470
AVATAR_RECT = (74, 118, 434, 478)
DEFAULT_FOOTER = "Local recap, not posted by Hermes Pets"

FONT_REGULAR = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FONT_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

PALETTE: tuple[tuple[int, int, int], ...] = (
    (246, 173, 85),
    (126, 200, 255),
    (167, 139, 250),
    (86, 204, 242),
    (232, 121, 249),
    (52, 211, 153),
    (248, 113, 113),
    (250, 204, 21),
)

BACKGROUND_TOP = (8, 16, 31)
BACKGROUND_BOTTOM = (16, 25, 45)
CARD_FILL = (12, 19, 34, 242)
CARD_EDGE = (60, 75, 104, 200)
PANEL_FILL = (16, 25, 44, 210)
PANEL_EDGE = (76, 92, 126, 170)
TEXT_PRIMARY = (245, 247, 255, 255)
TEXT_SECONDARY = (181, 191, 216, 255)
TEXT_MUTED = (135, 149, 177, 255)
CAPTION_FILL = (10, 18, 33, 220)
CAPTION_EDGE = (86, 102, 138, 180)
FOOTER_FILL = (18, 28, 50, 190)

_RESAMPLE_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_text(value: object, default: str = "") -> str:
    text = str(value if value is not None else default)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(" ".join(part.split()) for part in text.split("\n"))


def _source_window_label(value: object, default: str = "") -> str:
    if isinstance(value, dict):
        since = _normalize_text(value.get("since"), default="")
        if since:
            return since if since.lower().startswith("last ") else f"Last {since}"
        lookback_seconds = value.get("lookback_seconds")
        if isinstance(lookback_seconds, (int, float)):
            seconds = int(lookback_seconds)
            if seconds % 86400 == 0 and seconds:
                return f"Last {seconds // 86400}d"
            if seconds % 3600 == 0 and seconds:
                return f"Last {seconds // 3600}h"
            if seconds % 60 == 0 and seconds:
                return f"Last {seconds // 60}m"
            if seconds:
                return f"Last {seconds}s"
    return _normalize_text(value, default=default)


def _humanize(value: object, default: str = "") -> str:
    text = _normalize_text(value, default=default)
    if not text:
        return default
    return text.replace("_", " ").replace("-", " ").strip().title()


def _color_from_seed(seed: str) -> tuple[int, int, int]:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return PALETTE[digest[0] % len(PALETTE)]


def _mix_color(
    left: tuple[int, int, int],
    right: tuple[int, int, int],
    weight: float,
) -> tuple[int, int, int]:
    weight = max(0.0, min(1.0, weight))
    inverse = 1.0 - weight
    return (
        int(round(left[0] * inverse + right[0] * weight)),
        int(round(left[1] * inverse + right[1] * weight)),
        int(round(left[2] * inverse + right[2] * weight)),
    )


def _rgba(color: tuple[int, ...], alpha: int = 255) -> tuple[int, int, int, int]:
    values = list(color)
    while len(values) < 3:
        values.append(0)
    if len(values) >= 4 and alpha == 255:
        return (int(values[0]), int(values[1]), int(values[2]), int(values[3]))
    return (int(values[0]), int(values[1]), int(values[2]), alpha)


def _load_font(path: Path, size: int) -> Any:
    if path.is_file():
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _measure_text(draw: Any, text: str, font: Any, spacing: int = 0) -> tuple[int, int]:
    bbox = draw.multiline_textbbox((0, 0), text or "", font=font, spacing=spacing, align="left")
    return int(round(bbox[2] - bbox[0])), int(round(bbox[3] - bbox[1]))


def _single_line_width(draw: Any, text: str, font: Any) -> int:
    bbox = draw.textbbox((0, 0), text or "", font=font)
    return int(round(bbox[2] - bbox[0]))


def _break_long_word(word: str, draw: Any, font: Any, max_width: int) -> list[str]:
    if not word:
        return [""]
    pieces: list[str] = []
    current = ""
    for char in word:
        candidate = current + char
        if current and _single_line_width(draw, candidate, font) > max_width:
            pieces.append(current)
            current = char
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces or [word]


def _wrap_text(text: str, draw: Any, font: Any, max_width: int) -> list[str]:
    paragraphs = _normalize_text(text).split("\n")
    lines: list[str] = []
    for paragraph in paragraphs:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        line = ""
        for word in words:
            candidate = word if not line else f"{line} {word}"
            if _single_line_width(draw, candidate, font) <= max_width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            if _single_line_width(draw, word, font) <= max_width:
                line = word
            else:
                chunks = _break_long_word(word, draw, font, max_width)
                if chunks:
                    if len(chunks) > 1:
                        lines.extend(chunks[:-1])
                    line = chunks[-1]
        if line or not words:
            lines.append(line)
    return lines or [""]


def _truncate_lines(lines: list[str], max_lines: int | None) -> list[str]:
    if max_lines is None or len(lines) <= max_lines:
        return lines
    if max_lines <= 0:
        return []
    clipped = lines[:max_lines]
    clipped[-1] = clipped[-1].rstrip() + ("…" if clipped[-1].strip() else "…")
    return clipped


def _fit_text_block(
    draw: Any,
    text: str,
    *,
    font_path: Path,
    size_range: range,
    max_width: int,
    max_height: int,
    spacing: int = 4,
    max_lines: int | None = None,
) -> tuple[Any, list[str]]:
    candidate_font = _load_font(font_path, size_range.start)
    candidate_lines = [""]
    for size in size_range:
        font = _load_font(font_path, size)
        lines = _truncate_lines(_wrap_text(text, draw, font, max_width), max_lines)
        width, height = _measure_text(draw, "\n".join(lines), font, spacing=spacing)
        if width <= max_width and height <= max_height:
            return font, lines
        candidate_font = font
        candidate_lines = lines
    return candidate_font, candidate_lines


def _draw_block(
    draw: Any,
    box: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int] | None = None,
    radius: int = 26,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2 if outline else 0)


def _draw_pill(
    draw: Any,
    origin: tuple[int, int],
    text: str,
    *,
    fill: tuple[int, int, int, int],
    accent: tuple[int, int, int, int],
    font: Any,
    padding_x: int = 18,
    padding_y: int = 11,
) -> tuple[int, int, int, int]:
    width, height = _measure_text(draw, text, font, spacing=0)
    x, y = origin
    box = (x, y, x + width + padding_x * 2, y + height + padding_y * 2)
    draw.rounded_rectangle(box, radius=999, fill=fill, outline=accent, width=2)
    draw.text((x + padding_x, y + padding_y), text, font=font, fill=TEXT_PRIMARY)
    return box


def _first_token(text: str, fallback: str) -> str:
    parts = [part for part in _normalize_text(text).replace("/", " ").replace(".", " ").split() if part]
    if not parts:
        return fallback
    initials = "".join(part[0] for part in parts[:2])
    return initials or fallback


def _pet_label(pet: dict[str, Any]) -> str:
    label = _normalize_text(pet.get("name_or_label") or pet.get("name") or pet.get("label") or pet.get("species"), default="Hermes")
    return label or "Hermes"


def _pet_species(pet: dict[str, Any]) -> str:
    return _normalize_text(pet.get("species") or pet.get("species_label") or "pet", default="pet") or "pet"


def _pet_image_path(pet: dict[str, Any]) -> Path | None:
    candidates: list[object] = [
        pet.get("image_path"),
        pet.get("sprite_path"),
        pet.get("preview_path"),
        pet.get("image"),
    ]
    visual = _as_dict(pet.get("visual"))
    candidates.extend([visual.get("path"), visual.get("image_path"), visual.get("sprite_path")])
    for candidate in candidates:
        if not candidate or not isinstance(candidate, (str, Path)):
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return path
    return None


def _render_background(canvas: Image.Image, accent: tuple[int, int, int]) -> None:
    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size
    for y in range(height):
        row_color = _mix_color(BACKGROUND_TOP, BACKGROUND_BOTTOM, y / max(1, height - 1))
        draw.line((0, y, width, y), fill=row_color + (255,))

    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-180, -130, 430, 470), fill=_rgba(accent, 58))
    glow_draw.ellipse((730, -100, 1290, 420), fill=_rgba(_mix_color(accent, (255, 255, 255), 0.2), 40))
    glow_draw.ellipse((860, 320, 1340, 860), fill=_rgba(_mix_color(accent, BACKGROUND_BOTTOM, 0.35), 36))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(62)))


def _render_card_shell(canvas: Image.Image, accent: tuple[int, int, int]) -> None:
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_box = (CARD_RECT[0], CARD_RECT[1] + 14, CARD_RECT[2], CARD_RECT[3] + 14)
    shadow_draw.rounded_rectangle(shadow_box, radius=38, fill=(0, 0, 0, 126))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))

    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    _draw_block(draw, CARD_RECT, fill=CARD_FILL, outline=CARD_EDGE, radius=38)
    left_bar = (CARD_RECT[0] + 2, CARD_RECT[1] + 2, CARD_RECT[0] + 10, CARD_RECT[3] - 2)
    draw.rounded_rectangle(left_bar, radius=4, fill=_rgba(accent, 220))
    canvas.alpha_composite(layer)


def _render_pet_panel(canvas: Image.Image, draw: Any, pet: dict[str, Any], accent: tuple[int, int, int]) -> None:
    panel_fill = _mix_color((19, 29, 50), accent, 0.12)
    panel_box = (60, 78, 438, 552)
    _draw_block(draw, panel_box, fill=_rgba(panel_fill, 216), outline=PANEL_EDGE, radius=32)

    label_font = _load_font(FONT_BOLD, 22)
    name_font = _load_font(FONT_BOLD, 36)
    meta_font = _load_font(FONT_REGULAR, 20)
    chip_font = _load_font(FONT_BOLD, 20)

    pet_label = _pet_label(pet)
    species = _pet_species(pet)
    rarity = _normalize_text(pet.get("rarity") or pet.get("tier"), default="")
    level = pet.get("level")
    variant = _normalize_text(pet.get("variant") or pet.get("form"), default="")

    draw.text((LEFT_COLUMN_X, 92), "PET PROFILE", font=label_font, fill=_rgba(accent, 255))
    draw.text((LEFT_COLUMN_X, 128), pet_label, font=name_font, fill=TEXT_PRIMARY)
    subtitle = species
    if rarity:
        subtitle = f"{subtitle} · {rarity}"
    draw.text((LEFT_COLUMN_X, 170), subtitle, font=meta_font, fill=TEXT_SECONDARY)

    avatar_box = AVATAR_RECT
    _draw_block(draw, avatar_box, fill=_rgba(_mix_color(accent, BACKGROUND_BOTTOM, 0.58), 255), outline=_rgba(accent, 200), radius=30)
    if image_path := _pet_image_path(pet):
        with Image.open(image_path) as loaded:
            avatar = ImageOps.fit(
                loaded.convert("RGBA"),
                (avatar_box[2] - avatar_box[0] - 18, avatar_box[3] - avatar_box[1] - 18),
                method=_RESAMPLE_LANCZOS,
            )
        mask = Image.new("L", avatar.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle((0, 0, avatar.size[0] - 1, avatar.size[1] - 1), radius=28, fill=255)
        avatar_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        avatar_layer.paste(avatar, (avatar_box[0] + 9, avatar_box[1] + 9), mask)
        canvas.alpha_composite(avatar_layer)
    else:
        badge = Image.new("RGBA", (avatar_box[2] - avatar_box[0] - 18, avatar_box[3] - avatar_box[1] - 18), (0, 0, 0, 0))
        badge_draw = ImageDraw.Draw(badge)
        badge_fill = _mix_color(accent, (255, 255, 255), 0.12)
        badge_draw.rounded_rectangle((0, 0, badge.size[0] - 1, badge.size[1] - 1), radius=28, fill=_rgba(badge_fill, 255))
        badge_draw.ellipse((20, 22, badge.size[0] - 20, badge.size[1] - 22), outline=_rgba(_mix_color(accent, (255, 255, 255), 0.28), 180), width=3)
        initials = _first_token(pet_label, species[:2].upper() or "HP")
        initials_font = _load_font(FONT_BOLD, 68)
        initials_box = badge_draw.textbbox((0, 0), initials, font=initials_font)
        initials_w = initials_box[2] - initials_box[0]
        initials_h = initials_box[3] - initials_box[1]
        badge_draw.text(
            ((badge.size[0] - initials_w) / 2, (badge.size[1] - initials_h) / 2 - 10),
            initials,
            font=initials_font,
            fill=TEXT_PRIMARY,
        )
        species_font = _load_font(FONT_REGULAR, 18)
        species_text = _humanize(species, default="PET")
        species_box = badge_draw.textbbox((0, 0), species_text, font=species_font)
        species_w = species_box[2] - species_box[0]
        badge_draw.text(
            ((badge.size[0] - species_w) / 2, badge.size[1] - 56),
            species_text.upper(),
            font=species_font,
            fill=TEXT_SECONDARY,
        )
        badge_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        badge_layer.paste(badge, (avatar_box[0] + 9, avatar_box[1] + 9), badge)
        canvas.alpha_composite(badge_layer)

    chips_y = 500
    chip_x = LEFT_COLUMN_X
    chips: list[str] = []
    if level is not None:
        chips.append(f"Lv. {level}")
    if species:
        chips.append(_humanize(species, default=species))
    if variant and variant.lower() != "normal":
        chips.append(_humanize(variant, default=variant))
    if rarity and rarity.lower() not in {"normal", "common"}:
        chips.append(_humanize(rarity, default=rarity))
    if not chips:
        chips.append("Local state")
    for chip in chips[:3]:
        chip_box = _draw_pill(
            draw,
            (chip_x, chips_y),
            chip,
            fill=_rgba(_mix_color(accent, BACKGROUND_BOTTOM, 0.35), 210),
            accent=_rgba(_mix_color(accent, (255, 255, 255), 0.12), 220),
            font=chip_font,
            padding_x=14,
            padding_y=9,
        )
        chip_x = chip_box[2] + 12


def _render_right_content(canvas: Image.Image, draw: Any, payload: dict[str, Any], accent: tuple[int, int, int]) -> None:
    dominant = _as_dict(payload.get("dominant_moment"))
    counts = _as_dict(payload.get("counts"))
    generated_at = _normalize_text(payload.get("generated_at"), default="")
    source_window = _source_window_label(payload.get("source_window"), default="")

    badge_font = _load_font(FONT_BOLD, 22)
    headline_font, headline_lines = _fit_text_block(
        draw,
        dominant.get("headline") or dominant.get("safe_summary") or payload.get("headline") or "Quiet local recap",
        font_path=FONT_BOLD,
        size_range=range(54, 35, -2),
        max_width=620,
        max_height=148,
        spacing=8,
        max_lines=3,
    )
    detail_font, detail_lines = _fit_text_block(
        draw,
        dominant.get("safe_summary") or _normalize_text(payload.get("summary"), default=""),
        font_path=FONT_REGULAR,
        size_range=range(28, 19, -1),
        max_width=620,
        max_height=78,
        spacing=4,
        max_lines=2,
    )

    draw.text((RIGHT_COLUMN_X, 92), "LOCAL RECAP", font=badge_font, fill=_rgba(accent, 255))
    if source_window:
        window_font = _load_font(FONT_REGULAR, 18)
        pill_x = 950
        pill_width, pill_height = _measure_text(draw, source_window, window_font)
        pill_box = (pill_x, 82, pill_x + pill_width + 26, 82 + pill_height + 18)
        draw.rounded_rectangle(pill_box, radius=999, fill=_rgba(_mix_color(accent, BACKGROUND_BOTTOM, 0.38), 210), outline=_rgba(accent, 120), width=2)
        draw.text((pill_x + 13, 91), source_window, font=window_font, fill=TEXT_SECONDARY)

    headline_top = 136
    draw.rounded_rectangle((RIGHT_COLUMN_X, headline_top + 10, RIGHT_COLUMN_X + 36, headline_top + 128), radius=18, fill=_rgba(accent, 255))
    draw.multiline_text((RIGHT_COLUMN_X + 54, headline_top), "\n".join(headline_lines), font=headline_font, fill=TEXT_PRIMARY, spacing=8)
    headline_bbox = draw.multiline_textbbox((RIGHT_COLUMN_X + 54, headline_top), "\n".join(headline_lines), font=headline_font, spacing=8)
    detail_y = max(268, headline_bbox[3] + 18)

    if detail_lines:
        draw.multiline_text((RIGHT_COLUMN_X, detail_y), "\n".join(detail_lines), font=detail_font, fill=TEXT_SECONDARY, spacing=4)
        detail_bbox = draw.multiline_textbbox((RIGHT_COLUMN_X, detail_y), "\n".join(detail_lines), font=detail_font, spacing=4)
        receipts_y = detail_bbox[3] + 22
    else:
        receipts_y = detail_y + 6

    receipts_title_font = _load_font(FONT_BOLD, 20)
    draw.text((RIGHT_COLUMN_X, receipts_y), "Receipts", font=receipts_title_font, fill=TEXT_PRIMARY)

    proof_lines: list[str] = []
    proof_points = payload.get("proof_points")
    if isinstance(proof_points, list):
        for item in proof_points:
            if isinstance(item, dict):
                candidate = _normalize_text(item.get("text") or item.get("label") or item.get("summary") or item.get("title"), default="")
            else:
                candidate = _normalize_text(item, default="")
            if candidate:
                proof_lines.append(candidate)
    if not proof_lines:
        if counts.get("jobs_total") is not None:
            proof_lines.append(f"{counts['jobs_total']} total jobs in the local window")
        if counts.get("jobs_succeeded") is not None:
            proof_lines.append(f"{counts['jobs_succeeded']} succeeded")
        if counts.get("jobs_failed") is not None:
            proof_lines.append(f"{counts['jobs_failed']} failed")
        if counts.get("events_total") is not None:
            proof_lines.append(f"{counts['events_total']} events tracked")
    if not proof_lines:
        proof_lines = ["Quiet local session recap"]

    receipt_font = _load_font(FONT_REGULAR, 22)
    receipt_y = receipts_y + 34
    for line in proof_lines[:3]:
        line_lines = _truncate_lines(_wrap_text(line, draw, receipt_font, 600), 2)
        row_text = "\n".join(line_lines)
        row_height = _measure_text(draw, row_text, receipt_font, spacing=4)[1]
        row_box = (RIGHT_COLUMN_X, receipt_y, RIGHT_COLUMN_X + 640, receipt_y + row_height + 22)
        draw.rounded_rectangle(row_box, radius=18, fill=_rgba(PANEL_FILL, 220), outline=_rgba(accent, 128), width=1)
        draw.ellipse((RIGHT_COLUMN_X + 16, receipt_y + 16, RIGHT_COLUMN_X + 28, receipt_y + 28), fill=_rgba(accent, 255))
        draw.multiline_text((RIGHT_COLUMN_X + 42, receipt_y + 11), row_text, font=receipt_font, fill=TEXT_PRIMARY, spacing=4)
        receipt_y = row_box[3] + 10

    caption = _normalize_text(payload.get("caption"), default=DEFAULT_FOOTER)
    caption_box_top = 500
    caption_box = (RIGHT_COLUMN_X, caption_box_top, RIGHT_COLUMN_X + 640, 566)
    draw.rounded_rectangle(caption_box, radius=24, fill=_rgba(CAPTION_FILL, 235), outline=_rgba(CAPTION_EDGE, 190), width=2)
    quote_font = _load_font(FONT_BOLD, 32)
    draw.text((RIGHT_COLUMN_X + 20, caption_box_top + 12), "“", font=quote_font, fill=_rgba(accent, 255))
    caption_font, caption_lines = _fit_text_block(
        draw,
        caption,
        font_path=FONT_BOLD,
        size_range=range(28, 19, -1),
        max_width=570,
        max_height=50,
        spacing=4,
        max_lines=2,
    )
    draw.multiline_text((RIGHT_COLUMN_X + 52, caption_box_top + 18), "\n".join(caption_lines), font=caption_font, fill=TEXT_PRIMARY, spacing=4)

    footer_text = _normalize_text(payload.get("footer"), default=DEFAULT_FOOTER)
    footer_font = _load_font(FONT_REGULAR, 18)
    footer_fill = _rgba(_mix_color(accent, BACKGROUND_BOTTOM, 0.25), 208)
    footer_box = (RIGHT_COLUMN_X, 568, 1116, 592)
    draw.rounded_rectangle(footer_box, radius=16, fill=_rgba(FOOTER_FILL, 180), outline=_rgba(accent, 95), width=1)
    draw.text((RIGHT_COLUMN_X + 16, 572), footer_text, font=footer_font, fill=TEXT_MUTED)
    if generated_at:
        generated_width = _single_line_width(draw, generated_at, footer_font)
        draw.text((1116 - generated_width - 16, 572), generated_at, font=footer_font, fill=footer_fill)


def render_recap_card(payload: dict[str, Any], output_path: str | Path) -> Path:
    """Render a deterministic recap card PNG to ``output_path``.

    The renderer intentionally trusts its caller to hand it a sanitized payload.
    It never reads live Hermes Pets state by itself.
    """

    data = _as_dict(payload)
    output = Path(output_path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)

    pet = _as_dict(data.get("pet"))
    accent_seed = _pet_label(pet) + "|" + _pet_species(pet)
    accent = _color_from_seed(accent_seed)

    canvas = Image.new("RGBA", CANVAS_SIZE, BACKGROUND_TOP + (255,))
    _render_background(canvas, accent)
    _render_card_shell(canvas, accent)

    content_layer = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    content_draw = ImageDraw.Draw(content_layer)
    _render_pet_panel(content_layer, content_draw, pet, accent)
    _render_right_content(content_layer, content_draw, data, accent)
    canvas.alpha_composite(content_layer)

    canvas.save(output, format="PNG", optimize=False, compress_level=6)
    return output
