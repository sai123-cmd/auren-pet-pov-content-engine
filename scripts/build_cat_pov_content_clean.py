#!/usr/bin/env python3
"""Build clean Chinese cat POV diary, comic inputs, and vlog from VLM rows."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

try:
    from render_pov_locked_comic_page import render_pov_locked_comic_page
except Exception:  # pragma: no cover - optional local renderer fallback.
    render_pov_locked_comic_page = None


BEATS = [
    {
        "key": "ground_patrol",
        "title": "碎石路开场",
        "caption": "路先醒了",
        "anchor_keywords": ["gravel path", "path or road", "low-angle pov"],
        "avoid_keywords": ["face", "nose", "close-up", "extreme close-up"],
        "event_keywords": ["ground_patrol", "owner_check_in"],
        "action_keywords": ["walk", "creep", "search"],
        "time_preference": 0.10,
        "diary": "我先让胡须贴近碎石路。法国的早晨没有大声说话，只把小石头、草边和树影一粒一粒摆到我面前。",
        "comic": "低角度碎石路开场，猫耳朵或胡须在画面边缘，像一张旅行地图刚被摊开。",
    },
    {
        "key": "roof_view",
        "title": "苔藓屋顶",
        "caption": "屋顶也有味道",
        "anchor_keywords": ["roof", "tiled roof", "moss-covered", "countryside"],
        "scene_keywords": ["roof", "tiled", "moss", "countryside"],
        "event_keywords": ["ground_patrol", "new_scene_discovery"],
        "action_keywords": ["walk", "look_around", "pause_observe"],
        "time_preference": 0.18,
        "diary": "没走多久，我看到一片长着苔藓的旧屋顶。人类会说那是风景，我会说那是一块被太阳晒暖的老饼干。",
        "comic": "苔藓屋顶和乡野远景，画成像古老小城堡的高处发现，猫把它想象成可以闻的明信片。",
    },
    {
        "key": "riverbank",
        "title": "水边停顿",
        "caption": "水边换了气味",
        "anchor_keywords": ["riverbank", "water", "muddy"],
        "scene_keywords": ["riverbank", "water", "muddy", "pond", "lake"],
        "event_keywords": ["threshold_pause", "ground_patrol"],
        "action_keywords": ["sniff", "pause_observe"],
        "time_preference": 0.28,
        "diary": "水边的空气突然变湿，泥土把声音压低。我停下来闻了一会儿，确认这条路不是简单地往前走，它还会横着拐进水里。",
        "comic": "泥土水边和近距离胡须，画成猫在水气前停步，水面像打开了另一页地图。",
    },
    {
        "key": "cat_close",
        "title": "鼻子抢镜",
        "caption": "我来确认一下",
        "anchor_keywords": ["face", "nose", "whiskers", "close-up", "extreme close-up"],
        "scene_keywords": ["face", "nose", "whiskers", "close-up"],
        "event_keywords": ["owner_check_in", "ground_patrol", "sudden_attention"],
        "action_keywords": ["sniff", "walk", "search"],
        "time_preference": 0.38,
        "diary": "后来我的鼻子决定亲自入镜。它一向比我积极，尤其遇到碎石、草根和不肯说明来历的风。",
        "comic": "猫鼻子或脸部突然贴近画面，做成幽默转场，像猫把镜头抢过来盖章确认。",
    },
    {
        "key": "woodpile",
        "title": "木柴堡垒",
        "caption": "这里像一堵墙",
        "anchor_keywords": ["woodpile", "logs", "stacked"],
        "scene_keywords": ["woodpile", "logs", "wood", "stacked"],
        "event_keywords": ["threshold_pause", "new_scene_discovery", "ground_patrol"],
        "action_keywords": ["sniff", "look_up", "creep"],
        "time_preference": 0.48,
        "diary": "然后我遇见一整面木柴墙。它们排得太整齐，像在假装自己不是秘密基地。",
        "comic": "木柴堆画成森林边的堡垒，猫从低处经过，想象木柴后面藏着另一条小路。",
    },
    {
        "key": "forest_floor",
        "title": "树根迷宫",
        "caption": "下面也有路",
        "anchor_keywords": ["forest floor", "mossy logs", "fallen branches", "twigs"],
        "scene_keywords": ["mossy", "fallen", "branches", "leaves", "tree trunk", "forest floor"],
        "event_keywords": ["brush_inspection", "ground_patrol", "prey_track"],
        "action_keywords": ["sniff", "search", "creep"],
        "time_preference": 0.62,
        "diary": "真正复杂的是树根下面。落叶、苔藓和断枝挤在一起，像一座只允许小动物进入的迷宫。",
        "comic": "森林地面、苔藓树根和断枝，画成猫眼里的小型迷宫，光点像路标。",
    },
    {
        "key": "human_van",
        "title": "人类据点",
        "caption": "他们也在这儿",
        "anchor_keywords": ["person", "human", "white van", "van", "parked"],
        "avoid_keywords": ["construction vehicle", "excavator", "heavy machinery"],
        "scene_keywords": ["van", "vehicle", "person", "human", "machinery", "wheel"],
        "event_keywords": ["owner_check_in", "ground_patrol"],
        "action_keywords": ["approach_human", "walk", "climb"],
        "time_preference": 0.80,
        "diary": "快到后面，人类和车终于出现了。他们坐在那里，好像这片森林的临时售票员。",
        "comic": "白色车、人类腿或车轮，猫从低处看，把这里当作旅途中的人类据点。",
    },
    {
        "key": "ending",
        "title": "松针收尾",
        "caption": "今天藏进松针里",
        "anchor_keywords": ["evergreen", "pine", "needles", "underneath"],
        "scene_keywords": ["evergreen", "pine", "branches", "needles", "underneath"],
        "event_keywords": ["brush_inspection", "threshold_pause", "quiet_observation"],
        "action_keywords": ["sniff", "hide", "stalk", "pause_observe"],
        "time_preference": 0.92,
        "diary": "最后我钻到松针下面。光变得很碎，空气也安静下来，我把今天整张法国气味地图折好，藏进身上。",
        "comic": "松针和暗绿色枝叶包住画面，猫在里面安静收尾，像把一张旅行地图折进梦里。",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--bgm", default="")
    args = parser.parse_args()

    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(Path(args.manifest))
    rows = [enrich(row, manifest) for row in load_json(Path(args.results)) if row.get("parse_ok")]
    selected = select_rows(rows)

    highlights_json = out / "cat_pov_highlights_clean.json"
    write_json(highlights_json, [public(item) for item in selected])
    write_csv(out / "cat_pov_highlights_clean.csv", [public(item) for item in selected])
    write_diary(out / "cat_diary_story_clean.md", selected)
    write_evidence(out / "cat_diary_evidence_clean.md", selected)
    write_reference_board(out / "cat_comic_reference_mature_real_scenes.jpg", selected[:7])
    write_comic_prompt(out / "cat_comic_mature_prompt.md", selected[:7])
    if render_pov_locked_comic_page:
        render_pov_locked_comic_page(
            highlights_json,
            out / "cat_comic_page_looki_pov_locked_generated_v4.png",
            out / "comic_pov_locked_frames",
        )
    write_vlog_plan(out / "cat_vlog_plan_clean.md", selected)
    render_vlog(out, selected, Path(args.bgm) if args.bgm else None)
    write_run_notes(out / "RUN_NOTES.md", selected)
    print(f"Done: {out}")


def load_manifest(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {row["id"]: row for row in csv.DictReader(f)}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def enrich(row: dict[str, Any], manifest: dict[str, dict[str, str]]) -> dict[str, Any]:
    row = dict(row)
    meta = manifest.get(row.get("video_id", ""), {})
    row["source_path"] = meta.get("path", "")
    row["video_name_clean"] = meta.get("name", row.get("video_name", ""))
    row["text"] = " ".join(str(row.get(key, "")) for key in ["scene", "visible_subjects", "pet_action", "pet_event", "description", "why_memorable"]).lower()
    row["fit_score"] = score_num(row.get("vlog_fit")) + score_num(row.get("diary_fit")) + score_num(row.get("comic_fit"))
    return row


def select_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used_segments: set[str] = set()
    used_time_bins: set[int] = set()
    max_end = max((float(row.get("end") or 0) for row in rows), default=1.0)
    for beat in BEATS:
        candidates = sorted(rows, key=lambda row: beat_score(row, beat, used_segments, used_time_bins, max_end), reverse=True)
        row = next((candidate for candidate in candidates if candidate["segment_id"] not in used_segments), None)
        if not row:
            continue
        used_segments.add(row["segment_id"])
        used_time_bins.add(int(float(row["start"]) // 600))
        selected.append({"beat": beat, "row": row})
    return selected


def beat_score(row: dict[str, Any], beat: dict[str, Any], used_segments: set[str], used_time_bins: set[int], max_end: float) -> float:
    text = row["text"]
    score = row["fit_score"] / 20.0
    score += sum(18 for key in beat.get("anchor_keywords", []) if key in text)
    score += sum(8 for key in beat["event_keywords"] if key in text)
    score += sum(4 for key in beat["action_keywords"] if key in text)
    score += sum(10 for key in beat.get("scene_keywords", []) if key in text)
    score -= sum(14 for key in beat.get("avoid_keywords", []) if key in text)
    if row["segment_id"] in used_segments:
        score -= 1000
    if int(float(row["start"]) // 600) in used_time_bins:
        score -= 2
    target = float(beat.get("time_preference", 0.5))
    position = float(row.get("start") or 0) / max(max_end, 1.0)
    score -= abs(position - target) * 9
    if "bad" in str(row.get("quality", "")).lower():
        score -= 10
    return score


def public(item: dict[str, Any]) -> dict[str, Any]:
    beat, row = item["beat"], item["row"]
    return {
        "section": beat["title"],
        "caption": beat["caption"],
        "segment_id": row["segment_id"],
        "video_id": row["video_id"],
        "video_name": row.get("video_name_clean", ""),
        "start": row["start"],
        "end": row["end"],
        "scene": row.get("scene", ""),
        "visible_subjects": row.get("visible_subjects", ""),
        "pet_action": row.get("pet_action", ""),
        "pet_event": row.get("pet_event", ""),
        "why_memorable": row.get("why_memorable", ""),
        "source_path": row.get("source_path", ""),
        "primary_comic_frame": row.get("primary_comic_frame", ""),
        "strip": row.get("strip", ""),
    }


def write_diary(path: Path, selected: list[dict[str, Any]]) -> None:
    body = [item["beat"]["diary"] for item in selected]
    text = [
        "# 今天，我把法国折成了一张气味地图",
        "",
        "今天出门的时候，我本来只是想确认一下这条路有没有认真准备好。结果刚把胡须贴近地面，法国就开始一层一层打开：先是碎石路，然后是苔藓屋顶，再往后是水边、木柴、树根和人类停在森林边的小车。",
        "",
        " ".join(body[:3]),
        "",
        " ".join(body[3:6]),
        "",
        " ".join(body[6:]),
        "",
        "所以这不是一段普通散步。普通散步不会经过屋顶和水气，不会让木柴堆看起来像堡垒，也不会把车边的人类缩成低低的风景。等我回去趴下时，今天的结论已经很清楚：法国很大，路很多，我只负责把它们一条一条闻出来。",
    ]
    path.write_text("\n".join(text), encoding="utf-8")


def write_evidence(path: Path, selected: list[dict[str, Any]]) -> None:
    lines = ["# 猫咪日记证据表", ""]
    for item in selected:
        row, beat = item["row"], item["beat"]
        lines.append(f"- {beat['title']} | {row['segment_id']} | {fmt(row['start'])}-{fmt(row['end'])} | action={row.get('pet_action')} | event={row.get('pet_event')}")
        lines.append(f"  - scene: {row.get('scene', '')}")
        lines.append(f"  - subjects: {row.get('visible_subjects', '')}")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_reference_board(path: Path, selected: list[dict[str, Any]]) -> None:
    width, height = 1600, 1260
    canvas = Image.new("RGB", (width, height), (244, 238, 228))
    draw = ImageDraw.Draw(canvas)
    draw.text((42, 34), "AUREN 猫咪 POV 成熟漫画参考板", font=font(38, True), fill=(28, 24, 20))
    draw.text((42, 84), "这些是真实关键帧。最终漫画要重绘成成熟叙事页，不要使用雷达、警告三角、路线图等分析符号。", font=font(22), fill=(82, 70, 58))
    boxes = [
        (42, 138, 680, 310),
        (746, 138, 380, 310),
        (1150, 138, 408, 310),
        (42, 520, 520, 360),
        (586, 520, 520, 360),
        (1130, 520, 428, 360),
        (42, 950, 520, 240),
    ]
    for idx, (item, box) in enumerate(zip(selected, boxes), 1):
        row, beat = item["row"], item["beat"]
        x, y, w, h = box
        img = Image.open(row["primary_comic_frame"]).convert("RGB")
        img = fit_cover(img, w, h)
        canvas.paste(img, (x, y))
        draw.rectangle([x, y, x + w, y + h], outline=(24, 22, 20), width=5)
        draw.rounded_rectangle([x + 14, y + 14, x + 64, y + 62], radius=14, fill=(255, 248, 212), outline=(24, 22, 20), width=3)
        draw.text((x + 31, y + 20), str(idx), font=font(25, True), fill=(24, 22, 20))
        draw.text((x, y + h + 12), f"{beat['title']} | {beat['caption']}", font=font(23, True), fill=(35, 30, 25))
        draw.text((x, y + h + 44), wrap(str(row.get("scene", "")), 42), font=font(17), fill=(90, 78, 68))
    canvas.save(path, quality=94)


def write_comic_prompt(path: Path, selected: list[dict[str, Any]]) -> None:
    panel_lines = []
    for idx, item in enumerate(selected, 1):
        row, beat = item["row"], item["beat"]
        panel_lines.append(
            f"{idx}. {beat['title']}: real scene={row.get('scene', '')}; subjects={row.get('visible_subjects', '')}; "
            f"action={row.get('pet_action', '')}; event={row.get('pet_event', '')}; comic idea={beat['comic']}; short bubble={beat['caption']}."
        )
    prompt = f"""Create a mature polished Looki-like hand-drawn multi-panel comic page based on the attached real cat POV reference board.

Style: soft digital watercolor, clean black gutters, cinematic lighting, expressive line art, readable scenes, gentle humor, professional webcomic polish.

Grounding: keep the real cat POV events recognizable: low outdoor paths, grass, leaves, people/feet if visible, trees/sky, boundaries, quiet observation. The cat may be implied by ears, paws, whiskers, shadow, or thought bubbles at the frame edge.

POV lock: preserve each panel's source camera angle, horizon, crop logic, object scale, and occlusion from the reference frame. Do not add visible cat ears, cat face, paws, whiskers, body, or a recurring cat avatar unless that exact element is already visible in that specific source frame. Do not convert a first-person/neck-camera frame into a third-person, over-the-shoulder, or cinematic external camera view.

Story arc: a cat in France turns one long outdoor walk into a scent-map travelogue: gravel road, mossy roof, wet riverbank, nose close-up, woodpile fortress, forest-floor maze, human van camp, evergreen hiding place.

Panels:
{chr(10).join(panel_lines)}

Text: use only short readable Chinese bubbles, preferably these exact short phrases: 路先醒了, 屋顶也有味道, 水边换了气味, 我来确认一下, 这里像一堵墙, 下面也有路, 他们也在这儿, 今天藏进松针里.

Avoid: analysis symbols, radar circles, warning triangles, route-map overlays, UI graphics, debug marks, raw screenshots, contact sheet, storyboard, photo filter, unrelated fantasy, generic cute-cat portrait page, invented ears/face/body, shifted POV, unreadable text, watermark."""
    path.write_text("# 成熟猫咪 POV 漫画生成提示\n\n```text\n" + prompt + "\n```\n", encoding="utf-8")


def write_vlog_plan(path: Path, selected: list[dict[str, Any]]) -> None:
    lines = ["# 猫咪 POV Vlog 剪辑方案", "", "片名：今天，我把法国折成了一张气味地图", ""]
    for idx, item in enumerate(selected, 1):
        row, beat = item["row"], item["beat"]
        lines.append(f"{idx}. {beat['title']} | {row['segment_id']} | {fmt(row['start'])}-{fmt(row['end'])} | {beat['caption']}")
        lines.append(f"   - scene: {row.get('scene', '')}")
        lines.append(f"   - action/event: {row.get('pet_action', '')} / {row.get('pet_event', '')}")
    path.write_text("\n".join(lines), encoding="utf-8")


def render_vlog(out: Path, selected: list[dict[str, Any]], bgm: Path | None) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return
    clip_dir = out / "cat_vlog_clips_clean"
    overlay_dir = out / "cat_vlog_overlays_clean"
    clip_dir.mkdir(exist_ok=True)
    overlay_dir.mkdir(exist_ok=True)
    clips: list[Path] = []
    for idx, item in enumerate(selected, 1):
        row, beat = item["row"], item["beat"]
        src = Path(row["source_path"])
        if not src.exists():
            continue
        start = max(0.0, float(row["start"]) + 0.15)
        duration = min(3.8, max(1.4, float(row["end"]) - float(row["start"]) - 0.15))
        overlay = overlay_dir / f"overlay_{idx:02d}.png"
        make_overlay(overlay, beat["title"], beat["caption"])
        clip = clip_dir / f"{idx:02d}_{row['segment_id']}.mp4"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{start:.2f}",
                "-t",
                f"{duration:.2f}",
                "-i",
                str(src),
                "-i",
                str(overlay),
                "-filter_complex",
                "[0:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,eq=contrast=1.06:saturation=1.08[v0];[v0][1:v]overlay=0:0,fps=30,format=yuv420p[v]",
                "-map",
                "[v]",
                "-map",
                "0:a:0?",
                "-af",
                "volume=0.72,aresample=44100,aformat=channel_layouts=stereo",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "21",
                "-c:a",
                "aac",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-shortest",
                str(clip),
            ],
            check=False,
        )
        if clip.exists() and clip.stat().st_size > 0:
            clips.append(clip)
    if not clips:
        return
    concat = out / "cat_vlog_concat_clean.txt"
    concat.write_text("\n".join(f"file '{clip.as_posix()}'" for clip in clips), encoding="utf-8")
    no_bgm = out / "cat_vlog_no_bgm_clean.mp4"
    subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", str(no_bgm)], check=False)
    final = out / "cat_vlog_story_clean.mp4"
    if bgm and bgm.exists() and no_bgm.exists():
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(no_bgm),
                "-stream_loop",
                "-1",
                "-i",
                str(bgm),
                "-filter_complex",
                "[0:a]volume=0.85[a0];[1:a]volume=0.20,afade=t=in:st=0:d=1.0[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=1[a]",
                "-map",
                "0:v",
                "-map",
                "[a]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(final),
            ],
            check=False,
        )
    elif no_bgm.exists():
        shutil.copy2(no_bgm, final)


def make_overlay(path: Path, section: str, caption: str) -> None:
    image = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([44, 42, 282, 92], radius=16, fill=(0, 0, 0, 120))
    draw.text((64, 52), section, font=font(27, True), fill=(255, 255, 255, 238))
    draw.rounded_rectangle([70, 582, 1210, 680], radius=28, fill=(0, 0, 0, 138))
    draw.text((102, 606), caption, font=font(43, True), fill=(255, 255, 255, 248))
    image.save(path)


def write_run_notes(path: Path, selected: list[dict[str, Any]]) -> None:
    lines = [
        "# Run Notes",
        "",
        "- MiniMax VLM analyzed image strips, not audio.",
        "- Source audio is preserved and mixed into the vlog.",
        "- True audio understanding still needs ASR/audio-event labels for meows, bells, owner speech, wind, and sudden sounds.",
        "- Final mature comic should be generated from `cat_comic_reference_mature_real_scenes.jpg` and `cat_comic_mature_prompt.md`.",
        "",
        f"- selected highlights: {len(selected)}",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def score_num(value: Any) -> float:
    try:
        value = float(value)
    except Exception:
        return 0.0
    return max(0.0, min(value, 100.0))


def fmt(value: Any) -> str:
    seconds = int(float(value))
    minutes, second = divmod(seconds, 60)
    return f"{minutes:02d}:{second:02d}"


def wrap(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    lines = []
    words = text.split()
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = (current + " " + word).strip()
    if current:
        lines.append(current)
    return "\n".join(lines[:3])


def fit_cover(image: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / image.width, height / image.height)
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


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


if __name__ == "__main__":
    main()
