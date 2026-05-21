#!/usr/bin/env python3
"""Build cat-specific AUREN POV content outputs.

Cat POV footage is usually quieter and more predatory than dog POV footage.
This builder emphasizes observation, sudden attention, stalking, hiding, and
ground-level threshold crossing instead of dog-style social/running beats.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


BEATS = [
    {
        "key": "forest_scan",
        "ids": ["pov_001_s0001", "pov_001_s0002"],
        "section": "林地侦察",
        "caption": "地面先说话，我先不出声。",
    },
    {
        "key": "leaf_walk",
        "ids": ["pov_001_s0002", "pov_001_s0005"],
        "section": "落叶巡路",
        "caption": "落叶很吵，但我很轻。",
    },
    {
        "key": "prey_track",
        "ids": ["pov_001_s0003", "pov_002_s0003"],
        "section": "目标出现",
        "caption": "那边动了一下。",
    },
    {
        "key": "sudden_attention",
        "ids": ["pov_002_s0002"],
        "section": "突然抬头",
        "caption": "上面也有消息。",
    },
    {
        "key": "courtyard_cross",
        "ids": ["pov_002_s0003", "pov_002_s0004"],
        "section": "楼边穿行",
        "caption": "开阔地要快点过。",
    },
    {
        "key": "brush_watch",
        "ids": ["pov_003_s0002", "pov_003_s0004"],
        "section": "草堆盯梢",
        "caption": "草里面藏着答案。",
    },
    {
        "key": "nest_touch",
        "ids": ["pov_003_s0003", "pov_003_s0005"],
        "section": "巢边试探",
        "caption": "我只碰一下。",
    },
    {
        "key": "hidden_rustle",
        "ids": ["pov_003_s0005", "pov_003_s0004"],
        "section": "最后的沙沙声",
        "caption": "今天的线索，收进胡须。",
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
    rows = [enrich(r) for r in json.loads(Path(args.results).read_text(encoding="utf-8")) if r.get("parse_ok")]
    manifest = load_manifest(Path(args.manifest))
    for row in rows:
        meta = manifest.get(row["video_id"], {})
        row["source_path"] = meta.get("path", "")
        row["video_name_clean"] = meta.get("name", row.get("video_name", ""))
    selected = select(rows)
    write_json(out / "cat_pov_highlights_v1.json", [public(x) for x in selected])
    write_csv(out / "cat_pov_highlights_v1.csv", [public(x) for x in selected])
    write_diary(out / "cat_diary_story_v1.md", selected)
    write_evidence(out / "cat_diary_evidence_v1.md", selected)
    write_comic_brief(out / "cat_comic_brief_v1.md", selected)
    write_reference_board(out / "cat_comic_reference_real_scenes_v1.jpg", selected[:6])
    write_vlog_plan(out / "cat_vlog_plan_v1.md", selected)
    render_vlog(out, selected, Path(args.bgm) if args.bgm else None)
    write_review(out / "cat_pov_self_evaluation_v1.md", selected)
    write_readme(out / "README.md")
    print(f"Done: {out}")


def load_manifest(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def enrich(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    text = " ".join(str(row.get(k, "")) for k in ["scene", "visible_subjects", "pet_action", "pet_event", "why_memorable"]).lower()
    tags = []
    if any(w in text for w in ["forest", "wooded", "leaf", "rocky", "fallen logs"]):
        tags.append("林地/落叶")
    if any(w in text for w in ["small animal", "squirrel", "bird", "rodent", "tracking", "scurries"]):
        tags.append("猎物注意")
    if any(w in text for w in ["quick upward", "turn", "tilts upward", "post", "sky"]):
        tags.append("突然抬头")
    if any(w in text for w in ["grass", "vegetation", "brush", "hay", "straw", "foliage"]):
        tags.append("草丛/躲藏")
    if any(w in text for w in ["building", "courtyard", "paved", "slope"]):
        tags.append("建筑边界")
    row["cat_tags"] = tags or ["低位观察"]
    row["cat_score"] = float(row.get("vlog_fit") or 0) + float(row.get("diary_fit") or 0) + float(row.get("comic_fit") or 0)
    return row


def select(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {r["segment_id"]: r for r in rows}
    used = set()
    selected = []
    for beat in BEATS:
        row = None
        for sid in beat["ids"]:
            if sid in by_id and sid not in used:
                row = by_id[sid]
                break
        if row is None:
            row = max((r for r in rows if r["segment_id"] not in used), key=lambda r: r["cat_score"], default=None)
        if row:
            used.add(row["segment_id"])
            selected.append({"beat": beat, "row": row})
    return selected


def public(item: dict[str, Any]) -> dict[str, Any]:
    row, beat = item["row"], item["beat"]
    return {
        "section": beat["section"],
        "caption": beat["caption"],
        "segment_id": row["segment_id"],
        "video_id": row["video_id"],
        "start": row["start"],
        "end": row["end"],
        "cat_tags": " | ".join(row["cat_tags"]),
        "scene": row.get("scene", ""),
        "subjects": row.get("visible_subjects", ""),
        "action": row.get("pet_action", ""),
        "event": row.get("pet_event", ""),
        "evidence_frame": row.get("primary_comic_frame", ""),
        "source_path": row.get("source_path", ""),
    }


def write_diary(path: Path, selected: list[dict[str, Any]]) -> None:
    text = """# 今天，我把脚步藏了起来

今天我醒得很轻，轻到连落叶都不知道我已经开始工作了。

我先贴着地面走。狗会把世界撞开，我不会。我让胡须先出去，让耳朵竖起来，让每一片叶子自己交代它昨晚听见了什么。林地是黑白的，石头、树根和远处的房子都安静地摆在那里，像一张等我签字的地图。我没有急着跑，因为猫的速度不是给别人看的，是留给真正有动静的东西用的。

然后，那边动了一下。

我看见一个小影子从落叶和草坡之间掠过去。它不大，但足够让空气变紧。我把身体压低，眼睛往前，脚步往后藏。人类会说这是“追踪目标”，但我觉得更准确的说法是：世界突然把一行字写在地上，而我刚好读得懂。

有一瞬间，我抬头看见一根竖起来的东西和亮得发白的天空。上面也有消息。猫不能只看地面，地面负责留下痕迹，高处负责藏住声音。我停了一下，把耳朵转过去，又把注意力收回来。开阔地不能待太久，楼边、草边、阴影边，才是比较合理的位置。

后来我钻到草和枯枝旁边。那里有沙沙声，有干草被碰过的痕迹，还有一点点看不清的黑影。我没有冲进去。我只靠近一点，再靠近一点，像把爪子放在秘密的门缝上。草里面藏着答案，但答案不一定愿意马上出来。没关系，我有耐心。

最后我碰了一下那堆干草。真的，只碰一下。它动了，声音很小，但我的胡须听见了。今天的线索就到这里：落叶、石头、建筑边、草堆、一个跑得很快的小东西，还有我没有发出声音的脚步。

人类如果看这段视频，也许会觉得画面短、暗、晃、没有什么大事。

但猫知道，最重要的事情从来不是大声发生的。"""
    path.write_text(text, encoding="utf-8")


def write_evidence(path: Path, selected: list[dict[str, Any]]) -> None:
    lines = ["# Cat POV diary evidence", ""]
    for item in selected:
        row, beat = item["row"], item["beat"]
        lines.append(f"- {beat['section']} | {row['segment_id']} | {fmt(row['start'])}-{fmt(row['end'])} | {row.get('pet_event','')}")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_comic_brief(path: Path, selected: list[dict[str, Any]]) -> None:
    prompt = """Create a square 6-panel Looki-like hand-drawn comic page based on the cat POV evidence frames. Redraw, do not apply a photo filter. Keep the real events recognizable: monochrome low forest floor, leaf path, tiny prey movement, sudden upward attention to post/sky, crossing near buildings, brush pile and hay nest. Style: soft digital watercolor, clean black gutters, cinematic shadows, expressive cat-like low camera feeling, quiet suspense, a little whimsical imagination. Add only subtle scent lines, ear-alert marks, paw-map marks, and blank thought bubbles. No readable text, no logos, no watermark."""
    lines = [
        "# Cat POV comic brief",
        "",
        "This should be grounded redraw, not text-only invention and not a photo filter.",
        "",
        "## Panels",
        "",
    ]
    for i, item in enumerate(selected[:6], 1):
        row, beat = item["row"], item["beat"]
        lines.append(f"{i}. {beat['section']} | {beat['caption']} | evidence: {row['segment_id']} | frame: {row.get('primary_comic_frame','')}")
    lines.extend(["", "## Generation prompt", "", "```text", prompt, "```"])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_reference_board(path: Path, selected: list[dict[str, Any]]) -> None:
    w, h = 1500, 1060
    canvas = Image.new("RGB", (w, h), (244, 239, 230))
    draw = ImageDraw.Draw(canvas)
    draw.text((36, 24), "AUREN Cat POV comic reference: redraw these real scenes", font=font(34, True), fill=(28, 26, 23))
    draw.text((36, 68), "Use as scene/event grounding. Redraw in Looki-like illustration, not photo filter.", font=font(22), fill=(76, 70, 62))
    boxes = [(36, 120, 450, 250), (525, 120, 450, 250), (1014, 120, 450, 250), (36, 510, 450, 250), (525, 510, 450, 250), (1014, 510, 450, 250)]
    for i, (item, box) in enumerate(zip(selected, boxes), 1):
        row, beat = item["row"], item["beat"]
        x, y, bw, bh = box
        img = Image.open(row["primary_comic_frame"]).convert("RGB")
        img = fit_cover(img, bw, bh)
        canvas.paste(img, (x, y))
        draw.rectangle([x, y, x + bw, y + bh], outline=(25, 25, 25), width=4)
        draw.rounded_rectangle([x + 10, y + 10, x + 62, y + 58], radius=18, fill=(255, 250, 218), outline=(25, 25, 25), width=3)
        draw.text((x + 28, y + 17), str(i), font=font(24, True), fill=(25, 25, 25))
        draw.text((x, y + bh + 12), f"{i}. {beat['caption']} | {row['segment_id']}", font=font(23, True), fill=(30, 28, 24))
        draw.text((x, y + bh + 42), wrap(row.get("scene", ""), 45), font=font(18), fill=(82, 76, 68))
    notes = [
        "Cat-specific redraw notes:",
        "quiet observation, low ground, sudden attention, prey tracking, hiding, brush movement",
        "preserve the black-and-white field-study feeling but make it polished and readable",
        "imagination layer should be subtle: whisker radar, scent lines, paw-map marks",
    ]
    yy = 894
    for note in notes:
        draw.text((36, yy), note, font=font(25, True) if note.endswith(":") else font(22), fill=(30, 28, 24))
        yy += 34
    canvas.save(path, quality=94)


def write_vlog_plan(path: Path, selected: list[dict[str, Any]]) -> None:
    lines = ["# Cat POV Vlog Plan", "", "片名：我把脚步藏了起来", ""]
    lines.append("猫咪素材很短，因此剪辑目标不是狗狗式热闹 vlog，而是短促、安静、有悬念的观察片。")
    lines.append("")
    for item in selected:
        row, beat = item["row"], item["beat"]
        lines.append(f"- {beat['section']} | {row['segment_id']} | {fmt(row['start'])}-{fmt(row['end'])} | {beat['caption']}")
    path.write_text("\n".join(lines), encoding="utf-8")


def render_vlog(out: Path, selected: list[dict[str, Any]], bgm: Path | None) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return
    clip_dir = out / "cat_vlog_clips"
    overlay_dir = out / "cat_vlog_overlays"
    clip_dir.mkdir(exist_ok=True)
    overlay_dir.mkdir(exist_ok=True)
    clips = []
    for i, item in enumerate(selected, 1):
        row, beat = item["row"], item["beat"]
        src = Path(row["source_path"])
        if not src.exists():
            continue
        overlay = overlay_dir / f"ov_{i:02d}.png"
        make_overlay(overlay, beat["section"], beat["caption"])
        out_clip = clip_dir / f"{i:02d}_{row['segment_id']}.mp4"
        start = float(row["start"])
        dur = max(0.7, float(row["end"]) - float(row["start"]))
        vf = "[0:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,eq=contrast=1.08:brightness=0.02[v0];[v0][1:v]overlay=0:0,fps=30,format=yuv420p[v]"
        subprocess.run([
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", str(src), "-i", str(overlay),
            "-filter_complex", vf, "-map", "[v]", "-map", "0:a:0?",
            "-af", "volume=0.80,aresample=44100,aformat=channel_layouts=stereo",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", str(out_clip)
        ], check=False)
        if out_clip.exists():
            clips.append(out_clip)
    concat = out / "cat_vlog_concat.txt"
    concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in clips), encoding="utf-8")
    no_bgm = out / "cat_vlog_no_bgm.mp4"
    subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", str(no_bgm)], check=False)
    final = out / "cat_vlog_story_v1.mp4"
    if bgm and bgm.exists() and no_bgm.exists():
        subprocess.run([
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(no_bgm), "-stream_loop", "-1", "-i", str(bgm),
            "-filter_complex", "[0:a]volume=0.75[a0];[1:a]volume=0.18,afade=t=in:st=0:d=0.8[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=1[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(final)
        ], check=False)
    elif no_bgm.exists():
        shutil.copy2(no_bgm, final)


def make_overlay(path: Path, section: str, caption: str) -> None:
    img = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([44, 42, 260, 92], radius=16, fill=(0, 0, 0, 126))
    draw.text((64, 53), section, font=font(28), fill=(255, 255, 255, 238))
    draw.rounded_rectangle([70, 578, 1210, 680], radius=28, fill=(0, 0, 0, 138))
    draw.text((100, 604), caption, font=font(44, True), fill=(255, 255, 255, 248))
    img.save(path)


def write_review(path: Path, selected: list[dict[str, Any]]) -> None:
    lines = [
        "# Cat POV Self Evaluation",
        "",
        "## What worked",
        "",
        "- VLM correctly recognized the footage as low, monochrome animal POV in woodland/grass/building-edge settings.",
        "- Cat-specific highlights differ from dog highlights: quiet scanning, prey tracking, sudden upward attention, brush/nest investigation.",
        "- The diary reads as a quiet first-person cat narrative rather than a dog-style outing.",
        "",
        "## Limitations",
        "",
        "- Source material is only 3 clips x 5 seconds, 480x360, monochrome scientific footage.",
        "- VLM sometimes says dog/animal instead of cat because the wearer is not visible and the footage is old low-res grayscale.",
        "- Audio exists but is not semantically rich enough here; future cat workflow needs bell/meow/owner voice/prey sound classifiers.",
        "",
        "## Next optimization",
        "",
        "- Collect longer modern cat collar-cam samples with indoor shelves, windows, owner interaction, meow/bell audio, and outdoor stalking.",
        "- Add cat-specific label schema: stalk, perch, hide, window_watch, threshold_pause, sudden_attention, prey_track, owner_call.",
        "- Use image-reference grounded comic generation exactly as required for dog outputs.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_readme(path: Path) -> None:
    lines = [
        "# AUREN Cat POV Eval 001",
        "",
        "Source material: Wikimedia Commons CC BY 2.5 cat-mounted camera clips from Lesica et al. 2006 supplementary videos.",
        "",
        "Outputs:",
        "",
        "- `cat_diary_story_v1.md`: continuous first-person cat diary.",
        "- `cat_pov_highlights_v1.csv/json`: recognition and cat-specific labels.",
        "- `cat_comic_reference_real_scenes_v1.jpg`: real-scene grounding board for Looki-like redraw.",
        "- `cat_comic_brief_v1.md`: grounded comic prompt and panel evidence.",
        "- `cat_vlog_story_v1.mp4`: short narrative cat POV vlog.",
        "- `cat_pov_self_evaluation_v1.md`: self-evaluation and limitations.",
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


def fit_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    scale = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
    return img.crop(((img.width - w) // 2, (img.height - h) // 2, (img.width - w) // 2 + w, (img.height - h) // 2 + h))


def wrap(text: str, width: int) -> str:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        if len(cur) + len(word) + 1 > width:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines[:3])


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in [Path("C:/Windows/Fonts/msyhbd.ttc") if bold else Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simhei.ttf"), Path("C:/Windows/Fonts/arial.ttf")]:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def fmt(v: Any) -> str:
    sec = int(float(v))
    return f"00:{sec:02d}"


if __name__ == "__main__":
    main()
