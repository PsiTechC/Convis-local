#!/usr/bin/env python3
"""Generate an animated CONVIS logo GIF for the web client."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "convis-web" / "public" / "convis-logo.gif"

WIDTH, HEIGHT = 640, 320
FRAMES = 28
FPS = 20
TEXT = "CONVIS"
TOP_COLOR = "#050B14"
BOTTOM_COLOR = "#101F3D"
TEXT_COLOR = "#F8FAFC"
ACCENT = "#22D3EE"
ACCENT_PULSE = "#7DD3FC"
ICON_ACCENT = "#60A5FA"


def hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def lerp(start: int, end: int, t: float) -> int:
    return int(start + (end - start) * t)


def build_gradient() -> Image.Image:
    bg = Image.new("RGB", (WIDTH, HEIGHT))
    top = hex_to_rgb(TOP_COLOR)
    bottom = hex_to_rgb(BOTTOM_COLOR)
    pixels = bg.load()
    for y in range(HEIGHT):
        ratio = y / (HEIGHT - 1)
        row_color = tuple(lerp(top[i], bottom[i], ratio) for i in range(3))
        for x in range(WIDTH):
            pixels[x, y] = row_color
    return bg


def main() -> None:
    font = ImageFont.truetype("DejaVuSans-Bold.ttf", 140)
    sub_font = ImageFont.truetype("DejaVuSans.ttf", 36)
    gradient = build_gradient()
    frames = []
    text_bbox = font.getbbox(TEXT)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    text_x = (WIDTH - text_width) // 2 + 40
    text_y = (HEIGHT - text_height) // 2 - 10

    tagline = "Contextual Vision Intelligence"
    sub_bbox = sub_font.getbbox(tagline)
    sub_width = sub_bbox[2] - sub_bbox[0]
    sub_height = sub_bbox[3] - sub_bbox[1]
    sub_x = text_x
    sub_y = text_y + text_height + 10

    base_text_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    base_draw = ImageDraw.Draw(base_text_layer)
    base_draw.text((text_x, text_y), TEXT, font=font, fill=TEXT_COLOR)
    base_draw.text((sub_x, sub_y), tagline, font=sub_font, fill="#CBD5F5")

    for frame_idx in range(FRAMES):
        progress = frame_idx / FRAMES
        img = gradient.copy().convert("RGBA")
        img = Image.alpha_composite(img, base_text_layer)

        # Icon glow
        icon_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        icon_draw = ImageDraw.Draw(icon_layer)
        cx, cy = text_x - 120, HEIGHT // 2
        outer_r, inner_r = 70, 38
        icon_draw.ellipse(
            (cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r),
            outline=ICON_ACCENT,
            width=6,
        )
        icon_draw.ellipse(
            (cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r),
            fill=TOP_COLOR,
            outline=None,
        )
        sweep = 210
        start_angle = (progress * 360) % 360
        icon_draw.arc(
            (cx - outer_r - 6, cy - outer_r - 6, cx + outer_r + 6, cy + outer_r + 6),
            start=start_angle,
            end=start_angle + sweep,
            fill=ACCENT,
            width=6,
        )
        glow = icon_layer.copy().convert("L").filter(ImageFilter.GaussianBlur(12))
        glow_layer = Image.new(
            "RGBA", (WIDTH, HEIGHT), (*hex_to_rgb(ACCENT_PULSE), 0)
        )
        glow_layer.putalpha(glow)
        img = Image.alpha_composite(img, glow_layer)
        img = Image.alpha_composite(img, icon_layer)

        # Moving highlight across the brand text
        mask = Image.new("L", (WIDTH, HEIGHT), 0)
        mask_draw = ImageDraw.Draw(mask)
        highlight_width = WIDTH // 5
        x_pos = int(-highlight_width + (WIDTH + highlight_width * 2) * progress)
        mask_draw.rectangle(
            (x_pos, text_y - 20, x_pos + highlight_width, sub_y + sub_height + 20),
            fill=255,
        )
        mask = mask.filter(ImageFilter.GaussianBlur(radius=50))
        accent_layer = Image.new("RGBA", (WIDTH, HEIGHT), (*hex_to_rgb(ACCENT), 0))
        accent_layer.putalpha(mask)

        text_highlight = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        highlight_draw = ImageDraw.Draw(text_highlight)
        highlight_draw.text(
            (text_x, text_y),
            TEXT,
            font=font,
            fill=(*hex_to_rgb(ACCENT), 255),
        )
        highlight_draw.text(
            (sub_x, sub_y),
            tagline,
            font=sub_font,
            fill=(*hex_to_rgb(ACCENT_PULSE), 255),
        )
        text_highlight.putalpha(mask)

        img = Image.alpha_composite(img, text_highlight)
        frames.append(img.convert("P", palette=Image.ADAPTIVE))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        OUTPUT_PATH,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / FPS),
        loop=0,
        optimize=True,
    )
    print(f"Saved logo GIF to {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
