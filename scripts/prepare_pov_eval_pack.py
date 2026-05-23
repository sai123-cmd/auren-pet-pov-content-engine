#!/usr/bin/env python3
"""Prepare a small AUREN pet POV evaluation pack.

The project folder currently lives under System32 and is read-only for normal
users, so this script writes all review artifacts under the user's output
folder. It does not modify the source videos.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


KNOWN_FFMPEG_DIRS = [
    Path.home() / "AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.1-full_build/bin",
]

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}


@dataclass
class VideoItem:
    id: str
    name: str
    path: str
    size_mb: float
    duration_s: float
    duration_text: str
    width: int
    height: int
    fps: float
    video_codec: str
    has_audio: bool
    audio_codec: str | None
    contact_sheet: str
    frame_dir: str


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--samples", type=int, default=12)
    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_root = out_dir / "keyframes"
    sheets_root = out_dir / "contact_sheets"
    frames_root.mkdir(exist_ok=True)
    sheets_root.mkdir(exist_ok=True)

    ffmpeg, ffprobe = find_ffmpeg()
    videos = sorted([p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS], key=lambda p: p.name.lower())
    if not videos:
        raise SystemExit(f"No video files found in {source_dir}")

    items: list[VideoItem] = []
    for idx, video in enumerate(videos, 1):
        video_id = f"pov_{idx:03d}"
        meta = probe_video(ffprobe, video)
        frame_dir = frames_root / video_id
        frame_dir.mkdir(exist_ok=True)
        frames = extract_keyframes(ffmpeg, video, frame_dir, meta["duration_s"], args.samples)
        sheet_path = sheets_root / f"{video_id}_contact_sheet.jpg"
        make_contact_sheet(video_id, video.name, meta, frames, sheet_path)
        items.append(VideoItem(
            id=video_id,
            name=video.name,
            path=str(video),
            size_mb=round(video.stat().st_size / 1024 / 1024, 2),
            duration_s=round(meta["duration_s"], 2),
            duration_text=fmt_time(meta["duration_s"]),
            width=meta["width"],
            height=meta["height"],
            fps=round(meta["fps"], 3),
            video_codec=meta["video_codec"],
            has_audio=meta["has_audio"],
            audio_codec=meta["audio_codec"],
            contact_sheet=str(sheet_path),
            frame_dir=str(frame_dir),
        ))

    write_manifest(out_dir, items)
    write_label_schema(out_dir)
    write_capability_map(out_dir)
    write_html_review(out_dir, items)

    print("Done")
    print(f"- videos: {len(items)}")
    print(f"- manifest: {out_dir / 'manifest.csv'}")
    print(f"- review html: {out_dir / 'review_index.html'}")
    print(f"- capability map: {out_dir / 'AUREN_POV_CAPABILITY_MAP.md'}")


def find_ffmpeg() -> tuple[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        return ffmpeg, ffprobe
    for folder in KNOWN_FFMPEG_DIRS:
        f1 = folder / "ffmpeg.exe"
        f2 = folder / "ffprobe.exe"
        if f1.exists() and f2.exists():
            return str(f1), str(f2)
    raise SystemExit("ffmpeg/ffprobe not found")


def probe_video(ffprobe: str, video: Path) -> dict[str, Any]:
    result = subprocess.run([
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video),
    ], capture_output=True, check=True)
    payload = json.loads(result.stdout.decode("utf-8", errors="replace"))
    streams = payload.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video_stream:
        raise RuntimeError(f"No video stream: {video}")
    duration = float(payload.get("format", {}).get("duration") or video_stream.get("duration") or 0)
    return {
        "duration_s": max(duration, 0.1),
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "fps": parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")),
        "video_codec": video_stream.get("codec_name") or "",
        "has_audio": audio_stream is not None,
        "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
    }


def extract_keyframes(ffmpeg: str, video: Path, frame_dir: Path, duration_s: float, samples: int) -> list[tuple[float, Path]]:
    if samples <= 1:
        times = [min(duration_s / 2, max(duration_s - 0.2, 0.1))]
    else:
        times = [duration_s * (idx + 1) / (samples + 1) for idx in range(samples)]
    frames: list[tuple[float, Path]] = []
    for idx, t in enumerate(times, 1):
        out = frame_dir / f"frame_{idx:02d}_{int(t):04d}s.jpg"
        if not out.exists():
            subprocess.run([
                ffmpeg,
                "-y",
                "-ss",
                f"{t:.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-vf",
                "scale=360:-2",
                "-q:v",
                "3",
                str(out),
            ], capture_output=True, check=True)
        frames.append((t, out))
    return frames


def make_contact_sheet(video_id: str, name: str, meta: dict[str, Any], frames: list[tuple[float, Path]], out: Path) -> None:
    thumb_w, thumb_h = 260, 150
    cols = 3
    rows = (len(frames) + cols - 1) // cols
    header_h = 112
    pad = 18
    caption_h = 32
    sheet = Image.new("RGB", (cols * thumb_w + (cols + 1) * pad, header_h + rows * (thumb_h + caption_h + pad) + pad), "#f7f3ee")
    draw = ImageDraw.Draw(sheet)
    font_title = load_font(24)
    font = load_font(16)
    draw.text((pad, 18), f"{video_id}  {name}", fill="#2d241f", font=font_title)
    draw.text((pad, 54), f"{fmt_time(meta['duration_s'])} | {meta['width']}x{meta['height']} | {meta['fps']:.2f} fps | audio={meta['has_audio']}", fill="#6f6158", font=font)
    draw.text((pad, 80), "Review: scene diversity, camera mount quality, pet POV clarity, usable memory moments.", fill="#8a7668", font=font)
    for idx, (time_s, frame) in enumerate(frames):
        image = Image.open(frame).convert("RGB")
        image.thumbnail((thumb_w, thumb_h))
        tile = Image.new("RGB", (thumb_w, thumb_h), "#ded6cf")
        tile.paste(image, ((thumb_w - image.width) // 2, (thumb_h - image.height) // 2))
        x = pad + (idx % cols) * (thumb_w + pad)
        y = header_h + (idx // cols) * (thumb_h + caption_h + pad)
        sheet.paste(tile, (x, y))
        draw.rectangle((x, y, x + thumb_w, y + thumb_h), outline="#c7b8aa", width=2)
        draw.text((x + 8, y + thumb_h + 7), fmt_time(time_s), fill="#4c3b31", font=font)
    sheet.save(out, quality=92)


def write_manifest(out_dir: Path, items: list[VideoItem]) -> None:
    write_json(out_dir / "manifest.json", [asdict(item) for item in items])
    with (out_dir / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(items[0]).keys()))
        writer.writeheader()
        for item in items:
            writer.writerow(asdict(item))


def write_label_schema(out_dir: Path) -> None:
    schema = {
        "segment_unit": "2-5 seconds",
        "fields": {
            "scene": ["park", "river_lake", "beach", "street", "home", "trail", "unknown"],
            "visible_subjects": ["owner", "stranger", "dog", "animal", "water", "toy", "food", "vehicle", "leash", "ground"],
            "pet_action": ["walk", "run", "sniff", "stop_observe", "turn_head", "approach_human", "approach_animal", "play", "drink", "unclear"],
            "sound_event": ["human_voice", "dog_bark", "water", "traffic", "leash_noise", "wind", "impact", "quiet", "unknown"],
            "motion_state": ["stable", "walking", "running", "shaky", "sudden_stop", "camera_blocked"],
            "quality": ["good", "usable", "bad_blurry", "bad_dark", "bad_blocked", "bad_duplicate"],
            "pet_event": ["run_chase", "sniff_explore", "sudden_attention", "human_interaction", "animal_interaction", "quiet_observe", "audio_event", "scene_change"],
            "highlight_score": "0-5",
            "why_memorable": "short free text",
            "usable_for": ["diary", "comic", "vlog", "training", "discard"],
        },
        "positive_highlight_rule": "A segment is a highlight if a human can write a specific pet-memory sentence from visible/audio evidence, not just because pixels move.",
    }
    write_json(out_dir / "label_schema.json", schema)


def write_capability_map(out_dir: Path) -> None:
    text = """# AUREN POV Capability Map

Generated for `AUREN_POV_EVAL_001`.

## Current Decision

The existing local pipeline proves the file-to-artifact loop, but it does not yet understand scene, action, sound, or story. The next build should be modular: pet POV understanding first, content generation second.

## Modules

| Module | Job | Candidate Tools | AUREN Judgment |
| --- | --- | --- | --- |
| Dataset and benchmark | Learn egocentric task design and pet POV labels | DogCentric Activity Dataset, Ego4D, EPIC-KITCHENS | Use as references, not final commercial training corpus. |
| Shot/segment candidates | Split long videos into reviewable 2-5s units | ffmpeg, PySceneDetect, TransNetV2 | Start here. It is robust and cheap. |
| Visual scene/action understanding | Detect river/park/street/owner/animal, sniff/run/stop/turn | Qwen2.5-VL, InternVL, LLaVA-NeXT-Video, InternVideo | Use API or hosted model first; local model later if quality and cost justify it. |
| Audio understanding | Detect human voice, bark, water, traffic, sudden sounds | YAMNet, PANNs, CLAP, Whisper | Use YAMNet/PANNs for sound tags, Whisper for speech. |
| Highlight scoring | Rank memorable moments, not just fast motion | AUREN custom scoring with model evidence + human labels | Must be proprietary AUREN logic. |
| Diary generation | Turn evidence into pet memory writing | LLM prompt with strict JSON evidence | Only meaningful after upstream evidence improves. |
| Comic generation | Generate real comic panels or stylized storyboards | Product APIs, ComfyUI, newer image models | Keep swappable; old StoryDiffusion-like outputs may not meet brand bar. |
| Vlog generation | Cut, pace, subtitle, mix BGM, export | ai-video-editing-skill workflow, ffmpeg, MoviePy | Borrow workflow structure, not pet highlight logic. |
| Review loop | Let human approve labels and content | Label Studio, CVAT, simple HTML dashboard | Needed immediately for taste and truth checking. |

## What The User Needs To Judge

- Whether the selected moments feel like real pet memories.
- Whether the visual style is premium enough for AUREN.
- Whether a generated diary sounds charming rather than generic.
- Whether the vlog rhythm feels shareable.

Everything else can be prepared automatically by Codex first.
"""
    (out_dir / "AUREN_POV_CAPABILITY_MAP.md").write_text(text, encoding="utf-8")


def write_html_review(out_dir: Path, items: list[VideoItem]) -> None:
    rows = []
    for item in items:
        rel_sheet = Path(item.contact_sheet).relative_to(out_dir).as_posix()
        rows.append(f"""
        <section class="video">
          <h2>{html.escape(item.id)} · {html.escape(item.name)}</h2>
          <p>{item.duration_text} · {item.width}x{item.height} · {item.fps:.2f} fps · audio={item.has_audio} · {item.size_mb} MB</p>
          <img src="{html.escape(rel_sheet)}" alt="{html.escape(item.name)} contact sheet" />
        </section>
        """)
    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>AUREN POV Eval 001</title>
  <style>
    body {{ margin: 0; font-family: "Microsoft YaHei", "Noto Sans SC", Arial, sans-serif; background: #f5f1ec; color: #2d241f; }}
    header {{ padding: 32px 40px 18px; border-bottom: 1px solid #d8c9ba; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 26px 24px 60px; }}
    .video {{ margin-bottom: 34px; padding: 22px; background: #fffaf4; border: 1px solid #dfd1c4; border-radius: 8px; }}
    .video h2 {{ margin: 0 0 8px; font-size: 19px; }}
    .video p {{ margin: 0 0 16px; color: #7b6a5f; }}
    img {{ display: block; max-width: 100%; height: auto; border-radius: 6px; border: 1px solid #cab9a9; }}
  </style>
</head>
<body>
  <header>
    <h1>AUREN POV Eval 001</h1>
    <p>Keyframe review pack for pet first-person footage. Use this to judge visual quality and scene diversity before model integration.</p>
  </header>
  <main>
    {''.join(rows)}
  </main>
</body>
</html>
"""
    (out_dir / "review_index.html").write_text(html_doc, encoding="utf-8")


def parse_fps(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" in value:
        num, den = value.split("/", 1)
        den_f = float(den)
        return float(num) / den_f if den_f else 0.0
    return float(value)


def fmt_time(seconds: float) -> str:
    seconds_i = max(0, int(round(seconds)))
    return f"{seconds_i // 60:02d}:{seconds_i % 60:02d}"


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in [
        "C:/Windows/Fonts/NotoSansSC-VF.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/Deng.ttf",
    ]:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
