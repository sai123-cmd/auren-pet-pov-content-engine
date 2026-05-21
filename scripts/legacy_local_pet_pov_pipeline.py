#!/usr/bin/env python3
"""
AUREN Pet POV content validation pipeline.

Input: raw first-person pet video.
Output: highlight tags, edited vlog, pet diary, comic summary.

This is intentionally independent from the App. It is a local validation tool
for proving the capture-to-content loop before product integration.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import textwrap
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


@dataclass
class VideoMeta:
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool


@dataclass
class FrameSignal:
    index: int
    time: float
    frame_path: str
    motion: float
    sharpness: float
    brightness: float
    contrast: float
    audio_energy: float
    novelty: float
    score: float
    tags: list[str]
    reason: str


@dataclass
class Highlight:
    rank: int
    start: float
    end: float
    peak_time: float
    duration: float
    score: float
    tags: list[str]
    title: str
    reason: str
    frame_path: str
    clip_path: str | None = None
    panel_path: str | None = None


PET_TAGS = {
    "run_chase": "奔跑/追逐",
    "sniff_explore": "嗅闻/探索",
    "sudden_attention": "突然注意",
    "human_interaction": "与人互动",
    "quiet_observe": "停下观察",
    "audio_event": "声音触发",
    "scene_change": "环境变化",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="AUREN pet POV content pipeline")
    parser.add_argument("--input", required=True, help="Raw pet POV video file")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--top-k", type=int, default=5, help="Number of highlight moments")
    parser.add_argument("--sample-interval", type=float, default=1.0, help="Frame sampling interval in seconds")
    parser.add_argument("--segment-duration", type=float, default=3.6, help="Default highlight clip duration")
    args = parser.parse_args()

    source = Path(args.input).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Input video not found: {source}")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg and ffprobe are required")

    out_dir = Path(args.output).expanduser().resolve()
    analysis_dir = out_dir / "analysis"
    frames_dir = analysis_dir / "frames"
    clips_dir = out_dir / "clips"
    panels_dir = out_dir / "comic_panels"
    final_dir = out_dir / "outputs"
    for directory in [analysis_dir, frames_dir, clips_dir, panels_dir, final_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    meta = probe_video(source)
    print(f"[1/6] video: {meta.duration:.1f}s, {meta.width}x{meta.height}, audio={meta.has_audio}")

    print("[2/6] extract analysis frames")
    samples = extract_frames(source, frames_dir, meta.duration, args.sample_interval)
    audio_curve = extract_audio_curve(source, analysis_dir, meta.duration) if meta.has_audio else []

    print("[3/6] score pet POV highlights")
    frame_signals = analyze_frame_signals(samples, audio_curve)
    highlights = select_highlights(frame_signals, meta.duration, args.top_k, args.segment_duration)
    write_json(analysis_dir / "timeline.json", [asdict(item) for item in frame_signals])

    print("[4/6] render vlog clips")
    render_highlight_clips(source, highlights, clips_dir, meta.has_audio)
    vlog_path = final_dir / "vlog.mp4"
    render_vlog(highlights, clips_dir, vlog_path)

    print("[5/6] generate pet diary")
    diary = build_pet_diary(source, meta, highlights)
    (final_dir / "pet_diary.md").write_text(diary["markdown"], encoding="utf-8")
    write_json(final_dir / "pet_diary.json", diary["json"])
    edit_plan = build_edit_plan(source, highlights, vlog_path)
    write_json(final_dir / "edit_plan.json", edit_plan)

    print("[6/6] generate comic summary")
    comic_panels = render_comic_panels(highlights, panels_dir)
    comic_summary = final_dir / "comic_summary.png"
    render_comic_strip(comic_panels, highlights, comic_summary)
    write_json(analysis_dir / "highlights.json", [asdict(item) for item in highlights])
    write_report(out_dir, source, meta, highlights, vlog_path, comic_summary)

    print("")
    print("Done")
    print(f"- highlights: {analysis_dir / 'highlights.json'}")
    print(f"- vlog:       {vlog_path}")
    print(f"- diary:      {final_dir / 'pet_diary.md'}")
    print(f"- comic:      {comic_summary}")


def probe_video(source: Path) -> VideoMeta:
    payload = json.loads(run([
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(source),
    ]).stdout)
    video = next((stream for stream in payload["streams"] if stream.get("codec_type") == "video"), None)
    if not video:
        raise RuntimeError("No video stream found")
    has_audio = any(stream.get("codec_type") == "audio" for stream in payload["streams"])
    return VideoMeta(
        duration=max(float(payload.get("format", {}).get("duration", 0) or video.get("duration", 0) or 1), 1),
        width=int(video.get("width", 0) or 0),
        height=int(video.get("height", 0) or 0),
        fps=parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        has_audio=has_audio,
    )


def extract_frames(source: Path, frames_dir: Path, duration: float, interval: float) -> list[tuple[float, Path]]:
    times = []
    t = 0.5
    while t < max(duration - 0.2, 0.6):
        times.append(t)
        t += max(interval, 0.5)
    if not times:
        times = [0.1]

    samples = []
    for idx, time_point in enumerate(times, 1):
        frame_path = frames_dir / f"frame_{idx:04d}_{time_point:.1f}s.jpg"
        if not frame_path.exists():
            run([
                "ffmpeg",
                "-y",
                "-ss",
                f"{time_point:.3f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                "scale=720:-2",
                "-q:v",
                "3",
                str(frame_path),
            ])
        samples.append((time_point, frame_path))
    return samples


def extract_audio_curve(source: Path, analysis_dir: Path, duration: float) -> list[float]:
    wav_path = analysis_dir / "audio_16k_mono.wav"
    run([
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-acodec",
        "pcm_s16le",
        str(wav_path),
    ])
    if not wav_path.exists():
        return []

    with wave.open(str(wav_path), "rb") as wav:
        sample_rate = wav.getframerate()
        audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

    window = max(1, int(sample_rate))
    energies = []
    for start in range(0, len(audio), window):
        chunk = audio[start:start + window]
        if len(chunk) == 0:
            energies.append(0.0)
        else:
            energies.append(float(np.sqrt(np.mean(chunk * chunk))))
    while len(energies) < math.ceil(duration):
        energies.append(0.0)
    return normalize_list(energies)


def analyze_frame_signals(samples: list[tuple[float, Path]], audio_curve: list[float]) -> list[FrameSignal]:
    signals = []
    prev_gray = None
    prev_hist = None
    raw_items: list[dict[str, Any]] = []

    for index, (time_point, frame_path) in enumerate(samples):
        image = Image.open(frame_path).convert("RGB").resize((160, 160))
        gray = np.asarray(ImageOps.grayscale(image), dtype=np.float32) / 255.0
        rgb = np.asarray(image, dtype=np.float32) / 255.0

        motion = float(np.mean(np.abs(gray - prev_gray))) if prev_gray is not None else 0.0
        sharpness = gradient_energy(gray)
        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))
        hist, _ = np.histogram(gray, bins=24, range=(0, 1), density=True)
        novelty = float(np.mean(np.abs(hist - prev_hist))) if prev_hist is not None else 0.0
        color_var = float(np.mean(np.std(rgb, axis=(0, 1))))
        audio_energy = audio_curve[min(int(time_point), len(audio_curve) - 1)] if audio_curve else 0.0

        raw_items.append({
            "index": index,
            "time": time_point,
            "frame_path": str(frame_path),
            "motion": motion,
            "sharpness": sharpness,
            "brightness": brightness,
            "contrast": contrast,
            "novelty": novelty,
            "color_var": color_var,
            "audio_energy": audio_energy,
        })

        prev_gray = gray
        prev_hist = hist

    for key in ["motion", "sharpness", "contrast", "novelty", "color_var"]:
        normalized = normalize_list([item[key] for item in raw_items])
        for item, value in zip(raw_items, normalized):
            item[key] = value

    for item in raw_items:
        tags = classify_pet_pov_tags(item)
        score = (
            item["motion"] * 0.38
            + item["sharpness"] * 0.18
            + item["contrast"] * 0.12
            + item["novelty"] * 0.14
            + item["audio_energy"] * 0.12
            + item["color_var"] * 0.06
        )
        tag_boost = 0.04 if "run_chase" in tags or "audio_event" in tags else 0.0
        score = min(1.0, score + tag_boost)
        signals.append(FrameSignal(
            index=item["index"],
            time=round(item["time"], 2),
            frame_path=item["frame_path"],
            motion=round(item["motion"], 4),
            sharpness=round(item["sharpness"], 4),
            brightness=round(item["brightness"], 4),
            contrast=round(item["contrast"], 4),
            audio_energy=round(item["audio_energy"], 4),
            novelty=round(item["novelty"], 4),
            score=round(score * 100, 1),
            tags=tags,
            reason=build_reason(tags, item),
        ))
    return signals


def select_highlights(signals: list[FrameSignal], duration: float, top_k: int, segment_duration: float) -> list[Highlight]:
    ranked = sorted(signals, key=lambda signal: signal.score, reverse=True)
    selected: list[FrameSignal] = []
    min_gap = max(2.0, segment_duration + 0.4)

    for signal in ranked:
        if all(abs(signal.time - other.time) >= min_gap for other in selected):
            selected.append(signal)
        if len(selected) >= top_k:
            break
    for signal in ranked:
        if len(selected) >= top_k:
            break
        if signal not in selected:
            selected.append(signal)

    highlights = []
    for rank, signal in enumerate(sorted(selected, key=lambda item: item.time), 1):
        start = max(0.0, min(duration - 0.2, signal.time - segment_duration * 0.45))
        end = min(duration, start + segment_duration)
        highlights.append(Highlight(
            rank=rank,
            start=round(start, 2),
            end=round(end, 2),
            peak_time=signal.time,
            duration=round(end - start, 2),
            score=signal.score,
            tags=signal.tags,
            title=build_title(signal),
            reason=signal.reason,
            frame_path=signal.frame_path,
        ))
    return highlights


def render_highlight_clips(source: Path, highlights: list[Highlight], clips_dir: Path, has_audio: bool) -> None:
    for highlight in highlights:
        clip_path = clips_dir / f"highlight_{highlight.rank:02d}.mp4"
        highlight.clip_path = str(clip_path)
        vf = "scale=720:-2,setsar=1,format=yuv420p"
        args = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{highlight.start:.2f}",
            "-i",
            str(source),
            "-t",
            f"{highlight.duration:.2f}",
            "-map",
            "0:v:0",
        ]
        if has_audio:
            args += ["-map", "0:a:0?"]
        args += [
            "-vf",
            vf,
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
        ]
        if has_audio:
            args += ["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"]
        else:
            args += ["-an"]
        args += ["-movflags", "+faststart", str(clip_path)]
        run(args)


def render_vlog(highlights: list[Highlight], clips_dir: Path, vlog_path: Path) -> None:
    concat_path = clips_dir / "concat.txt"
    lines = []
    for highlight in highlights:
        clip_path = Path(highlight.clip_path or "")
        lines.append(f"file '{clip_path.as_posix()}'")
    concat_path.write_text("\n".join(lines), encoding="utf-8")
    run([
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(vlog_path),
    ])


def build_pet_diary(source: Path, meta: VideoMeta, highlights: list[Highlight]) -> dict[str, Any]:
    timeline = []
    for highlight in highlights:
        tags_cn = "、".join(PET_TAGS.get(tag, tag) for tag in highlight.tags)
        timeline.append({
            "time": f"{fmt_time(highlight.start)}-{fmt_time(highlight.end)}",
            "title": highlight.title,
            "tags": highlight.tags,
            "tags_cn": tags_cn,
            "caption": diary_sentence(highlight),
            "reason": highlight.reason,
        })

    title = "今天我看到的世界"
    summary = "我从自己的视角记录了一段小冒险。系统挑出了画面变化、声音变化和清晰观察的时刻，把它们整理成今天的故事。"
    lines = [
        f"# {title}",
        "",
        f"- 原始素材: `{source.name}`",
        f"- 视频时长: {fmt_time(meta.duration)}",
        f"- 高光数量: {len(highlights)}",
        "",
        summary,
        "",
        "## 高光日志",
        "",
    ]
    for item in timeline:
        lines.append(f"### {item['time']} · {item['title']}")
        lines.append("")
        lines.append(item["caption"])
        lines.append("")
        lines.append(f"标签: {item['tags_cn']}")
        lines.append("")

    return {
        "json": {
            "title": title,
            "summary": summary,
            "source": source.name,
            "duration": meta.duration,
            "timeline": timeline,
        },
        "markdown": "\n".join(lines),
    }


def build_edit_plan(source: Path, highlights: list[Highlight], vlog_path: Path) -> dict[str, Any]:
    return {
        "title": "宠物第一视角高光 Vlog",
        "source": source.name,
        "output": str(vlog_path),
        "structure": [
            {
                "section": "开场 — 今天的视角",
                "description": "用宠物第一视角的清晰高光建立一天的氛围。",
                "clips": [highlight_to_clip(highlight) for highlight in highlights[:2]],
            },
            {
                "section": "探索 — 变化和声音",
                "description": "保留运动、声音或场景变化明显的片段。",
                "clips": [highlight_to_clip(highlight) for highlight in highlights[2:4]],
            },
            {
                "section": "收尾 — 被记住的一刻",
                "description": "用最后一个稳定片段完成宠物日志。",
                "clips": [highlight_to_clip(highlight) for highlight in highlights[4:]],
            },
        ],
        "bgm_suggestion": "genre: warm acoustic; mood: curious, playful; tempo: moderate; keep original audio if pet sound is meaningful",
        "editing_notes": "Pet POV highlight scoring is custom to AUREN. The editing workflow can reuse the ai-video-editing-skill structure, but highlight detection is domain-specific.",
    }


def highlight_to_clip(highlight: Highlight) -> dict[str, Any]:
    return {
        "file": Path(highlight.clip_path or "").name,
        "source_start": highlight.start,
        "source_end": highlight.end,
        "note": highlight.title,
        "tags": highlight.tags,
        "subtitle": "",
    }


def render_comic_panels(highlights: list[Highlight], panels_dir: Path) -> list[Path]:
    font_title = load_font(30, bold=True)
    font_caption = load_font(28)
    panel_paths = []
    for highlight in highlights:
        image = Image.open(highlight.frame_path).convert("RGB")
        panel = make_comic_image(image, (760, 760))
        canvas = Image.new("RGB", (820, 980), "#FFFBF7")
        canvas.paste(panel, (30, 30))
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle((30, 30, 790, 790), radius=24, outline="#3D2B1F", width=6)
        draw.rounded_rectangle((44, 44, 776, 776), radius=18, outline="#FFFBF7", width=3)
        draw.rounded_rectangle((48, 820, 772, 930), radius=24, fill="#FFF7EE", outline="#D4C4B0", width=3)
        draw.ellipse((72, 848, 126, 902), fill="#F0A854")
        draw.text((99, 875), str(highlight.rank), fill="#3D2B1F", font=font_title, anchor="mm")
        caption = comic_caption(highlight)
        draw_wrapped_text(draw, caption, (150, 848), font_caption, "#3D2B1F", max_width=580, line_spacing=8)
        panel_path = panels_dir / f"panel_{highlight.rank:02d}.png"
        canvas.save(panel_path)
        highlight.panel_path = str(panel_path)
        panel_paths.append(panel_path)
    return panel_paths


def render_comic_strip(panel_paths: list[Path], highlights: list[Highlight], out_path: Path) -> None:
    cols = 2
    panel_w, panel_h = 410, 490
    gap = 24
    header_h = 92
    rows = math.ceil(len(panel_paths) / cols)
    width = cols * panel_w + (cols + 1) * gap
    height = header_h + rows * panel_h + (rows + 1) * gap
    canvas = Image.new("RGB", (width, height), "#FDF8F3")
    draw = ImageDraw.Draw(canvas)
    draw.text((gap, 34), "今日高光漫画", fill="#3D2B1F", font=load_font(38, bold=True))
    draw.text((width - gap, 42), "AUREN PET POV", fill="#8B7355", font=load_font(18), anchor="ra")
    for idx, path in enumerate(panel_paths):
        panel = Image.open(path).convert("RGB").resize((panel_w, panel_h), Image.Resampling.LANCZOS)
        x = gap + (idx % cols) * (panel_w + gap)
        y = header_h + gap + (idx // cols) * (panel_h + gap)
        canvas.paste(panel, (x, y))
    canvas.save(out_path)


def write_report(out_dir: Path, source: Path, meta: VideoMeta, highlights: list[Highlight], vlog: Path, comic: Path) -> None:
    lines = [
        "# AUREN Pet POV Pipeline Report",
        "",
        f"- Source: `{source}`",
        f"- Duration: {fmt_time(meta.duration)}",
        f"- Resolution: {meta.width}x{meta.height}",
        f"- Vlog: `{vlog}`",
        f"- Comic: `{comic}`",
        "",
        "## Highlights",
        "",
    ]
    for h in highlights:
        tags = ", ".join(PET_TAGS.get(tag, tag) for tag in h.tags)
        lines.append(f"{h.rank}. {fmt_time(h.start)}-{fmt_time(h.end)} `{h.score}` {h.title} [{tags}]")
        lines.append(f"   - {h.reason}")
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def classify_pet_pov_tags(item: dict[str, float]) -> list[str]:
    tags = []
    if item["motion"] > 0.68:
        tags.append("run_chase")
    elif item["motion"] > 0.38:
        tags.append("sniff_explore")
    if item["novelty"] > 0.58:
        tags.append("scene_change")
    if item["audio_energy"] > 0.62:
        tags.append("audio_event")
    if item["motion"] < 0.32 and item["sharpness"] > 0.5:
        tags.append("quiet_observe")
    if item["motion"] > 0.5 and item["audio_energy"] > 0.4:
        tags.append("sudden_attention")
    if not tags:
        tags.append("quiet_observe")
    return tags[:3]


def build_reason(tags: list[str], item: dict[str, float]) -> str:
    parts = []
    if "run_chase" in tags:
        parts.append("运动强度高，像奔跑或追逐")
    if "sniff_explore" in tags:
        parts.append("画面持续变化，适合表现探索")
    if "audio_event" in tags:
        parts.append("音频能量突增，可能有叫声或环境声")
    if "scene_change" in tags:
        parts.append("场景差异明显")
    if "quiet_observe" in tags:
        parts.append("画面较稳定且清晰，适合做观察镜头")
    return "；".join(parts) or "综合得分较高"


def build_title(signal: FrameSignal) -> str:
    if "run_chase" in signal.tags:
        return "突然加速"
    if "sniff_explore" in signal.tags:
        return "认真探索"
    if "audio_event" in signal.tags:
        return "被声音吸引"
    if "scene_change" in signal.tags:
        return "发现新环境"
    return "停下观察"


def diary_sentence(highlight: Highlight) -> str:
    if "run_chase" in highlight.tags:
        return "我突然跑了起来，眼前的路一下子变得很快，风和声音都冲到身边。"
    if "sniff_explore" in highlight.tags:
        return "我靠近了一点，认真闻了闻，这里好像藏着新的故事。"
    if "audio_event" in highlight.tags:
        return "我听见了一个声音，立刻停下来确认它从哪里来。"
    if "scene_change" in highlight.tags:
        return "眼前的环境变了，我记住了这个新的地方。"
    return "我停下来观察了一会儿，把这一刻安静地收进今天的记忆里。"


def comic_caption(highlight: Highlight) -> str:
    if "run_chase" in highlight.tags:
        return "冲呀，我要追上它！"
    if "sniff_explore" in highlight.tags:
        return "这里闻起来不一样。"
    if "audio_event" in highlight.tags:
        return "等等，我听见声音了。"
    if "scene_change" in highlight.tags:
        return "前面好像有新地方。"
    return "先停下，看一看。"


def make_comic_image(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    base = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    color = ImageOps.posterize(base, 4)
    color = ImageEnhanceCompat(color, saturation=1.2, contrast=1.08)
    edges = base.convert("L").filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.autocontrast(edges)
    edges = ImageOps.invert(edges)
    edges = edges.point(lambda p: 255 if p > 185 else 40)
    return Image.composite(color, Image.new("RGB", size, "#17110D"), edges.convert("L"))


def ImageEnhanceCompat(image: Image.Image, saturation: float, contrast: float) -> Image.Image:
    from PIL import ImageEnhance
    image = ImageEnhance.Color(image).enhance(saturation)
    image = ImageEnhance.Contrast(image).enhance(contrast)
    return image


def gradient_energy(gray: np.ndarray) -> float:
    gx = np.diff(gray, axis=1)
    gy = np.diff(gray, axis=0)
    return float((np.mean(np.abs(gx)) + np.mean(np.abs(gy))) / 2)


def normalize_list(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if abs(hi - lo) < 1e-9:
        return [0.0 for _ in values]
    return [(value - lo) / (hi - lo) for value in values]


def parse_fps(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        denominator_f = float(denominator)
        return float(numerator) / denominator_f if denominator_f else 0.0
    return float(value)


def fmt_time(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size, index=1 if bold else 0)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_wrapped_text(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], font: ImageFont.ImageFont, fill: str, max_width: int, line_spacing: int) -> None:
    x, y = xy
    lines = wrap_text(draw, text, font, max_width)
    for line in lines[:2]:
        draw.text((x, y), line, fill=fill, font=font)
        bbox = draw.textbbox((x, y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_spacing


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines = []
    current = ""
    for char in text:
        trial = current + char
        width = draw.textbbox((0, 0), trial, font=font)[2]
        if width > max_width and current:
            lines.append(current)
            current = char
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True)
    if result.returncode != 0:
        cmd = " ".join(args)
        raise RuntimeError(f"Command failed: {cmd}\n{result.stderr[-1600:]}")
    return result


if __name__ == "__main__":
    main()
