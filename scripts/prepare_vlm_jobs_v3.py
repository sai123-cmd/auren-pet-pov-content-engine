#!/usr/bin/env python3
"""Prepare VLM annotation jobs for AUREN POV segments.

This script does not call any model API. It packages the best V2 candidates
into model-ready evidence: start/mid/end frames, a visual strip, a primary comic
frame candidate, and JSONL prompts.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont


FFMPEG_HINT = Path.home() / "AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.1-full_build/bin"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v2-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--per-mode", type=int, default=36)
    parser.add_argument("--profile", choices=["generic", "dog"], default="generic")
    args = parser.parse_args()

    v2_dir = Path(args.v2_dir).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = out_dir / "frames"
    strips_dir = out_dir / "strips"
    primary_dir = out_dir / "primary_frames"
    for folder in [frames_dir, strips_dir, primary_dir]:
        folder.mkdir(exist_ok=True)

    ffmpeg = find_ffmpeg()
    rows = select_rows(v2_dir, args.per_mode)
    jobs = []
    for row in rows:
        segment_id = row["segment_id"]
        segment_frame_dir = frames_dir / segment_id
        segment_frame_dir.mkdir(exist_ok=True)
        frame_paths = extract_triplet(ffmpeg, row, segment_frame_dir)
        primary = choose_primary_frame(frame_paths)
        primary_copy = primary_dir / f"{segment_id}_primary.jpg"
        if not primary_copy.exists():
            shutil.copy2(primary, primary_copy)
        strip_path = strips_dir / f"{segment_id}_strip.jpg"
        make_strip(row, frame_paths, strip_path)
        job = {
            "custom_id": segment_id,
            "segment": {
                "video_id": row["video_id"],
                "video_name": row["video_name"],
                "source_path": row["source_path"],
                "start": float(row["start"]),
                "end": float(row["end"]),
            },
            "v2_prelabels": {
                "scene": split_tags(row.get("scene_v2", "")),
                "visible_subjects": split_tags(row.get("visible_subjects_v2", "")),
                "pet_action": split_tags(row.get("pet_action_v2", "")),
                "pet_event": split_tags(row.get("pet_event_v2", "")),
                "quality": row.get("quality_v2", ""),
                "vlog_score": safe_float(row.get("vlog_score")),
                "diary_score": safe_float(row.get("diary_score")),
                "comic_score": safe_float(row.get("comic_score")),
                "preferred_formats": split_tags(row.get("preferred_formats", "")),
            },
            "evidence": {
                "frames": [str(p) for p in frame_paths],
                "strip": str(strip_path),
                "primary_comic_frame": str(primary_copy),
            },
            "profile": args.profile,
            "prompt": build_prompt(row, args.profile),
        }
        jobs.append(job)

    write_json(out_dir / "vlm_jobs.json", jobs)
    with (out_dir / "vlm_jobs.jsonl").open("w", encoding="utf-8") as f:
        for job in jobs:
            f.write(json.dumps(job, ensure_ascii=False) + "\n")
    write_prompt_template(out_dir, args.profile)
    write_content_logic(out_dir)
    write_review_html(out_dir, jobs)

    print("Done")
    print(f"- jobs: {len(jobs)}")
    print(f"- jsonl: {out_dir / 'vlm_jobs.jsonl'}")
    print(f"- review: {out_dir / 'vlm_job_review.html'}")


def find_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    hinted = FFMPEG_HINT / "ffmpeg.exe"
    if hinted.exists():
        return str(hinted)
    raise SystemExit("ffmpeg not found")


def select_rows(v2_dir: Path, per_mode: int) -> list[dict[str, str]]:
    selected: dict[str, dict[str, str]] = {}
    for filename in ["top_vlog.csv", "top_diary.csv", "top_comic.csv"]:
        for row in read_rows(v2_dir / filename)[:per_mode]:
            selected[row["segment_id"]] = row
    return list(selected.values())


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def extract_triplet(ffmpeg: str, row: dict[str, str], out_dir: Path) -> list[Path]:
    start = float(row["start"])
    end = float(row["end"])
    duration = max(0.8, end - start)
    times = [
        start + min(0.35, duration * 0.20),
        start + duration * 0.50,
        max(start + 0.1, end - min(0.35, duration * 0.20)),
    ]
    names = ["start", "mid", "end"]
    paths = []
    for name, t in zip(names, times):
        out = out_dir / f"{row['segment_id']}_{name}.jpg"
        if not out.exists():
            subprocess.run([
                ffmpeg,
                "-y",
                "-ss",
                f"{t:.3f}",
                "-i",
                row["source_path"],
                "-frames:v",
                "1",
                "-vf",
                "scale=512:-2",
                "-q:v",
                "3",
                str(out),
            ], capture_output=True, check=True)
        paths.append(out)
    return paths


def choose_primary_frame(frame_paths: list[Path]) -> Path:
    scored = []
    for path in frame_paths:
        img = Image.open(path).convert("RGB").resize((180, 120))
        arr = np.asarray(img, dtype=np.float32) / 255.0
        gray = np.mean(arr, axis=2)
        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))
        sharpness = gradient_energy(gray)
        exposure_penalty = abs(brightness - 0.48)
        score = sharpness * 0.45 + contrast * 0.35 + (1.0 - exposure_penalty) * 0.20
        scored.append((score, path))
    return max(scored, key=lambda item: item[0])[1]


def make_strip(row: dict[str, str], frame_paths: list[Path], out: Path) -> None:
    if out.exists():
        return
    thumbs = []
    for path in frame_paths:
        img = Image.open(path).convert("RGB")
        img.thumbnail((260, 150))
        tile = Image.new("RGB", (260, 150), "#ded6cf")
        tile.paste(img, ((260 - img.width) // 2, (150 - img.height) // 2))
        thumbs.append(tile)
    pad = 16
    header_h = 82
    canvas = Image.new("RGB", (3 * 260 + 4 * pad, header_h + 150 + 62), "#f7f3ee")
    draw = ImageDraw.Draw(canvas)
    font_title = load_font(20)
    font = load_font(14)
    draw.text((pad, 14), f"{row['segment_id']}  {row['start']}-{row['end']}  vlog={row.get('vlog_score')} diary={row.get('diary_score')} comic={row.get('comic_score')}", fill="#2d241f", font=font_title)
    draw.text((pad, 42), f"V2: {row.get('pet_action_v2')} / {row.get('pet_event_v2')}", fill="#79685d", font=font)
    for i, tile in enumerate(thumbs):
        x = pad + i * (260 + pad)
        y = header_h
        canvas.paste(tile, (x, y))
        draw.rectangle((x, y, x + 260, y + 150), outline="#c8b7a8", width=2)
        draw.text((x + 8, y + 158), ["start", "mid", "end"][i], fill="#5f4f45", font=font)
    canvas.save(out, quality=92)


def build_prompt(row: dict[str, str], profile: str = "generic") -> str:
    schema = profile_schema(profile)
    profile_guidance = {
        "generic": "Use general pet POV labels. Do not assume species if it is not visible or known from source context.",
        "dog": "Use dog-specific POV judgment: social connection, running, sniffing, swimming, grass exploration, and owner interaction are often important.",
    }[profile]
    return f"""You are annotating pet first-person wearable camera footage for AUREN.

Use the three frames from one short segment. Correct the heuristic labels. Be literal and evidence-bound.
Profile: {profile}
Profile guidance: {profile_guidance}

Existing V2 labels:
- scene: {row.get('scene_v2')}
- visible_subjects: {row.get('visible_subjects_v2')}
- pet_action: {row.get('pet_action_v2')}
- pet_event: {row.get('pet_event_v2')}
- quality: {row.get('quality_v2')}

Return STRICT JSON with these keys:
{{
  "scene": ["..."],
  "visible_subjects": {json.dumps(schema["visible_subjects"], ensure_ascii=False)},
  "pet_action": {json.dumps(schema["pet_action"], ensure_ascii=False)},
  "pet_event": {json.dumps(schema["pet_event"], ensure_ascii=False)},
  "quality": "good|usable|bad",
  "vlog_fit": 0-5,
  "diary_fit": 0-5,
  "comic_fit": 0-5,
  "why_memorable": "one concrete sentence grounded in visible evidence",
  "diary_sentence": "one pet-voice sentence, only if evidence supports it",
  "comic_panel_caption": "short speech/thought bubble, only if visually meaningful",
  "corrections_to_v2": ["..."]
}}"""


def profile_schema(profile: str) -> dict[str, list[str]]:
    base_subjects = ["owner", "human", "dog", "animal", "water", "grass", "brush", "toy", "food", "ground", "building", "vehicle", "unknown"]
    if profile == "dog":
        return {
            "visible_subjects": base_subjects + ["leash", "river", "stick", "ball", "trail", "bench"],
            "pet_action": ["walk", "run", "swim", "sniff", "search", "look_around", "approach_human", "approach_animal", "play", "chase", "drink", "pause_observe", "unclear"],
            "pet_event": ["water_adventure", "grass_exploration", "search_or_inspect", "human_connection", "animal_social_moment", "run_or_chase", "quiet_observation", "new_scene_discovery", "sound_triggered_attention", "low_signal"],
        }
    return {
        "visible_subjects": base_subjects,
        "pet_action": ["walk", "run", "swim", "sniff", "search", "look_around", "approach_human", "approach_animal", "play", "pause_observe", "unclear"],
        "pet_event": ["water_adventure", "grass_exploration", "search_or_inspect", "human_connection", "animal_social_moment", "quiet_observation", "new_scene_discovery", "sound_triggered_attention", "low_signal"],
    }


def write_prompt_template(out_dir: Path, profile: str) -> None:
    schema = profile_schema(profile)
    (out_dir / "VLM_PROMPT_TEMPLATE.md").write_text(f"""# AUREN VLM Prompt Template

Goal: correct heuristic V2 labels for short pet POV segments.
Profile: `{profile}`

The model should:

- be literal;
- avoid inventing owner/dog/animal/toy if not visible;
- separate observable action from narrative event;
- score vlog/diary/comic independently;
- explain corrections to V2 labels.

Profile label hints:

- visible_subjects: `{", ".join(schema["visible_subjects"])}`
- pet_action: `{", ".join(schema["pet_action"])}`
- pet_event: `{", ".join(schema["pet_event"])}`

Use `vlm_jobs.jsonl` as the task queue.
""", encoding="utf-8")


def write_content_logic(out_dir: Path) -> None:
    (out_dir / "CONTENT_SELECTION_LOGIC.md").write_text("""# AUREN Content Selection Logic

## Vlog

Vlog prefers rhythm: motion, scene transition, sound, and sequence continuity.
A vlog candidate can be visually messy if it carries action or movement.

## Diary

Diary prefers semantic specificity. A segment is useful only if it supports a
concrete pet-memory sentence, such as "I followed my person under the table" or
"I put my nose into the grass to search for a smell."

## Comic

Comic prefers readable single frames, iconic posture, visible subject, and a
simple punchline. A clip can be great for vlog but poor for comic if the frame is
blurred, blocked, or too abstract.

## Comic Frame Policy

First version: choose one primary frame per event.

Better version: choose 1-3 frames per event:

1. setup frame;
2. action/reaction frame;
3. payoff frame.

The current V3 pack extracts start/mid/end frames and picks a primary frame by
sharpness, contrast, and exposure. A VLM/human can override it.
""", encoding="utf-8")


def write_review_html(out_dir: Path, jobs: list[dict[str, Any]]) -> None:
    cards = []
    for job in jobs:
        strip = Path(job["evidence"]["strip"]).relative_to(out_dir).as_posix()
        primary = Path(job["evidence"]["primary_comic_frame"]).relative_to(out_dir).as_posix()
        seg = job["segment"]
        v2 = job["v2_prelabels"]
        cards.append(f"""
        <article class="card">
          <img src="{html.escape(strip)}" alt="{html.escape(job['custom_id'])}" />
          <p><b>{html.escape(job['custom_id'])}</b> · {seg['start']}-{seg['end']} · {html.escape(seg['video_id'])}</p>
          <p>V2 action: <code>{html.escape('|'.join(v2['pet_action']))}</code></p>
          <p>V2 event: <code>{html.escape('|'.join(v2['pet_event']))}</code></p>
          <p>formats: <code>{html.escape('|'.join(v2['preferred_formats']))}</code></p>
          <p>primary comic frame: <a href="{html.escape(primary)}">open</a></p>
        </article>
        """)
    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>AUREN VLM Jobs V3</title>
  <style>
    body {{ margin:0; background:#f5f1ec; color:#2d241f; font-family:"Microsoft YaHei","Noto Sans SC",Arial,sans-serif; }}
    header {{ padding:30px 38px 18px; border-bottom:1px solid #dacbbe; }}
    main {{ padding:24px 28px 60px; display:grid; grid-template-columns:repeat(auto-fill,minmax(420px,1fr)); gap:18px; }}
    .card {{ background:#fffaf4; border:1px solid #d8c9ba; border-radius:8px; padding:14px; }}
    img {{ width:100%; border-radius:6px; border:1px solid #cab9a9; }}
    p {{ color:#6c5a4f; font-size:13px; }}
    code {{ font-size:12px; }}
  </style>
</head>
<body>
  <header>
    <h1>AUREN VLM Jobs V3</h1>
    <p>Start/mid/end visual evidence for correcting V2 labels.</p>
  </header>
  <main>{''.join(cards)}</main>
</body>
</html>"""
    (out_dir / "vlm_job_review.html").write_text(doc, encoding="utf-8")


def split_tags(value: str) -> list[str]:
    return [item for item in str(value).split("|") if item]


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def gradient_energy(gray: np.ndarray) -> float:
    gx = np.diff(gray, axis=1)
    gy = np.diff(gray, axis=0)
    return float((np.mean(np.abs(gx)) + np.mean(np.abs(gy))) / 2)


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in ["C:/Windows/Fonts/NotoSansSC-VF.ttf", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]:
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
