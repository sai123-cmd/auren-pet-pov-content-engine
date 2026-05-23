#!/usr/bin/env python3
"""Render a POV-locked comic page from real selected keyframes.

This renderer intentionally preserves each source frame's camera angle,
composition, occlusion, and subject scale. It can stylize the pixels and add
short pet-thought bubbles, but it must not add a recurring pet avatar, ears,
face, paws, or a third-person camera unless those are already visible in the
source frame.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


BUBBLES = [
    "\u8def\u5148\u9192\u4e86",
    "\u5c4b\u9876\u4e5f\u6709\u5473\u9053",
    "\u6c34\u8fb9\u6362\u4e86\u6c14\u5473",
    "\u6211\u6765\u786e\u8ba4\u4e00\u4e0b",
    "\u8fd9\u91cc\u50cf\u4e00\u5835\u5899",
    "\u4e0b\u9762\u4e5f\u6709\u8def",
    "\u4ed6\u4eec\u4e5f\u5728\u8fd9\u513f",
    "\u4eca\u5929\u85cf\u8fdb\u677e\u9488\u91cc",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--highlights", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--frame-dir", default="")
    args = parser.parse_args()

    render_pov_locked_comic_page(
        highlights_path=Path(args.highlights),
        output_path=Path(args.output),
        frame_dir=Path(args.frame_dir) if args.frame_dir else None,
    )
    print(Path(args.output).resolve())


def render_pov_locked_comic_page(highlights_path: Path, output_path: Path, frame_dir: Path | None = None) -> None:
    highlights = json.loads(highlights_path.read_text(encoding="utf-8"))[:8]
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if frame_dir is None:
        frame_dir = output_path.parent / "comic_pov_locked_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    panels = []
    for idx, item in enumerate(highlights, 1):
        frame = choose_or_extract_frame(item, idx, frame_dir)
        panels.append((item, frame))
    render_page(panels, output_path)


def choose_or_extract_frame(item: dict[str, Any], idx: int, frame_dir: Path) -> Path:
    source = Path(str(item.get("source_path", "")))
    start = to_float(item.get("start"))
    end = to_float(item.get("end"))
    section = str(item.get("section", ""))
    duration = max(0.0, end - start)

    # Use real frames from the original video. These offsets pick the most
    # readable moment without changing perspective or inventing a new subject.
    offset = 0.5
    if "\u9f3b" in section:
        offset = 0.90
    elif "\u4eba\u7c7b" in section:
        offset = 0.50
    elif "\u6c34\u8fb9" in section:
        offset = 0.48
    elif "\u677e\u9488" in section:
        offset = 0.72
    timestamp = start + duration * offset

    extracted = frame_dir / f"{idx:02d}_{item.get('segment_id', 'segment')}_pov.jpg"
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg and source.exists():
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(extracted),
            ],
            check=False,
        )
        if extracted.exists() and extracted.stat().st_size > 0:
            return extracted

    fallback = Path(str(item.get("primary_comic_frame", "")))
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"No usable frame for {item.get('segment_id')}")


def render_page(panels: list[tuple[dict[str, Any], Path]], output_path: Path) -> None:
    width, height = 1600, 1600
    margin, gutter = 20, 16
    page = Image.new("RGB", (width, height), (16, 15, 14))
    draw = ImageDraw.Draw(page)

    boxes = [
        (margin, margin, 734, 360),
        (margin + 734 + gutter, margin, 390, 360),
        (margin + 734 + gutter + 390 + gutter, margin, 420, 360),
        (margin, margin + 360 + gutter, 500, 540),
        (margin + 500 + gutter, margin + 360 + gutter, 500, 540),
        (margin + 500 + gutter + 500 + gutter, margin + 360 + gutter, 544, 540),
        (margin, margin + 360 + gutter + 540 + gutter, 772, 628),
        (margin + 772 + gutter, margin + 360 + gutter + 540 + gutter, 772, 628),
    ]

    for idx, ((item, frame), box) in enumerate(zip(panels, boxes), 0):
        panel = make_panel(frame, box[2], box[3])
        x, y, w, h = box
        page.paste(panel, (x, y))
        draw.rectangle([x, y, x + w, y + h], outline=(248, 242, 232), width=3)
        draw.rectangle([x, y, x + w, y + h], outline=(0, 0, 0), width=8)
        bubble = str(item.get("caption") or BUBBLES[min(idx, len(BUBBLES) - 1)])
        add_bubble(draw, box, bubble, idx)

    page = add_paper_grain(page)
    page.save(output_path, quality=94)


def make_panel(frame: Path, width: int, height: int) -> Image.Image:
    src = Image.open(frame).convert("RGB")
    src = ImageOps.exif_transpose(src)
    stylized = painterly(src)
    contained = ImageOps.contain(stylized, (width, height), Image.Resampling.LANCZOS)
    matte = panel_matte(stylized, width, height)
    x = (width - contained.width) // 2
    y = (height - contained.height) // 2
    matte.paste(contained, (x, y))
    return matte


def painterly(src: Image.Image) -> Image.Image:
    cv_painted = cv2_painterly(src)
    if cv_painted is not None:
        return cv_painted

    img = ImageOps.autocontrast(src, cutoff=1)
    img = ImageEnhance.Color(img).enhance(1.10)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    wash = img.filter(ImageFilter.SMOOTH_MORE).filter(ImageFilter.SMOOTH_MORE)
    wash = ImageOps.posterize(wash, 6)

    gray = ImageOps.grayscale(img).filter(ImageFilter.SMOOTH)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.autocontrast(edges)
    edge_mask = edges.point(lambda value: 150 if value > 42 else 0, mode="L").filter(ImageFilter.MaxFilter(3))
    ink = Image.new("RGB", wash.size, (24, 22, 20))
    return Image.composite(ink, wash, edge_mask)


def cv2_painterly(src: Image.Image) -> Image.Image | None:
    try:
        import cv2
        import numpy as np
    except Exception:
        return None
    rgb = np.array(ImageOps.autocontrast(src, cutoff=1))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    bgr = cv2.edgePreservingFilter(bgr, flags=1, sigma_s=48, sigma_r=0.32)
    bgr = cv2.stylization(bgr, sigma_s=55, sigma_r=0.38)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    painted = Image.fromarray(rgb)
    painted = ImageEnhance.Color(painted).enhance(1.08)
    painted = ImageEnhance.Contrast(painted).enhance(1.06)

    gray = ImageOps.grayscale(src).filter(ImageFilter.SMOOTH)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.autocontrast(edges)
    edge_mask = edges.point(lambda value: 95 if 46 < value < 220 else 0, mode="L").filter(ImageFilter.MaxFilter(1))
    ink = Image.new("RGB", painted.size, (28, 25, 22))
    return Image.composite(ink, painted, edge_mask)


def panel_matte(stylized: Image.Image, width: int, height: int) -> Image.Image:
    cover = ImageOps.fit(stylized, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    cover = cover.filter(ImageFilter.GaussianBlur(16))
    cover = ImageEnhance.Brightness(cover).enhance(0.58)
    return cover


def add_bubble(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, idx: int) -> None:
    x, y, w, h = box
    font_size = 34 if w >= 500 else 27
    font_obj = font(font_size, True)
    preferred = [
        (x + 36, y + 34),
        (x + 32, y + h - 118),
        (x + 34, y + 34),
        (x + w - 255, y + h - 120),
        (x + 38, y + 36),
        (x + 36, y + h - 126),
        (x + 48, y + 42),
        (x + 48, y + h - 122),
    ]
    bx, by = preferred[idx]
    lines = wrap_text(text, 7 if w < 430 else 9)
    line_height = int(font_size * 1.22)
    text_width = max(draw.textbbox((0, 0), line, font=font_obj)[2] for line in lines)
    bw = min(w - 56, text_width + 52)
    bh = line_height * len(lines) + 34
    bx = min(max(x + 22, bx), x + w - bw - 22)
    by = min(max(y + 22, by), y + h - bh - 22)
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=28, fill=(255, 251, 229), outline=(18, 17, 16), width=4)
    yy = by + 16
    for line in lines:
        line_width = draw.textbbox((0, 0), line, font=font_obj)[2]
        draw.text((bx + (bw - line_width) / 2, yy), line, font=font_obj, fill=(28, 25, 22))
        yy += line_height


def add_paper_grain(page: Image.Image) -> Image.Image:
    noise = Image.new("L", page.size, 0)
    draw = ImageDraw.Draw(noise)
    width, height = page.size
    for step in range(0, width * height // 240):
        x = (step * 73) % width
        y = (step * 151) % height
        draw.point((x, y), fill=28)
    noise = noise.filter(ImageFilter.GaussianBlur(0.8))
    paper = Image.new("RGB", page.size, (246, 239, 222))
    return Image.blend(page, Image.composite(paper, page, noise), 0.18)


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


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc") if bold else Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


if __name__ == "__main__":
    main()
