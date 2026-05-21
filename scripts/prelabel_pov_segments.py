#!/usr/bin/env python3
"""Pre-label pet POV candidate segments for AUREN.

This is a deliberately explainable V1 pre-labeler. It does not pretend to be a
full scene/action model. It creates segment-level evidence so humans and later
VLM/audio models can improve the labels.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import shutil
import subprocess
import sys
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont


VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
FFMPEG_HINT = Path.home() / "AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.1-full_build/bin"


@dataclass
class SegmentLabel:
    segment_id: str
    video_id: str
    video_name: str
    source_path: str
    start: float
    end: float
    mid: float
    frame_path: str
    scene: list[str]
    visible_subjects: list[str]
    pet_action: list[str]
    sound_event: list[str]
    motion_state: list[str]
    quality: str
    pet_event: list[str]
    highlight_score: float
    why_memorable: str
    usable_for: list[str]
    brightness: float
    sharpness: float
    contrast: float
    motion: float
    novelty: float
    audio_energy: float
    green_ratio: float
    blue_ratio: float
    top_dark_ratio: float
    lower_blue_ratio: float


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--interval", type=float, default=4.0)
    parser.add_argument("--top-per-video", type=int, default=12)
    parser.add_argument("--global-top", type=int, default=80)
    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_root = out_dir / "segment_frames"
    audio_root = out_dir / "audio"
    review_root = out_dir / "review"
    for folder in [frames_root, audio_root, review_root]:
        folder.mkdir(exist_ok=True)

    ffmpeg, ffprobe = find_ffmpeg()
    videos = sorted([p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS], key=lambda p: p.name.lower())
    all_segments: list[SegmentLabel] = []
    by_video: dict[str, list[SegmentLabel]] = {}

    for video_index, video in enumerate(videos, 1):
        video_id = f"pov_{video_index:03d}"
        print(f"[{video_id}] {video.name}")
        meta = probe_video(ffprobe, video)
        frame_dir = frames_root / video_id
        frame_dir.mkdir(exist_ok=True)
        frames = extract_segment_frames(ffmpeg, video, frame_dir, args.interval)
        audio_curve = extract_audio_curve(ffmpeg, video, audio_root / f"{video_id}.wav", meta["duration_s"], args.interval) if meta["has_audio"] else []
        segments = analyze_video(video_id, video, meta, frames, audio_curve, args.interval)
        all_segments.extend(segments)
        by_video[video_id] = segments

    top_global = sorted(all_segments, key=lambda s: s.highlight_score, reverse=True)[:args.global_top]
    write_json(out_dir / "segments.json", [asdict(s) for s in all_segments])
    write_csv(out_dir / "segments.csv", all_segments)
    write_json(out_dir / "top_highlights.json", [asdict(s) for s in top_global])
    write_csv(out_dir / "top_highlights.csv", top_global)
    write_labeling_queue(out_dir, top_global)
    write_review_html(out_dir, by_video, args.top_per_video, top_global)
    make_top_contact_sheet(review_root / "top_highlights_contact_sheet.jpg", top_global[:24])

    print("Done")
    print(f"- segments: {len(all_segments)}")
    print(f"- segments.csv: {out_dir / 'segments.csv'}")
    print(f"- top_highlights.csv: {out_dir / 'top_highlights.csv'}")
    print(f"- review: {out_dir / 'review_segments.html'}")


def find_ffmpeg() -> tuple[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        return ffmpeg, ffprobe
    f1 = FFMPEG_HINT / "ffmpeg.exe"
    f2 = FFMPEG_HINT / "ffprobe.exe"
    if f1.exists() and f2.exists():
        return str(f1), str(f2)
    raise SystemExit("ffmpeg/ffprobe not found")


def probe_video(ffprobe: str, video: Path) -> dict[str, Any]:
    result = subprocess.run([
        ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(video)
    ], capture_output=True, check=True)
    payload = json.loads(result.stdout.decode("utf-8", errors="replace"))
    streams = payload.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(payload.get("format", {}).get("duration") or (video_stream or {}).get("duration") or 0)
    return {
        "duration_s": max(duration, 0.1),
        "width": int((video_stream or {}).get("width") or 0),
        "height": int((video_stream or {}).get("height") or 0),
        "has_audio": audio_stream is not None,
    }


def extract_segment_frames(ffmpeg: str, video: Path, frame_dir: Path, interval: float) -> list[Path]:
    existing = sorted(frame_dir.glob("seg_*.jpg"))
    if existing:
        return existing
    subprocess.run([
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-vf",
        f"fps=1/{interval},scale=360:-2",
        "-q:v",
        "3",
        str(frame_dir / "seg_%05d.jpg"),
    ], capture_output=True, check=True)
    return sorted(frame_dir.glob("seg_*.jpg"))


def extract_audio_curve(ffmpeg: str, video: Path, wav_path: Path, duration_s: float, interval: float) -> list[float]:
    if not wav_path.exists():
        subprocess.run([
            ffmpeg, "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le", str(wav_path)
        ], capture_output=True, check=True)
    with wave.open(str(wav_path), "rb") as wav:
        sr = wav.getframerate()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    values = []
    seg_samples = max(1, int(sr * interval))
    for start in range(0, len(samples), seg_samples):
        chunk = samples[start:start + seg_samples]
        rms = float(np.sqrt(np.mean(chunk * chunk))) if len(chunk) else 0.0
        values.append(rms)
    expected = math.ceil(duration_s / interval)
    while len(values) < expected:
        values.append(0.0)
    return normalize(values)


def analyze_video(video_id: str, video: Path, meta: dict[str, Any], frames: list[Path], audio_curve: list[float], interval: float) -> list[SegmentLabel]:
    raw = []
    prev_gray = None
    prev_hist = None
    for idx, frame in enumerate(frames):
        try:
            image = Image.open(frame).convert("RGB").resize((160, 90))
        except Exception:
            continue
        rgb = np.asarray(image, dtype=np.float32) / 255.0
        gray = np.mean(rgb, axis=2)
        hist, _ = np.histogram(gray, bins=24, range=(0, 1), density=True)
        motion = float(np.mean(np.abs(gray - prev_gray))) if prev_gray is not None else 0.0
        novelty = float(np.mean(np.abs(hist - prev_hist))) if prev_hist is not None else 0.0
        sharpness = gradient_energy(gray)
        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))
        green = ((rgb[:, :, 1] > rgb[:, :, 0] * 1.08) & (rgb[:, :, 1] > rgb[:, :, 2] * 1.04) & (rgb[:, :, 1] > 0.22))
        blue = ((rgb[:, :, 2] > rgb[:, :, 0] * 1.10) & (rgb[:, :, 2] > rgb[:, :, 1] * 1.03) & (rgb[:, :, 2] > 0.25))
        dark = gray < 0.16
        lower = slice(rgb.shape[0] // 2, rgb.shape[0])
        top = slice(0, rgb.shape[0] // 4)
        raw.append({
            "idx": idx,
            "frame": frame,
            "motion": motion,
            "novelty": novelty,
            "sharpness": sharpness,
            "brightness": brightness,
            "contrast": contrast,
            "green_ratio": float(np.mean(green)),
            "blue_ratio": float(np.mean(blue)),
            "lower_blue_ratio": float(np.mean(blue[lower, :])),
            "top_dark_ratio": float(np.mean(dark[top, :])),
            "audio_energy": audio_curve[min(idx, len(audio_curve) - 1)] if audio_curve else 0.0,
        })
        prev_gray = gray
        prev_hist = hist

    for key in ["motion", "novelty", "sharpness", "contrast"]:
        values = normalize([r[key] for r in raw])
        for item, value in zip(raw, values):
            item[f"{key}_norm"] = value

    segments = []
    for item in raw:
        start = item["idx"] * interval
        end = min(start + interval, meta["duration_s"])
        if start >= meta["duration_s"]:
            continue
        labels = classify(item)
        segment_id = f"{video_id}_s{item['idx'] + 1:04d}"
        segments.append(SegmentLabel(
            segment_id=segment_id,
            video_id=video_id,
            video_name=video.name,
            source_path=str(video),
            start=round(start, 2),
            end=round(end, 2),
            mid=round((start + end) / 2, 2),
            frame_path=str(item["frame"]),
            scene=labels["scene"],
            visible_subjects=labels["visible_subjects"],
            pet_action=labels["pet_action"],
            sound_event=labels["sound_event"],
            motion_state=labels["motion_state"],
            quality=labels["quality"],
            pet_event=labels["pet_event"],
            highlight_score=labels["highlight_score"],
            why_memorable=labels["why_memorable"],
            usable_for=labels["usable_for"],
            brightness=round(item["brightness"], 4),
            sharpness=round(item["sharpness_norm"], 4),
            contrast=round(item["contrast_norm"], 4),
            motion=round(item["motion_norm"], 4),
            novelty=round(item["novelty_norm"], 4),
            audio_energy=round(item["audio_energy"], 4),
            green_ratio=round(item["green_ratio"], 4),
            blue_ratio=round(item["blue_ratio"], 4),
            top_dark_ratio=round(item["top_dark_ratio"], 4),
            lower_blue_ratio=round(item["lower_blue_ratio"], 4),
        ))
    return segments


def classify(item: dict[str, Any]) -> dict[str, Any]:
    scene = []
    subjects = []
    pet_action = []
    sound_event = []
    motion_state = []
    pet_event = []
    usable_for = []

    if item["lower_blue_ratio"] > 0.16 or item["blue_ratio"] > 0.22:
        scene.append("river_lake_or_sky")
        subjects.append("water_or_sky")
    if item["green_ratio"] > 0.20:
        scene.append("park_grass_trail")
        subjects.append("grass_or_trees")
    if item["green_ratio"] < 0.08 and item["blue_ratio"] < 0.10 and item["brightness"] > 0.42:
        scene.append("open_ground_or_pavement")
        subjects.append("ground")
    if item["brightness"] < 0.22:
        scene.append("indoor_or_shadow")
    if not scene:
        scene.append("mixed_unknown")

    if item["top_dark_ratio"] > 0.15:
        subjects.append("dog_muzzle_or_mount_occlusion")
    if item["top_dark_ratio"] > 0.38:
        subjects.append("camera_partly_blocked")

    if item["motion_norm"] > 0.72:
        motion_state.append("fast_motion")
        pet_action.append("run_or_quick_turn")
        pet_event.append("run_chase")
    elif item["motion_norm"] > 0.42:
        motion_state.append("walking_or_turning")
        pet_action.append("walk_or_explore")
    else:
        motion_state.append("stable")

    if item["novelty_norm"] > 0.64:
        pet_event.append("scene_change")
        if "sudden_turn" not in pet_action:
            pet_action.append("sudden_turn_or_new_view")

    if item["top_dark_ratio"] > 0.12 and item["motion_norm"] < 0.60:
        pet_action.append("sniff_or_close_inspection")
        pet_event.append("sniff_explore")

    if item["motion_norm"] < 0.34 and item["sharpness_norm"] > 0.45:
        pet_action.append("stop_observe")
        pet_event.append("quiet_observe")

    if item["audio_energy"] > 0.70:
        sound_event.append("loud_or_sudden_sound")
        pet_event.append("audio_event")
    elif item["audio_energy"] > 0.38:
        sound_event.append("ambient_activity")
    else:
        sound_event.append("quiet_or_low_audio")

    quality = "good"
    if item["brightness"] < 0.14:
        quality = "bad_dark"
    elif item["brightness"] > 0.82:
        quality = "bad_overexposed"
    elif item["sharpness_norm"] < 0.18:
        quality = "bad_blurry"
    elif item["top_dark_ratio"] > 0.45:
        quality = "usable_but_blocked"

    quality_score = {"good": 1.0, "usable_but_blocked": 0.62, "bad_blurry": 0.30, "bad_dark": 0.25, "bad_overexposed": 0.25}.get(quality, 0.5)
    score = (
        item["motion_norm"] * 0.26
        + item["novelty_norm"] * 0.24
        + item["sharpness_norm"] * 0.14
        + item["contrast_norm"] * 0.10
        + item["audio_energy"] * 0.12
        + min(item["green_ratio"] + item["blue_ratio"], 0.35) * 0.20
        + quality_score * 0.14
    )
    if "sniff_explore" in pet_event or "quiet_observe" in pet_event:
        score += 0.05
    if quality.startswith("bad"):
        score -= 0.22
    if "camera_partly_blocked" in subjects:
        score -= 0.08
    score = max(0.0, min(1.0, score))

    if score >= 0.62 and quality in {"good", "usable_but_blocked"}:
        usable_for.extend(["diary", "vlog"])
    if score >= 0.55 and quality == "good":
        usable_for.append("comic")
    if score >= 0.42:
        usable_for.append("training")
    if not usable_for:
        usable_for.append("discard_or_low_priority")

    pet_event = dedupe(pet_event) or ["low_signal"]
    pet_action = dedupe(pet_action) or ["unclear"]
    subjects = dedupe(subjects) or ["unknown"]
    why = build_why(scene, pet_action, sound_event, motion_state, pet_event, quality)

    return {
        "scene": dedupe(scene),
        "visible_subjects": subjects,
        "pet_action": pet_action,
        "sound_event": dedupe(sound_event),
        "motion_state": dedupe(motion_state),
        "quality": quality,
        "pet_event": pet_event,
        "highlight_score": round(score * 100, 1),
        "why_memorable": why,
        "usable_for": dedupe(usable_for),
    }


def build_why(scene: list[str], actions: list[str], sounds: list[str], motion: list[str], events: list[str], quality: str) -> str:
    parts = []
    if "run_chase" in events:
        parts.append("fast POV movement")
    if "sniff_explore" in events:
        parts.append("close inspection/sniff-like view")
    if "quiet_observe" in events:
        parts.append("stable observation moment")
    if "scene_change" in events:
        parts.append("clear scene/view change")
    if "audio_event" in events:
        parts.append("audio energy spike")
    if any(s in scene for s in ["river_lake_or_sky", "park_grass_trail"]):
        parts.append("visually identifiable outdoor scene")
    if quality != "good":
        parts.append(f"quality={quality}")
    return "; ".join(parts) if parts else "low semantic signal; needs model/human review"


def make_top_contact_sheet(out: Path, segments: list[SegmentLabel]) -> None:
    if not segments:
        return
    thumb_w, thumb_h = 220, 124
    cols = 4
    rows = math.ceil(len(segments) / cols)
    pad = 16
    cap_h = 58
    header_h = 70
    canvas = Image.new("RGB", (cols * thumb_w + (cols + 1) * pad, header_h + rows * (thumb_h + cap_h + pad) + pad), "#f7f3ee")
    draw = ImageDraw.Draw(canvas)
    font_title = load_font(26)
    font = load_font(14)
    draw.text((pad, 22), "AUREN POV Top Candidate Highlights", fill="#2d241f", font=font_title)
    for idx, seg in enumerate(segments):
        img = Image.open(seg.frame_path).convert("RGB")
        img.thumbnail((thumb_w, thumb_h))
        tile = Image.new("RGB", (thumb_w, thumb_h), "#ded6cf")
        tile.paste(img, ((thumb_w - img.width) // 2, (thumb_h - img.height) // 2))
        x = pad + (idx % cols) * (thumb_w + pad)
        y = header_h + (idx // cols) * (thumb_h + cap_h + pad)
        canvas.paste(tile, (x, y))
        draw.rectangle((x, y, x + thumb_w, y + thumb_h), outline="#c7b8aa", width=2)
        text = f"{seg.segment_id} {fmt_time(seg.start)} score={seg.highlight_score}"
        draw.text((x, y + thumb_h + 6), text[:34], fill="#3b302b", font=font)
        draw.text((x, y + thumb_h + 26), ",".join(seg.pet_event)[:34], fill="#7a675b", font=font)
    canvas.save(out, quality=92)


def write_review_html(out_dir: Path, by_video: dict[str, list[SegmentLabel]], top_per_video: int, top_global: list[SegmentLabel]) -> None:
    sections = []
    for video_id, segments in by_video.items():
        top = sorted(segments, key=lambda s: s.highlight_score, reverse=True)[:top_per_video]
        cards = "\n".join(segment_card(out_dir, s) for s in top)
        sections.append(f"<section><h2>{html.escape(video_id)} · {html.escape(segments[0].video_name)}</h2><div class='grid'>{cards}</div></section>")
    global_cards = "\n".join(segment_card(out_dir, s) for s in top_global[:24])
    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>AUREN POV Segment Prelabels</title>
  <style>
    body {{ margin:0; background:#f5f1ec; color:#2d241f; font-family:"Microsoft YaHei","Noto Sans SC",Arial,sans-serif; }}
    header {{ padding:30px 38px 18px; border-bottom:1px solid #dacbbe; }}
    main {{ padding:24px 28px 60px; }}
    h1 {{ margin:0 0 8px; font-size:28px; }}
    h2 {{ margin:34px 0 16px; font-size:20px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:16px; }}
    .card {{ background:#fffaf4; border:1px solid #d8c9ba; border-radius:8px; padding:12px; }}
    img {{ width:100%; border-radius:6px; border:1px solid #cab9a9; }}
    .meta {{ font-size:13px; color:#746357; line-height:1.45; }}
    .score {{ font-weight:700; color:#2d241f; }}
    code {{ font-size:12px; }}
  </style>
</head>
<body>
  <header>
    <h1>AUREN POV Segment Prelabels</h1>
    <p>Heuristic pre-labels for scene/action/sound/motion/highlight review. These are candidates, not truth labels.</p>
  </header>
  <main>
    <section><h2>Global Top Candidates</h2><div class="grid">{global_cards}</div></section>
    {''.join(sections)}
  </main>
</body>
</html>"""
    (out_dir / "review_segments.html").write_text(doc, encoding="utf-8")


def segment_card(root: Path, s: SegmentLabel) -> str:
    rel = Path(s.frame_path).relative_to(root).as_posix()
    return f"""<article class="card">
      <img src="{html.escape(rel)}" alt="{html.escape(s.segment_id)}" />
      <p class="meta"><span class="score">{s.highlight_score}</span> · {html.escape(s.segment_id)} · {fmt_time(s.start)}-{fmt_time(s.end)}</p>
      <p class="meta">scene: <code>{html.escape(','.join(s.scene))}</code></p>
      <p class="meta">action: <code>{html.escape(','.join(s.pet_action))}</code></p>
      <p class="meta">event: <code>{html.escape(','.join(s.pet_event))}</code></p>
      <p class="meta">quality: <code>{html.escape(s.quality)}</code></p>
      <p class="meta">{html.escape(s.why_memorable)}</p>
    </article>"""


def write_csv(path: Path, rows: list[SegmentLabel]) -> None:
    if not rows:
        return
    fieldnames = list(asdict(rows[0]).keys())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            item = asdict(row)
            for key, value in item.items():
                if isinstance(value, list):
                    item[key] = "|".join(value)
            writer.writerow(item)


def write_labeling_queue(out_dir: Path, top_global: list[SegmentLabel]) -> None:
    path = out_dir / "human_label_queue.csv"
    fields = [
        "segment_id", "video_id", "video_name", "start", "end", "frame_path",
        "auto_scene", "auto_action", "auto_sound", "auto_event", "auto_score",
        "human_scene", "human_action", "human_sound", "human_event", "human_highlight_score",
        "human_why_memorable", "approve_for_diary", "approve_for_comic", "approve_for_vlog",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for s in top_global:
            writer.writerow({
                "segment_id": s.segment_id,
                "video_id": s.video_id,
                "video_name": s.video_name,
                "start": s.start,
                "end": s.end,
                "frame_path": s.frame_path,
                "auto_scene": "|".join(s.scene),
                "auto_action": "|".join(s.pet_action),
                "auto_sound": "|".join(s.sound_event),
                "auto_event": "|".join(s.pet_event),
                "auto_score": s.highlight_score,
                "human_scene": "",
                "human_action": "",
                "human_sound": "",
                "human_event": "",
                "human_highlight_score": "",
                "human_why_memorable": "",
                "approve_for_diary": "",
                "approve_for_comic": "",
                "approve_for_vlog": "",
            })


def gradient_energy(gray: np.ndarray) -> float:
    gx = np.diff(gray, axis=1)
    gy = np.diff(gray, axis=0)
    return float((np.mean(np.abs(gx)) + np.mean(np.abs(gy))) / 2)


def normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if abs(hi - lo) < 1e-9:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def dedupe(values: list[str]) -> list[str]:
    out = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def fmt_time(seconds: float) -> str:
    s = max(0, int(round(float(seconds))))
    return f"{s // 60:02d}:{s % 60:02d}"


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
