#!/usr/bin/env python3
"""Render a user-facing grounded cat POV comic page.

This is a deterministic renderer for local validation. It is not a substitute
for a model-native image-reference redraw, but it must be good enough to show
as a final comic artifact instead of a storyboard or contact sheet.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


LABELS = [
    ("\u5730\u9762\u4e0a\u7ebf\u4e86", "route"),
    ("\u8def\u7ebf\u85cf\u5728\u8349\u91cc", "map"),
    ("\u6293\u5230\u534a\u4e2a\u58f0\u97f3", "radar"),
    ("\u5feb\uff0c\u522b\u88ab\u4e16\u754c\u53d1\u73b0", "danger"),
    ("\u4e0a\u9762\u4e5f\u6709\u60c5\u62a5", "signal"),
    ("\u7b54\u6848\u5728\u91cc\u9762\u88c5\u7761", "door"),
    ("\u6211\u53ea\u9760\u8fd1\u4e00\u70b9", "watch"),
    ("\u6848\u4ef6\u5148\u6536\u8fdb\u80e1\u987b", "stamp"),
]

TITLE = "\u4eca\u5929\u7684\u5730\u9762\u8c03\u67e5"
SUBTITLE = "\u788e\u77f3\u3001\u8349\u4e1b\u3001\u843d\u53f6\u548c\u534a\u4e2a\u58f0\u97f3\uff0c\u90fd\u88ab\u6211\u6536\u8fdb\u4e86\u79d8\u5bc6\u6863\u6848\u3002"
FOOTER = "\u7ed3\u8bba\uff1a\u4e16\u754c\u6682\u65f6\u8fd8\u6ca1\u6709\u53d1\u73b0\u6211\u3002"

PALETTES = [
    ((42, 42, 38), (206, 188, 145), (255, 244, 204)),
    ((30, 36, 32), (152, 177, 126), (247, 236, 198)),
    ((35, 30, 26), (170, 134, 94), (253, 234, 192)),
    ((28, 34, 40), (112, 145, 146), (232, 221, 190)),
    ((36, 35, 44), (128, 134, 176), (238, 225, 196)),
    ((42, 32, 25), (184, 155, 100), (250, 230, 180)),
    ((32, 36, 30), (132, 160, 108), (244, 232, 194)),
    ((38, 30, 28), (180, 144, 104), (252, 230, 186)),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--highlights", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    highlights = json.loads(Path(args.highlights).read_text(encoding="utf-8"))[:8]
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    render(highlights, output)
    print(output)


def render(highlights: list[dict[str, Any]], output: Path) -> None:
    random.seed(42)
    width, height = 1600, 1600
    margin, gutter = 38, 16
    page = paper(width, height)
    draw = ImageDraw.Draw(page)

    layout = [
        (margin, margin, 700, 370),
        (margin + 700 + gutter, margin, 270, 370),
        (margin + 700 + gutter + 270 + gutter, margin, width - (margin + 700 + gutter + 270 + gutter) - margin, 370),
        (margin, margin + 370 + gutter, 650, 720),
        (margin + 650 + gutter, margin + 370 + gutter, 390, 340),
        (margin + 650 + gutter + 390 + gutter, margin + 370 + gutter, width - (margin + 650 + gutter + 390 + gutter) - margin, 720),
        (margin + 650 + gutter, margin + 370 + gutter + 340 + gutter, 390, 364),
        (margin, 1144, width - 2 * margin, height - 1144 - margin),
    ]

    for index, box in enumerate(layout[: min(len(highlights), 7)]):
        item = highlights[index]
        label, kind = LABELS[index]
        panel = make_panel(Path(item["evidence_frame"]), box[2], box[3], PALETTES[index], kind)
        paste_panel(page, box, panel)
        draw_panel_number(draw, box, index + 1)
        add_bubble(draw, box, label, index)

    draw_footer_panel(draw, layout[7])
    page.save(output)


def paper(width: int, height: int) -> Image.Image:
    base = Image.new("RGB", (width, height), (238, 226, 210))
    noise = Image.new("L", (width, height), 0)
    nd = ImageDraw.Draw(noise)
    for _ in range(9000):
        nd.point((random.randrange(width), random.randrange(height)), fill=random.randrange(4, 24))
    noise = noise.filter(ImageFilter.GaussianBlur(1.2))
    return Image.composite(Image.new("RGB", (width, height), (246, 235, 216)), base, noise)


def make_panel(frame: Path, width: int, height: int, palette: tuple[tuple[int, int, int], ...], kind: str) -> Image.Image:
    src = Image.open(frame).convert("RGB")
    src = fit_cover(src, width, height)
    gray = ImageOps.grayscale(src)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    color = ImageOps.colorize(gray, black=palette[0], mid=palette[1], white=palette[2])
    color = ImageEnhance.Contrast(color).enhance(1.12)
    color = ImageEnhance.Color(color).enhance(1.06)
    poster = ImageOps.posterize(color.filter(ImageFilter.SMOOTH_MORE), 5)

    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.autocontrast(edges)
    mask = edges.point(lambda p: 210 if p > 38 else 0, mode="L").filter(ImageFilter.MaxFilter(3))
    ink = Image.new("RGB", (width, height), (22, 21, 20))
    panel = Image.composite(ink, poster, mask)
    panel = add_event_layer(panel.convert("RGBA"), kind).convert("RGB")
    return panel


def add_event_layer(panel: Image.Image, kind: str) -> Image.Image:
    draw = ImageDraw.Draw(panel, "RGBA")
    width, height = panel.size
    amber = (255, 190, 53, 215)
    green = (76, 196, 133, 185)
    red = (239, 77, 72, 190)
    blue = (95, 175, 230, 190)
    ink = (28, 24, 22, 230)

    if kind == "route":
        points = [(40, height - 62), (width * 0.23, height - 110), (width * 0.43, height - 92), (width * 0.64, height - 138), (width - 55, height - 122)]
        draw.line(points, fill=amber, width=9)
        for x, y in points[1:-1]:
            draw_paw(draw, x, y - 4, 28, green)
        for x, y in [(width * 0.30, 70), (width * 0.38, 45), (width * 0.48, 80)]:
            draw.rounded_rectangle([x - 18, y - 18, x + 18, y + 18], radius=5, outline=amber, width=5)
    elif kind == "map":
        for offset in [0, 55, 110, 165, 220]:
            draw.arc([offset - 20, 35, offset + 280, height + 50], 208, 334, fill=amber, width=6)
        for x, y in [(width * 0.68, height * 0.35), (width * 0.50, height * 0.63), (width * 0.78, height * 0.72)]:
            draw.line([x - 17, y - 17, x + 17, y + 17], fill=red, width=5)
            draw.line([x + 17, y - 17, x - 17, y + 17], fill=red, width=5)
        draw.arc([35, 40, 115, 125], 30, 330, fill=blue, width=5)
    elif kind == "radar":
        cx, cy = int(width * 0.60), int(height * 0.48)
        for radius in [35, 75, 120]:
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=green, width=6)
        draw.ellipse([cx - 12, cy - 8, cx + 12, cy + 8], fill=ink)
        draw.text((cx + 30, cy - 55), "?", font=load_font(72, True), fill=amber)
    elif kind == "danger":
        for start in range(-30, width + 60, 50):
            draw.line([start, height - 45, start + 28, height - 130], fill=red, width=8)
        draw.line([(55, height - 80), (170, height - 150), (285, height - 138), (width - 95, height - 210)], fill=green, width=7)
        draw.polygon([(width - 125, 70), (width - 75, 165), (width - 175, 165)], fill=(239, 77, 72, 80), outline=red)
    elif kind == "signal":
        for x in [width * 0.25, width * 0.38, width * 0.52, width * 0.66]:
            draw.line([x, 28, x + 28, 120], fill=blue, width=7)
            draw.line([x + 28, 120, x - 12, 105], fill=blue, width=7)
        for radius in [70, 115, 160]:
            draw.arc([width * 0.5 - radius, 30, width * 0.5 + radius, 30 + radius], 20, 160, fill=amber, width=6)
        draw.text((width * 0.12, height * 0.67), "!", font=load_font(82, True), fill=red)
    elif kind == "door":
        door = [int(width * 0.52), int(height * 0.28), int(width * 0.88), int(height * 0.80)]
        draw.rounded_rectangle(door, radius=20, fill=(255, 199, 66, 80), outline=amber, width=8)
        draw.text((door[0] + 35, door[1] + 38), "?", font=load_font(82, True), fill=red)
        draw.arc([door[0] - 50, door[1] + 25, door[2] + 50, door[3] + 70], 200, 340, fill=green, width=7)
        draw_paw(draw, door[0] - 18, door[3] - 40, 34, green)
    elif kind == "watch":
        draw.arc([40, 60, width - 40, height - 80], 12, 330, fill=amber, width=7)
        draw.text((width - 145, height - 118), "CASE", font=load_font(34, True), fill=red)
    return panel


def paste_panel(page: Image.Image, box: tuple[int, int, int, int], panel: Image.Image) -> None:
    x, y, width, height = box
    mask = Image.new("L", (width, height), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, width - 1, height - 1], radius=4, fill=255)
    page.paste(panel, (x, y), mask)
    draw = ImageDraw.Draw(page)
    draw.rectangle([x, y, x + width, y + height], outline=(18, 17, 16), width=8)


def draw_footer_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x, y, width, height = box
    draw.rectangle([x, y, x + width, y + height], fill=(42, 36, 32), outline=(18, 17, 16), width=8)
    draw.text((x + 34, y + 40), TITLE, font=load_font(52, True), fill=(255, 241, 207))
    draw.text((x + 36, y + 116), SUBTITLE, font=load_font(30), fill=(231, 214, 185))
    draw.text((x + 36, y + 178), FOOTER, font=load_font(34, True), fill=(255, 232, 165))
    draw_paw(draw, x + width - 100, y + height - 86, 42, (255, 232, 165))


def draw_panel_number(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], number: int) -> None:
    x, y, _, _ = box
    draw.rounded_rectangle([x + 16, y + 16, x + 64, y + 62], radius=12, fill=(255, 249, 216), outline=(20, 18, 16), width=3)
    draw.text((x + 32, y + 22), str(number), font=load_font(26, True), fill=(24, 22, 20))


def add_bubble(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, index: int) -> None:
    x, y, width, height = box
    positions = [
        (x + width - 250, y + 28, x + width - 110, y + 150, 28),
        (x + 24, y + height - 132, x + width * 0.55, y + height * 0.50, 21),
        (x + 28, y + 28, x + width * 0.65, y + height * 0.47, 21),
        (x + 30, y + 34, x + width * 0.52, y + height * 0.48, 28),
        (x + 22, y + 24, x + width * 0.70, y + height * 0.52, 21),
        (x + 30, y + 34, x + width * 0.60, y + height * 0.58, 28),
        (x + 34, y + height - 124, x + width * 0.55, y + height * 0.50, 22),
    ]
    bx, by, tx, ty, size = positions[index]
    draw_bubble(draw, int(bx), int(by), text, (int(tx), int(ty)), load_font(size, True))


def draw_bubble(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, tail: tuple[int, int], font: ImageFont.ImageFont) -> None:
    lines = wrap_text(text, 8)
    line_height = int(getattr(font, "size", 24) * 1.18)
    widths = [draw.textbbox((0, 0), line, font=font)[2] for line in lines]
    box_width = max(widths) + 42
    box_height = line_height * len(lines) + 34
    draw.rounded_rectangle([x, y, x + box_width, y + box_height], radius=24, fill=(255, 250, 220), outline=(25, 24, 22), width=4)
    draw.polygon([(x + box_width * 0.25, y + box_height - 2), (x + box_width * 0.42, y + box_height - 2), tail], fill=(255, 250, 220), outline=(25, 24, 22))
    yy = y + 15
    for line in lines:
        draw.text((x + 21, yy), line, font=font, fill=(35, 31, 28))
        yy += line_height


def wrap_text(text: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        current += char
        if len(current) >= max_chars:
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return lines[:2]


def draw_paw(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, fill: tuple[int, ...]) -> None:
    draw.ellipse([x - size * 0.35, y - size * 0.05, x + size * 0.35, y + size * 0.55], fill=fill)
    for dx, dy in [(-0.32, -0.28), (-0.1, -0.43), (0.14, -0.43), (0.36, -0.28)]:
        draw.ellipse([x + size * dx - size * 0.14, y + size * dy - size * 0.14, x + size * dx + size * 0.14, y + size * dy + size * 0.14], fill=fill)


def fit_cover(img: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / img.width, height / img.height)
    resized = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc") if bold else Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


if __name__ == "__main__":
    main()
