#!/usr/bin/env python3
"""Build cat-specific AUREN POV content outputs, v2.

This version is intentionally not tied to one fixed cat sample. It selects
highlights by cat-like first-person beats: ground patrol, distance watching,
prey attention, sudden head turn, threshold crossing, and brush inspection.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


BEATS = [
    {
        "key": "ground_departure",
        "section": "贴地出发",
        "caption": "地面先向我报到。",
        "keywords": ["ground_patrol", "legs", "people", "field", "walking forward", "rough terrain", "low angle", "animal", "rock", "stone"],
    },
    {
        "key": "field_lines",
        "section": "田垄巡逻",
        "caption": "黑白条纹里有今天的路线。",
        "keywords": ["rows", "vegetation", "soil", "garden", "field", "people"],
    },
    {
        "key": "leaf_prey",
        "section": "落叶线索",
        "caption": "那边动了一下。",
        "keywords": ["prey_track", "prey", "leaf", "wooded", "squirrel", "rodent", "small animal", "scurries", "pans right"],
    },
    {
        "key": "threshold_cross",
        "section": "边界穿行",
        "caption": "开阔地要快点过。",
        "keywords": ["threshold_pause", "building", "post", "ground-level", "forward", "outdoor area", "courtyard"],
    },
    {
        "key": "sudden_attention",
        "section": "突然抬头",
        "caption": "上面也有消息。",
        "keywords": ["sudden_attention", "look_up", "looking up", "tilts upward", "turn", "post", "sky", "quick move"],
    },
    {
        "key": "brush_rustle",
        "section": "草堆沙沙",
        "caption": "答案躲在干草里。",
        "keywords": ["brush_inspection", "hide", "dry grass", "twigs", "hay", "straw", "foliage", "brush"],
    },
    {
        "key": "close_watch",
        "section": "低处盯梢",
        "caption": "我只靠近一点，再靠近一点。",
        "keywords": ["quiet_observation", "stalk", "forest floor", "burrowing", "forage", "close-up", "obscured", "quiet observation"],
    },
    {
        "key": "soft_ending",
        "section": "收起胡须",
        "caption": "今天的线索，收进胡须。",
        "keywords": ["quiet", "observation", "movement", "animal", "natural environment"],
    },
]


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--bgm", default="")
    args = parser.parse_args()

    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    rows = [dict(r) for r in json.loads(Path(args.results).read_text(encoding="utf-8")) if r.get("parse_ok")]
    manifest = load_manifest(Path(args.manifest))
    for row in rows:
        meta = manifest.get(row["video_id"], {})
        row["source_path"] = meta.get("path", "")
        row["video_name_clean"] = meta.get("name", row.get("video_name", ""))
        row["has_audio"] = truthy(meta.get("has_audio"))
        enrich(row)

    selected = select(rows)

    write_json(out / "cat_pov_highlights_v2.json", [public(x) for x in selected])
    write_csv(out / "cat_pov_highlights_v2.csv", [public(x) for x in selected])
    write_diary(out / "cat_diary_story_v2.md", selected)
    write_evidence(out / "cat_diary_evidence_v2.md", selected)
    write_comic_brief(out / "cat_comic_brief_v2.md", selected)
    write_reference_board(out / "cat_comic_reference_real_scenes_v2.jpg", selected[:6])
    write_vlog_plan(out / "cat_vlog_plan_v2.md", selected)
    render_vlog(out, selected, Path(args.bgm) if args.bgm else None)
    write_review(out / "cat_pov_self_evaluation_v2.md", rows, selected)
    write_readme(out / "README.md")
    print(f"Done: {out}")


def load_manifest(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def row_text(row: dict[str, Any]) -> str:
    fields = ["scene", "visible_subjects", "pet_action", "pet_event", "why_memorable", "video_name_clean"]
    return " ".join(str(row.get(k, "")) for k in fields).lower()


def enrich(row: dict[str, Any]) -> None:
    text = row_text(row)
    tags: list[str] = []
    if any(w in text for w in ["leaf", "wooded", "forest", "rocky"]):
        tags.append("林地/落叶")
    if any(w in text for w in ["rock", "stone", "pavement", "rough terrain"]):
        tags.append("碎石/地面")
    if any(w in text for w in ["prey_track", "prey", "small animal", "squirrel", "rodent", "scurries", "movement within"]):
        tags.append("猎物注意")
    if any(w in text for w in ["people", "human", "person"]):
        tags.append("远处有人")
    if any(w in text for w in ["field", "garden", "soil", "rows", "vegetation"]):
        tags.append("田地/草地")
    if any(w in text for w in ["threshold_pause", "building", "courtyard", "post", "paved"]):
        tags.append("边界/建筑")
    if any(w in text for w in ["sudden_attention", "look_up", "looking up", "tilts upward", "sky", "quick move", "turn"]):
        tags.append("突然抬头")
    if any(w in text for w in ["brush_inspection", "hide", "dry grass", "twigs", "hay", "straw", "brush", "foliage"]):
        tags.append("草堆/躲藏")
    if any(w in text for w in ["perch_or_climb", "perch", "climb", "window_watch", "window"]):
        tags.append("高处/窗边")
    if "catcam" in text:
        tags.append("CatCam新增素材")
    row["cat_tags"] = tags or ["低位观察"]
    base = safe_float(row.get("vlog_fit")) + safe_float(row.get("diary_fit")) + safe_float(row.get("comic_fit"))
    bonus = 0.0
    bonus += 1.3 if "CatCam新增素材" in tags else 0.0
    bonus += 0.9 if "猎物注意" in tags else 0.0
    bonus += 0.7 if "远处有人" in tags else 0.0
    bonus += 0.6 if "草堆/躲藏" in tags else 0.0
    bonus += 0.5 if "碎石/地面" in tags else 0.0
    bonus += 0.5 if "高处/窗边" in tags else 0.0
    row["cat_score"] = base + bonus


def select(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    used: set[str] = set()
    video_counts: dict[str, int] = {}
    selected: list[dict[str, Any]] = []

    for beat in BEATS:
        best = None
        best_score = -999.0
        for row in rows:
            if row["segment_id"] in used:
                continue
            score = float(row["cat_score"])
            text = row_text(row)
            match_count = 0
            for keyword in beat["keywords"]:
                if keyword in text:
                    match_count += 1
                    score += 3.0
            if match_count == 0 and beat["key"] != "soft_ending":
                score -= 2.5
            score -= video_counts.get(row["video_id"], 0) * 0.8
            if score > best_score:
                best_score = score
                best = row
        if best:
            used.add(best["segment_id"])
            video_counts[best["video_id"]] = video_counts.get(best["video_id"], 0) + 1
            selected.append({"beat": beat, "row": best})

    return selected


def public(item: dict[str, Any]) -> dict[str, Any]:
    row, beat = item["row"], item["beat"]
    return {
        "section": beat["section"],
        "caption": beat["caption"],
        "segment_id": row["segment_id"],
        "video_id": row["video_id"],
        "video_name": row.get("video_name_clean", ""),
        "start": row["start"],
        "end": row["end"],
        "cat_tags": " | ".join(row["cat_tags"]),
        "scene": row.get("scene", ""),
        "subjects": row.get("visible_subjects", ""),
        "action": row.get("pet_action", ""),
        "event": row.get("pet_event", ""),
        "why_memorable": row.get("why_memorable", ""),
        "evidence_frame": row.get("primary_comic_frame", ""),
        "source_path": row.get("source_path", ""),
    }


def write_diary(path: Path, selected: list[dict[str, Any]]) -> None:
    pieces = {item["beat"]["key"]: item for item in selected}
    text = f"""# 今天，地面把秘密递给了我

今天我出门的时候，没有宣布。猫做重要的事通常不宣布。我先让镜头贴近地面，让草尖、土块和远处人的脚步自己出现。地上有黑白的纹路，像一张没有人类标注的地图；我从里面挑了一条只有胡须知道的路，轻轻往前走。

我经过田地和草坡的时候，远处有人在移动，天空很亮，地面却更会说话。那些一行一行的泥土和植物把路线铺开，我把身体放低，像把自己折进影子里。人类看见的也许只是晃动的画面，我看见的是风从哪里来、谁刚刚踩过、哪一块地方不该久留。

然后，落叶那边动了一下。很小，很快，像一句话只说了半个字。我没有马上扑过去，只把注意力推到前面：树根、石头、枯叶、草堆，每一样都可能在替那个小影子打掩护。狗会把谜题追成一阵风，我更喜欢先把谜题盯到不好意思。

有一刻我突然抬头，看到柱子、树影、建筑和发白的天。上面也有消息。猫不能只读地面，高处负责藏声音，开阔地负责暴露位置，所以我看一眼就继续走，沿着边界、阴影和草边，把自己放在最不容易被世界发现的位置。

后来我靠近干草和枯枝。那里有沙沙声，有被碰过的痕迹，也有那种“看不清但肯定有东西”的黑影。我只靠近一点，再靠近一点，把爪子放到秘密门缝旁边。答案没有立刻出来，但我不急。耐心是猫随身带着的工具，比项圈还可靠。

今天的高光不是大声发生的。它们只是远处的人、田垄的线、落叶里的小动作、突然抬起的头、草堆里躲着的答案，还有我几乎没有发出声音的脚步。等人类回放这段视频时，也许终于会明白：我的一天不是散步，是一场低处侦探工作。
"""
    path.write_text(text, encoding="utf-8")


def write_evidence(path: Path, selected: list[dict[str, Any]]) -> None:
    lines = ["# Cat POV Diary Evidence v2", ""]
    for item in selected:
        row, beat = item["row"], item["beat"]
        lines.append(f"- {beat['section']} | {row['segment_id']} | {fmt(row['start'])}-{fmt(row['end'])} | {row.get('pet_event', '')}")
        lines.append(f"  - scene: {row.get('scene', '')}")
        lines.append(f"  - why: {row.get('why_memorable', '')}")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_comic_brief(path: Path, selected: list[dict[str, Any]]) -> None:
    prompt = """Create a square 6-panel Looki-like hand-drawn comic page based on the attached real cat POV reference board. Redraw the real scenes, do not use a photo filter and do not invent unrelated scenes. Keep the real evidence recognizable: low black-and-white cat-mounted camera, field/soil rows, distant humans, leaf-covered slope, tiny prey movement, sudden upward attention to post/sky/building, brush and hay close-up. Style: polished soft digital watercolor, clean black gutters, expressive line art, cinematic shadows, gentle suspense, slightly whimsical cat imagination. Add subtle whisker radar, scent trails, paw-map marks, ear-alert marks, and small blank thought bubbles. No readable text, no logos, no watermark."""
    lines = [
        "# Cat POV Comic Brief v2",
        "",
        "Goal: Looki-like grounded redraw. The panel layout must be based on real keyframes, with only small imaginative additions.",
        "",
        "## Panel Evidence",
        "",
    ]
    for i, item in enumerate(selected[:6], 1):
        row, beat = item["row"], item["beat"]
        lines.append(f"{i}. {beat['section']} | {beat['caption']} | evidence: {row['segment_id']} | frame: {row.get('primary_comic_frame', '')}")
        lines.append(f"   scene: {row.get('scene', '')}")
    lines.extend(["", "## Image Generation Prompt", "", "```text", prompt, "```"])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_reference_board(path: Path, selected: list[dict[str, Any]]) -> None:
    w, h = 1600, 1120
    canvas = Image.new("RGB", (w, h), (244, 239, 230))
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 28), "AUREN Cat POV v2 comic reference: redraw real scenes", font=font(38, True), fill=(26, 24, 22))
    draw.text((40, 76), "Use these keyframes as grounding. Keep events/composition recognizable; add only subtle cat imagination.", font=font(22), fill=(78, 70, 62))
    boxes = [
        (40, 126, 470, 270),
        (565, 126, 470, 270),
        (1090, 126, 470, 270),
        (40, 548, 470, 270),
        (565, 548, 470, 270),
        (1090, 548, 470, 270),
    ]
    for i, (item, box) in enumerate(zip(selected, boxes), 1):
        row, beat = item["row"], item["beat"]
        x, y, bw, bh = box
        img = Image.open(row["primary_comic_frame"]).convert("RGB")
        img = fit_cover(img, bw, bh)
        canvas.paste(img, (x, y))
        draw.rectangle([x, y, x + bw, y + bh], outline=(23, 23, 23), width=4)
        draw.rounded_rectangle([x + 12, y + 12, x + 68, y + 66], radius=18, fill=(255, 250, 218), outline=(23, 23, 23), width=3)
        draw.text((x + 33, y + 21), str(i), font=font(26, True), fill=(20, 20, 20))
        draw.text((x, y + bh + 12), f"{beat['section']} | {beat['caption']}", font=font(24, True), fill=(30, 28, 24))
        draw.text((x, y + bh + 46), wrap(row.get("scene", ""), 48), font=font(18), fill=(82, 76, 68))
    notes = [
        "Cat redraw rules:",
        "Preserve real POV composition; do not replace with generic cute cat scenes.",
        "Make low-resolution grayscale evidence readable through polished illustration.",
        "Imagination layer: whisker radar, scent trails, paw-map marks, ear-alert marks.",
    ]
    yy = 940
    for note in notes:
        draw.text((40, yy), note, font=font(25, True) if note.endswith(":") else font(22), fill=(30, 28, 24))
        yy += 35
    canvas.save(path, quality=94)


def write_vlog_plan(path: Path, selected: list[dict[str, Any]]) -> None:
    lines = ["# Cat POV Vlog Plan v2", "", "片名：地面把秘密递给了我", ""]
    lines.append("剪辑逻辑：猫 POV 不追求狗狗式外放热闹，而是低机位侦查、停顿、突然抬头、草丛线索和安静收束。")
    lines.append("")
    for item in selected:
        row, beat = item["row"], item["beat"]
        lines.append(f"- {beat['section']} | {row['segment_id']} | {fmt(row['start'])}-{fmt(row['end'])} | {beat['caption']}")
        lines.append(f"  - action/event: {row.get('pet_action', '')} / {row.get('pet_event', '')}")
    path.write_text("\n".join(lines), encoding="utf-8")


def render_vlog(out: Path, selected: list[dict[str, Any]], bgm: Path | None) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg:
        return
    clip_dir = out / "cat_vlog_clips_v2"
    overlay_dir = out / "cat_vlog_overlays_v2"
    clip_dir.mkdir(exist_ok=True)
    overlay_dir.mkdir(exist_ok=True)
    clips: list[Path] = []
    for i, item in enumerate(selected, 1):
        row, beat = item["row"], item["beat"]
        src = Path(row["source_path"])
        if not src.exists():
            continue
        overlay = overlay_dir / f"ov_{i:02d}.png"
        make_overlay(overlay, beat["section"], beat["caption"])
        out_clip = clip_dir / f"{i:02d}_{row['segment_id']}.mp4"
        start = float(row["start"])
        dur = max(1.1, min(4.0, float(row["end"]) - float(row["start"])))
        vf = "[0:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,eq=contrast=1.08:brightness=0.02[v0];[v0][1:v]overlay=0:0:shortest=1,fps=30,format=yuv420p[v]"
        has_audio = source_has_audio(ffprobe, src) if ffprobe else bool(row.get("has_audio"))
        if has_audio:
            cmd = [
                ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", str(src),
                "-loop", "1", "-t", f"{dur:.2f}", "-i", str(overlay),
                "-filter_complex", vf, "-map", "[v]", "-map", "0:a:0",
                "-af", "volume=0.82,aresample=44100,aformat=channel_layouts=stereo",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", str(out_clip),
            ]
        else:
            cmd = [
                ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", str(src),
                "-loop", "1", "-t", f"{dur:.2f}", "-i", str(overlay),
                "-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-filter_complex", vf, "-map", "[v]", "-map", "2:a:0",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", str(out_clip),
            ]
        subprocess.run(cmd, check=False)
        if out_clip.exists():
            clips.append(out_clip)

    make_contact_sheet(out / "cat_vlog_contact_sheet_v2.jpg", selected)
    concat = out / "cat_vlog_concat_v2.txt"
    concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in clips), encoding="utf-8")
    no_bgm = out / "cat_vlog_no_bgm_v2.mp4"
    subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", str(no_bgm)], check=False)
    final = out / "cat_vlog_story_v2.mp4"
    if bgm and bgm.exists() and no_bgm.exists():
        subprocess.run([
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(no_bgm), "-stream_loop", "-1", "-i", str(bgm),
            "-filter_complex", "[0:a]volume=0.62[a0];[1:a]volume=0.22,afade=t=in:st=0:d=1.0[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=1[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(final),
        ], check=False)
    elif no_bgm.exists():
        shutil.copy2(no_bgm, final)


def source_has_audio(ffprobe: str | None, src: Path) -> bool:
    if not ffprobe:
        return False
    result = subprocess.run([
        ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(src),
    ], capture_output=True, text=True, check=False)
    return bool(result.stdout.strip())


def make_overlay(path: Path, section: str, caption: str) -> None:
    img = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([44, 42, 280, 94], radius=16, fill=(0, 0, 0, 126))
    draw.text((64, 53), section, font=font(28, True), fill=(255, 255, 255, 238))
    draw.rounded_rectangle([70, 578, 1210, 680], radius=28, fill=(0, 0, 0, 142))
    draw.text((100, 604), caption, font=font(44, True), fill=(255, 255, 255, 248))
    img.save(path)


def make_contact_sheet(path: Path, selected: list[dict[str, Any]]) -> None:
    w, h = 1500, 940
    canvas = Image.new("RGB", (w, h), (246, 241, 232))
    draw = ImageDraw.Draw(canvas)
    draw.text((36, 28), "AUREN Cat POV v2 vlog sequence", font=font(34, True), fill=(28, 26, 23))
    boxes = [(36, 92, 330, 190), (400, 92, 330, 190), (764, 92, 330, 190), (1128, 92, 330, 190),
             (36, 490, 330, 190), (400, 490, 330, 190), (764, 490, 330, 190), (1128, 490, 330, 190)]
    for i, (item, box) in enumerate(zip(selected, boxes), 1):
        row, beat = item["row"], item["beat"]
        x, y, bw, bh = box
        img = Image.open(row["primary_comic_frame"]).convert("RGB")
        img = fit_cover(img, bw, bh)
        canvas.paste(img, (x, y))
        draw.rectangle([x, y, x + bw, y + bh], outline=(45, 42, 38), width=3)
        draw.text((x, y + bh + 12), f"{i}. {beat['section']}  {row['segment_id']}", font=font(20, True), fill=(30, 28, 24))
        draw.text((x, y + bh + 40), wrap(beat["caption"], 24), font=font(20), fill=(84, 76, 68))
    canvas.save(path, quality=93)


def write_review(path: Path, rows: list[dict[str, Any]], selected: list[dict[str, Any]]) -> None:
    source_counts: dict[str, int] = {}
    for item in selected:
        name = item["row"].get("video_name_clean", "")
        source_counts[name] = source_counts.get(name, 0) + 1
    lines = [
        "# Cat POV Self Evaluation v2",
        "",
        "## What improved",
        "",
        f"- Processed {len(rows)} VLM-reviewed candidates and selected {len(selected)} cat-specific highlights.",
        "- Added longer CatCam clips, which improved ground patrol, distant human, field-line, and low movement examples.",
        "- Selection is now beat-based and dynamic instead of pinned to one old sample id list.",
        "- Vlog rendering handles no-audio scientific clips by creating silent beds before mixing BGM.",
        "",
        "## Selected source mix",
        "",
    ]
    for name, count in sorted(source_counts.items()):
        lines.append(f"- {name}: {count} highlights")
    lines.extend([
        "",
        "## Remaining limitations",
        "",
        "- CatCam is low-resolution grayscale and academic-use-only, so it is good for local validation but not for MIT example media.",
        "- The wearer is not visible in most frames; model prompts must infer cat POV from source context and camera height.",
        "- More modern cat collar-cam footage with indoor shelves, owner calls, meows, bells, windows, and color night scenes is still needed.",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_readme(path: Path) -> None:
    lines = [
        "# AUREN Cat POV Eval 002",
        "",
        "Local evaluation using Wikimedia Commons cat POV clips plus two Zenodo CatCam segments.",
        "",
        "Important license note: CatCam is academic-use-only / CC BY-NC, so these derived visual assets should stay local unless a compatible license is obtained.",
        "",
        "Outputs:",
        "",
        "- `cat_diary_story_v2.md`: one continuous first-person cat diary.",
        "- `cat_pov_highlights_v2.csv/json`: recognition table and cat-specific labels.",
        "- `cat_comic_reference_real_scenes_v2.jpg`: real-scene grounding board for Looki-like redraw.",
        "- `cat_comic_brief_v2.md`: grounded comic prompt and panel evidence.",
        "- `cat_vlog_story_v2.mp4`: short narrative cat POV vlog.",
        "- `cat_pov_self_evaluation_v2.md`: self-evaluation and limitations.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def fit_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    scale = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
    left = (img.width - w) // 2
    top = (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))


def wrap(text: str, width: int) -> str:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        if len(cur) + len(word) + 1 > width:
            if cur:
                lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines[:3])


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


def fmt(v: Any) -> str:
    sec = int(float(v))
    return f"00:{sec:02d}"


if __name__ == "__main__":
    main()
