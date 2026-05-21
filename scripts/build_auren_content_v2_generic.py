#!/usr/bin/env python3
"""Build AUREN V2 diary, comic brief/page, storyboard, and vlog from VLM rows.

This generator treats MiniMax VLM rows as recognition evidence. It does not use
the older coarse category labels, because those labels were good enough for
pipeline smoke tests but too lossy for diary/comic/vlog decisions.
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
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


W, H = 1280, 720


BEATS: list[dict[str, Any]] = [
    {
        "key": "leave_home",
        "section": "出门动员",
        "caption": "门开了，我还在认真考虑。",
        "diary_title": "门一开，风先报名",
        "diary_text": "一开始我其实没有那么想出门。门口亮得像一块刚拆封的饼干，人类站在那里，另一只小伙伴已经迈出去半步。我决定先跟上，毕竟如果世界真的有事找我，我不能让它等太久。",
        "preferred_ids": ["pov_007_s0002"],
        "target_video": "pov_007",
        "keywords": ["entrance", "house", "door", "patio", "owner", "exiting"],
    },
    {
        "key": "urban_walk",
        "section": "城市巡逻",
        "caption": "这只白色轮子，值得跟踪。",
        "diary_title": "滨江广场的低空侦察",
        "diary_text": "到了滨江，地面突然变得很宽。人类只看见楼和太阳，我看见的是鞋、轮子、影子和每一块石砖之间的情报。那只白色小推车轮子滚得很稳，我跟在后面，像在追踪一只圆圆的城市生物。",
        "preferred_ids": ["pov_001_s0005", "pov_001_s0002", "pov_001_s0008"],
        "target_video": "pov_001",
        "keywords": ["xuhui", "riverside", "urban", "plaza", "paved", "stroller", "pedestrians"],
    },
    {
        "key": "dog_meet",
        "section": "同伴社交",
        "caption": "等一下，你也是出来巡逻的吗？",
        "diary_title": "公共广场上的鼻尖会议",
        "diary_text": "半路我遇见了别的狗。人类打招呼靠嘴，我们打招呼靠更可靠的设备。大家凑近、转身、再确认一遍，三秒钟里交换了很多信息：吃过什么，去过哪里，今天心情是不是适合一起绕一圈。",
        "preferred_ids": ["pov_001_s0013", "pov_004_s0017", "pov_001_s0012"],
        "target_video": "",
        "keywords": ["dogs interacting", "another dog", "other dog", "husky", "social", "greeting", "sniffing around"],
    },
    {
        "key": "indoor_shop",
        "section": "室内探店",
        "caption": "人类的洞穴，灯很多，味道也很多。",
        "diary_title": "我闯进一间会发光的店",
        "diary_text": "后来我们进到一间很亮的室内空间。上面是灯，旁边是展示架，远处有人在聊天。我的头顶露出一点白毛，提醒大家这是正经的狗狗视察。店里没有草，但有很多人类留下的味道，我一边走一边给它们排队编号。",
        "preferred_ids": ["pov_008_s0010", "pov_008_s0006", "pov_008_s0004"],
        "target_video": "pov_008",
        "keywords": ["indoor", "store", "showroom", "gallery", "retail", "overhead lights", "wall displays"],
    },
    {
        "key": "grass_sniff",
        "section": "草地读信",
        "caption": "草丛今天留言很多。",
        "diary_title": "草地是一整面公告栏",
        "diary_text": "最重要的工作发生在草地。我把鼻子贴近叶子，读到昨晚的风、刚路过的脚步，还有一只陌生狗留下的签名。人类看见的是草，我看见的是一整面公告栏。读到一半，我抬头看天，确认世界还在原来的位置。",
        "preferred_ids": ["pov_002_s0019", "pov_002_s0031", "pov_002_s0013"],
        "target_video": "pov_002",
        "keywords": ["grass", "field", "dirt path", "plants", "sniff", "rural"],
    },
    {
        "key": "backyard",
        "section": "后院侦察",
        "caption": "围栏后面，一定藏着新地图。",
        "diary_title": "后院的墙和缝隙",
        "diary_text": "后院看起来普通，其实很有层次。水泥地、旧墙、木围栏，每一样都在说不同的事。我快步穿过去，又停在木头旁边看了一会儿。围栏后面也许没有宝藏，但没有检查过之前，谁也不能证明。",
        "preferred_ids": ["pov_005_s0011", "pov_005_s0012", "pov_005_s0004"],
        "target_video": "pov_005",
        "keywords": ["backyard", "patio", "concrete", "fence", "wall", "narrow", "wooden"],
    },
    {
        "key": "play_chase",
        "section": "草地追逐",
        "caption": "白色小伙伴启动，我也启动。",
        "diary_title": "草坪上的白色闪电",
        "diary_text": "然后草地上出现了一只白色小狗。它跑起来的时候，草都像被它叫醒了。我跟着它的方向转，镜头有点晃，但这很合理。快乐本来就不应该太稳。",
        "preferred_ids": ["pov_009_s0012", "pov_009_s0014", "pov_009_s0011"],
        "target_video": "pov_009",
        "keywords": ["white", "fluffy dog", "running", "playing", "jumping", "grass"],
    },
    {
        "key": "park_cart",
        "section": "湖畔聚会",
        "caption": "车、草、人类，全部要检查。",
        "diary_title": "湖畔聚会的巡检清单",
        "diary_text": "湖畔那边更热闹。有车，有人，有树，还有一只带着设备的黑狗。人类以为这是聚会，我认为这是巡检任务。我先检查小推车，再闻草地，最后确认队伍没有少员。",
        "preferred_ids": ["pov_006_s0020", "pov_006_s0017", "pov_006_s0025"],
        "target_video": "pov_006",
        "keywords": ["park", "field", "cart", "lake", "outing", "grass", "trees"],
    },
    {
        "key": "blossom_close",
        "section": "收尾回味",
        "caption": "把花、风和今天一起带回家。",
        "diary_title": "花树下面的收尾",
        "diary_text": "快结束时，我们路过开着粉色花的树。黑色小狗跑在前面，靴子踩过路边，我低头闻了最后一口草。今天的味道很多：城市石砖、室内灯光、草地、木围栏、湖边的风，还有同伴身上的快乐。",
        "preferred_ids": ["pov_006_s0027", "pov_006_s0025", "pov_006_s0020"],
        "target_video": "pov_006",
        "keywords": ["blossoming", "pink", "path", "black dog", "park", "slope"],
    },
    {
        "key": "funny_detour",
        "section": "彩蛋镜头",
        "caption": "等等，这位也装了第一视角？",
        "diary_title": "一个不太像狗的朋友",
        "diary_text": "还有一个小彩蛋：乡间小路上出现了一位很特别的第一视角选手。它抬头低头的节奏和我不太一样，头顶还自带红色标记。我暂时把它记进档案，分类为：会走路的早晨闹钟。",
        "preferred_ids": ["pov_002_s0033"],
        "target_video": "pov_002",
        "keywords": ["chicken", "beak", "farm", "countryside"],
        "comic_only": True,
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
    parser.add_argument("--comic-raw", default="")
    args = parser.parse_args()

    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(Path(args.manifest))
    rows = [enrich_row(r, manifest) for r in load_json(Path(args.results)) if r.get("parse_ok")]
    rows.sort(key=lambda r: r["base_score"], reverse=True)

    selected = select_story(rows)
    vlog_clips = [b for b in selected if not b["beat"].get("comic_only")]
    comic_beats = selected[:]

    write_json(out / "recognition_highlights_v2.json", [public_row(x) for x in selected])
    write_csv(out / "recognition_highlights_v2.csv", [public_row(x) for x in selected])
    write_diary(out / "pet_diary_story_v2.md", selected)
    write_diary_evidence(out / "pet_diary_evidence_v2.md", selected)
    write_json(out / "pet_diary_story_v2.json", build_diary_payload(selected))
    write_comic_files(out, comic_beats)
    write_vlog_plan(out / "pet_pov_vlog_plan_v2.json", vlog_clips)
    write_vlog_plan_md(out / "pet_pov_vlog_plan_v2.md", vlog_clips)
    write_dashboard(out / "storyboard_dashboard_v2.html", selected)
    write_frame_comic(out / "comic_page_frame_based_fallback.jpg", comic_beats[:6])

    comic_raw = Path(args.comic_raw).resolve() if args.comic_raw else None
    if comic_raw and comic_raw.exists():
        caption_comic(comic_raw, out / "comic_page_looki_captioned.jpg")

    bgm = Path(args.bgm).resolve() if args.bgm else None
    render_vlog(out, vlog_clips, bgm if bgm and bgm.exists() else None)
    write_readme(out / "README.md")
    print(f"Done: {out}")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def enrich_row(row: dict[str, Any], manifest: dict[str, dict[str, str]]) -> dict[str, Any]:
    row = dict(row)
    meta = manifest.get(row.get("video_id", ""), {})
    row["source_path"] = meta.get("path", "")
    row["video_width"] = int(float(meta.get("width") or 0))
    row["video_height"] = int(float(meta.get("height") or 0))
    row["video_name_clean"] = meta.get("name", row.get("video_name", ""))
    text = " ".join(
        str(row.get(k, ""))
        for k in [
            "scene",
            "visible_subjects",
            "pet_action",
            "pet_event",
            "description",
            "why_memorable",
            "corrections_to_v2",
            "v2_scene",
            "v2_action",
            "v2_event",
        ]
    ).lower()
    row["_text"] = text
    row["detected_tags"] = detect_tags(text)
    row["base_score"] = (
        fnum(row.get("vlog_fit")) * 1.2
        + fnum(row.get("diary_fit")) * 1.15
        + fnum(row.get("comic_fit")) * 1.1
        + fnum(row.get("v2_vlog_score")) / 30
        + fnum(row.get("v2_diary_score")) / 32
        + fnum(row.get("v2_comic_score")) / 34
    )
    return row


def detect_tags(text: str) -> list[str]:
    rules = {
        "城市/滨江": ["xuhui", "riverside", "urban plaza", "public plaza", "paved walkway", "stroller", "pedestrian"],
        "室内/商店": ["indoor", "store", "showroom", "gallery", "retail", "overhead lights", "wall displays"],
        "草地嗅闻": ["grass", "grassy", "field", "dirt path", "plants", "sniffing the grass", "rural"],
        "后院/围栏": ["backyard", "concrete patio", "wooden fencing", "picket fence", "weathered wall", "stone wall", "narrow path", "wooden structure"],
        "同伴互动": ["dogs interacting", "another dog", "other dog", "husky", "white dog", "playing", "running"],
        "主人/出门": ["owner", "entrance", "house", "screen-covered doorway", "doorway", "exiting"],
        "湖畔/公园": ["lake", "park", "cart", "blossoming", "trees", "outing"],
        "彩蛋/农场": ["chicken", "beak", "farm", "countryside"],
    }
    tags = [tag for tag, words in rules.items() if any(w in text for w in words)]
    return tags or ["新场景探索"]


def select_story(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {r["segment_id"]: r for r in rows}
    used: set[str] = set()
    selected: list[dict[str, Any]] = []
    for beat in BEATS:
        row = None
        for sid in beat.get("preferred_ids", []):
            if sid in by_id and sid not in used:
                row = by_id[sid]
                break
        if row is None:
            candidates = sorted(rows, key=lambda r: beat_score(r, beat, used), reverse=True)
            row = candidates[0] if candidates else None
        if not row:
            continue
        used.add(row["segment_id"])
        selected.append({"beat": beat, "row": row})
    return selected


def beat_score(row: dict[str, Any], beat: dict[str, Any], used: set[str]) -> float:
    text = row["_text"]
    score = row["base_score"]
    if row["segment_id"] in used:
        score -= 100
    target_video = beat.get("target_video")
    if target_video and row.get("video_id") == target_video:
        score += 8
    score += sum(4 for kw in beat.get("keywords", []) if kw.lower() in text)
    return score


def public_row(item: dict[str, Any]) -> dict[str, Any]:
    beat, row = item["beat"], item["row"]
    return {
        "beat_key": beat["key"],
        "section": beat["section"],
        "segment_id": row["segment_id"],
        "video_id": row["video_id"],
        "video_name": row.get("video_name_clean", ""),
        "start": row["start"],
        "end": row["end"],
        "detected_tags": " | ".join(row.get("detected_tags", [])),
        "scene": row.get("scene", ""),
        "visible_subjects": row.get("visible_subjects", ""),
        "pet_action": row.get("pet_action", ""),
        "pet_event": row.get("pet_event", ""),
        "vlog_fit": row.get("vlog_fit", ""),
        "diary_fit": row.get("diary_fit", ""),
        "comic_fit": row.get("comic_fit", ""),
        "caption": beat["caption"],
        "source_path": row.get("source_path", ""),
        "strip": row.get("strip", ""),
        "primary_comic_frame": row.get("primary_comic_frame", ""),
    }


def build_diary_payload(selected: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "title": "今天我把世界闻成了一张地图",
        "voice": "curious pet POV, funny but grounded in recognized events",
        "beats": [
            {
                "time": idx + 1,
                "title": item["beat"]["diary_title"],
                "text": item["beat"]["diary_text"],
                "evidence": public_row(item),
            }
            for idx, item in enumerate(selected)
            if not item["beat"].get("comic_only")
        ],
    }


def write_diary(path: Path, selected: list[dict[str, Any]]) -> None:
    payload = build_diary_payload(selected)
    beat_texts = [beat["text"] for beat in payload["beats"]]
    lines = [
        "# 今天我把世界闻成了一张地图",
        "",
        "我今天差点以为自己只是出去散步。",
        "",
        "事实证明，这个判断太保守了。门一开，风先冲进来，亮光铺在门口，人类站在外面，像在宣布一项重要任务。我看了看同伴，又看了看门外，决定勉强配合一下。毕竟世界那么大，万一它真的藏了好闻的东西呢？ "
        + " ".join(beat_texts[:3]),
        "",
        " ".join(beat_texts[3:6]),
        "",
        " ".join(beat_texts[6:]),
        "",
        "最后我把今天收进鼻子里：滨江石砖的热气、推车轮子的橡胶味、商店里明亮又陌生的空气、草叶上的留言、后院木围栏的旧味道、同伴跑过草地时扬起来的快乐，还有湖畔风里一点点聚会的声音。",
        "",
        "人类说这是一天的素材。我说，这是我的地图。明天如果还开门，我可以继续负责检查。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_diary_evidence(path: Path, selected: list[dict[str, Any]]) -> None:
    lines = ["# 宠物日记素材证据", ""]
    for item in selected:
        if item["beat"].get("comic_only"):
            continue
        r = item["row"]
        lines.append(
            f"- {item['beat']['section']}｜{r['segment_id']}｜{fmt(fnum(r['start']))}-{fmt(fnum(r['end']))}｜{r.get('pet_event', '')}"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_comic_files(out: Path, selected: list[dict[str, Any]]) -> None:
    panels = []
    for idx, item in enumerate(selected[:6], 1):
        row = item["row"]
        panels.append(
            {
                "panel": idx,
                "caption": item["beat"]["caption"],
                "event": item["beat"]["diary_title"],
                "visual_prompt": comic_panel_prompt(item),
                "evidence_segment": row["segment_id"],
                "evidence_frame": row.get("primary_comic_frame", ""),
            }
        )
    write_json(out / "comic_panels_v2.json", panels)
    prompt = build_comic_prompt(panels)
    (out / "comic_minimax_prompt_v2.txt").write_text(prompt, encoding="utf-8")

    lines = [
        "# AUREN 生成式漫画 Brief V2",
        "",
        "目标是 Looki 类的事件改编漫画：用真实高光做骨架，用宠物视角做想象，不把视频帧直接拼成漫画。",
        "",
        "## 六格事件",
        "",
    ]
    for p in panels:
        lines.append(f"{p['panel']}. {p['event']}｜{p['caption']}｜证据：{p['evidence_segment']}")
    lines.extend(["", "## MiniMax 图像生成 Prompt", "", "```text", prompt, "```"])
    (out / "comic_brief_looki_style.md").write_text("\n".join(lines), encoding="utf-8")
    write_comic_storyboard_html(out / "comic_storyboard_v2.html", panels)
    write_comic_grounding_plan(out / "comic_grounded_workflow_v2.md", panels)


def comic_panel_prompt(item: dict[str, Any]) -> str:
    beat, row = item["beat"], item["row"]
    tag_text = ", ".join(row.get("detected_tags", []))
    return (
        f"{beat['section']}: {row.get('scene', '')}; subjects: {row.get('visible_subjects', '')}; "
        f"action: {row.get('pet_action', '')}; tags: {tag_text}; pet imagination: {beat['caption']}"
    )


def write_comic_grounding_plan(path: Path, panels: list[dict[str, Any]]) -> None:
    lines = [
        "# 漫画生成链路说明",
        "",
        "当前 demo 的漫画页是事件改编，不是严格转绘。流程是：视频高光片段 -> 关键帧 -> VLM 识别场景/主体/动作/事件 -> 六格文字分镜 -> 文生图生成整页漫画 -> 本地叠加中文对白。",
        "",
        "这个逻辑能验证“高光变成漫画故事”的方向，但不能保证画面忠实，因为文生图会重新想象狗、场景、构图和物体。你说得对，只靠文字描述生图，漫画就可能不反映真实素材。",
        "",
        "更适合 AUREN 的产品级链路应该是：",
        "",
        "1. 每格先绑定一个 evidence frame 或 1-3 张连续证据帧。",
        "2. 对证据帧做主体/场景 mask：狗、主人、其他狗、推车、草地、室内店铺、围栏等。",
        "3. 用图生图或带结构控制的模型重绘，而不是纯文生图；保留原始构图、主体位置和关键物体。",
        "4. 用同一只宠物的参考图做角色一致性约束，避免每格变成不同的狗。",
        "5. 只把想象元素作为叠加层加入，例如气味轨迹、想法泡泡、小地图符号，而不替换真实事件。",
        "6. 最后本地排版对白和字幕，避免图像模型生成乱码文字。",
        "",
        "本次六格绑定的真实证据如下：",
        "",
    ]
    for p in panels:
        lines.append(f"- Panel {p['panel']}｜{p['caption']}｜{p['evidence_segment']}｜{p['evidence_frame']}")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_comic_prompt(panels: list[dict[str, Any]]) -> str:
    panel_text = (
        "Panel 1: reluctant dog at doorway, owner outside, morning light. "
        "Panel 2: low dog POV chasing a white stroller wheel on Xuhui riverside plaza. "
        "Panel 3: two dogs greeting nose-to-nose in a public square. "
        "Panel 4: bright indoor shop or gallery from dog-eye view, overhead lights and people. "
        "Panel 5: dog nose reading grass like a message board, visible colorful scent trails. "
        "Panel 6: backyard fence or park ending, dog imagining a small map of today's smells. "
    )
    return (
        "Square 6-panel narrative comic page, warm modern webcomic, soft watercolor slice-of-life style. "
        "Main character: small curious dog wearing tiny POV camera. Real dog-day events plus gentle imagination: "
        "scent trails, tiny map icons, motion swooshes, blank thought bubbles. Clean black gutters, varied panel "
        "sizes, painterly line art, warm pastel colors, expressive pet body language. No readable text, no letters, "
        "no watermark. "
        + panel_text
    )


def write_comic_storyboard_html(path: Path, panels: list[dict[str, Any]]) -> None:
    cards = []
    for p in panels:
        img = Path(p["evidence_frame"]).as_posix()
        cards.append(
            f"<section><img src=\"{html.escape(img)}\"><h2>{p['panel']}. {html.escape(p['caption'])}</h2>"
            f"<p>{html.escape(p['visual_prompt'])}</p></section>"
        )
    page = f"""<!doctype html><meta charset="utf-8"><title>AUREN Comic Storyboard V2</title>
<style>
body{{margin:0;background:#f6f0e7;color:#1d1b18;font-family:"Microsoft YaHei",Arial,sans-serif}}
main{{max-width:1180px;margin:auto;padding:28px}}h1{{margin:0 0 8px;font-size:30px}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}section{{background:#fff;padding:10px;border:2px solid #111;box-shadow:4px 4px 0 #111}}
img{{width:100%;aspect-ratio:16/9;object-fit:cover}}h2{{font-size:18px;margin:9px 0 4px}}p{{font-size:13px;line-height:1.45;color:#555}}
</style><main><h1>AUREN 漫画分镜 V2</h1><p>这是生成式漫画的事件骨架和证据帧，最终漫画由图像模型重绘。</p><div class="grid">{''.join(cards)}</div></main>"""
    path.write_text(page, encoding="utf-8")


def write_vlog_plan(path: Path, selected: list[dict[str, Any]]) -> None:
    by_key = {x["beat"]["key"]: x for x in selected}
    sections = [
        {
            "section": "开篇高光",
            "description": "用 0.9 秒快切先展示出门、同伴、草地、湖畔，给观众一个宠物 POV 的节奏入口。",
            "keys": ["leave_home", "dog_meet", "play_chase", "park_cart"],
            "duration": 0.9,
            "montage": True,
        },
        {
            "section": "城市到室内",
            "description": "从滨江低空巡逻切到室内探店，强调宠物看到的世界和人类不同。",
            "keys": ["urban_walk", "dog_meet", "indoor_shop"],
            "duration": 3.8,
            "montage": False,
        },
        {
            "section": "气味地图",
            "description": "草地嗅闻和后院侦察构成中段的探索逻辑。",
            "keys": ["grass_sniff", "backyard"],
            "duration": 4.0,
            "montage": False,
        },
        {
            "section": "聚会和收尾",
            "description": "用草地追逐、湖畔巡检和花树收尾，把情绪从兴奋落回温暖。",
            "keys": ["play_chase", "park_cart", "blossom_close"],
            "duration": 3.7,
            "montage": False,
        },
    ]
    payload_sections = []
    for section in sections:
        clips = []
        for key in section["keys"]:
            item = by_key.get(key)
            if not item:
                continue
            row = item["row"]
            start = fnum(row["start"]) + (0.45 if section["montage"] else 0.05)
            end = min(fnum(row["end"]), start + section["duration"])
            clips.append(
                {
                    "segment_id": row["segment_id"],
                    "file": row["source_path"],
                    "start": round(start, 2),
                    "end": round(max(start + 0.5, end), 2),
                    "subtitle": item["beat"]["caption"],
                    "recognized_event": row.get("pet_event", ""),
                    "layout": "blur_backdrop" if is_vertical(row) else "fill_crop",
                }
            )
        payload_sections.append({k: section[k] for k in ["section", "description"]} | {"clips": clips})
    plan = {
        "title": "今天我把世界闻成了一张地图",
        "target_duration_s": 34,
        "sections": payload_sections,
        "bgm_suggestion": "playful indie folk and light city pop, curious dog adventure, acoustic guitar, soft piano, hand percussion, 100 bpm, warm and bright",
        "audio_notes": "保留原片环境声作为质感，压低到中低音量；BGM 做情绪主线，开篇快切更轻快，中后段更温暖。",
    }
    write_json(path, plan)


def write_vlog_plan_md(path: Path, selected: list[dict[str, Any]]) -> None:
    plan_path = path.with_suffix(".json")
    plan = load_json(plan_path)
    lines = ["# AUREN 宠物 POV Vlog 方案 V2", "", f"片名：{plan['title']}", ""]
    for sec in plan["sections"]:
        lines.extend([f"## {sec['section']}", "", sec["description"], ""])
        for c in sec["clips"]:
            lines.append(f"- {Path(c['file']).name}｜{fmt(c['start'])}-{fmt(c['end'])}｜{c['subtitle']}｜{c['layout']}")
        lines.append("")
    lines.extend(["## BGM", "", plan["bgm_suggestion"], "", "## 音频说明", "", plan["audio_notes"]])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_dashboard(path: Path, selected: list[dict[str, Any]]) -> None:
    rows = []
    for idx, item in enumerate(selected, 1):
        row = item["row"]
        strip = Path(row.get("strip", "")).as_posix()
        rows.append(
            f"<tr><td>{idx}</td><td>{html.escape(item['beat']['section'])}</td><td><img src=\"{html.escape(strip)}\"></td>"
            f"<td>{html.escape(row['segment_id'])}<br>{fmt(fnum(row['start']))}-{fmt(fnum(row['end']))}</td>"
            f"<td>{html.escape(' | '.join(row.get('detected_tags', [])))}</td>"
            f"<td>{html.escape(row.get('scene', ''))}</td><td>{html.escape(row.get('pet_action', ''))}</td>"
            f"<td>{html.escape(row.get('pet_event', ''))}</td><td>{html.escape(item['beat']['caption'])}</td></tr>"
        )
    page = f"""<!doctype html><meta charset="utf-8"><title>AUREN V2 Storyboard</title>
<style>
body{{margin:0;background:#101319;color:#e8edf5;font-family:"Microsoft YaHei",Arial,sans-serif}}
main{{padding:24px;max-width:1420px;margin:auto}}h1{{margin:0 0 8px}}p{{color:#9ba8b7}}
table{{width:100%;border-collapse:collapse;background:#151b24}}th,td{{border-bottom:1px solid #293241;padding:10px;text-align:left;vertical-align:top;font-size:14px}}
th{{background:#202938;position:sticky;top:0}}img{{width:250px;height:84px;object-fit:cover}}td:first-child{{color:#8fd0ff;font-weight:700}}
</style><main><h1>AUREN V2 分镜确认板</h1><p>每一行都是 VLM 识别证据、重新打标和内容用途的合并结果。</p><table><thead><tr><th>#</th><th>内容段落</th><th>证据帧</th><th>片段</th><th>重打标</th><th>场景</th><th>动作</th><th>事件</th><th>宠物字幕</th></tr></thead><tbody>{''.join(rows)}</tbody></table></main>"""
    path.write_text(page, encoding="utf-8")


def write_frame_comic(path: Path, selected: list[dict[str, Any]]) -> None:
    panels = selected[:6]
    panel_w, panel_h = 520, 360
    margin, gap = 28, 18
    page_w = margin * 2 + panel_w * 2 + gap
    page_h = margin * 2 + panel_h * 3 + gap * 2 + 54
    canvas = Image.new("RGB", (page_w, page_h), (246, 240, 230))
    draw = ImageDraw.Draw(canvas)
    title_font = font(28)
    cap_font = font(24)
    draw.text((margin, 12), "AUREN 漫画证据草图：供生成式重绘参考", fill=(25, 25, 25), font=title_font)
    top = margin + 42
    for idx, item in enumerate(panels):
        row, beat = item["row"], item["beat"]
        x = margin + (idx % 2) * (panel_w + gap)
        y = top + (idx // 2) * (panel_h + gap)
        draw.rectangle([x + 5, y + 5, x + panel_w + 5, y + panel_h + 5], fill=(20, 20, 20))
        draw.rectangle([x, y, x + panel_w, y + panel_h], fill=(255, 255, 255), outline=(20, 20, 20), width=4)
        img = Image.open(row["primary_comic_frame"]).convert("RGB")
        img = comic_filter(fit_cover(img, panel_w - 18, 268))
        canvas.paste(img, (x + 9, y + 9))
        draw.rounded_rectangle([x + 14, y + 288, x + panel_w - 14, y + 342], radius=16, fill=(255, 249, 196), outline=(25, 25, 25), width=2)
        draw.multiline_text((x + 28, y + 296), wrap(f"{idx + 1}. {beat['caption']}", 18), fill=(20, 20, 20), font=cap_font, spacing=5)
    canvas.save(path, quality=93)


def caption_comic(raw: Path, out: Path) -> None:
    captions = [b["caption"] for b in BEATS[:6]]
    img = Image.open(raw).convert("RGB")
    img = ImageOps.contain(img, (1024, 1024), method=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (1024, 1024), (246, 240, 230))
    canvas.paste(img, ((1024 - img.width) // 2, (1024 - img.height) // 2))
    draw = ImageDraw.Draw(canvas)
    cap_font = font(24)
    boxes = [
        (36, 36, 488, 88),
        (536, 36, 988, 88),
        (36, 368, 488, 420),
        (536, 368, 988, 420),
        (36, 706, 488, 758),
        (536, 706, 988, 758),
    ]
    for idx, (box, caption) in enumerate(zip(boxes, captions), 1):
        x1, y1, x2, y2 = box
        draw.rounded_rectangle(box, radius=18, fill=(255, 250, 214), outline=(25, 25, 25), width=2)
        draw.text((x1 + 14, y1 + 11), f"{idx}. {caption}", font=cap_font, fill=(20, 20, 20))
    canvas.save(out, quality=94)


def render_vlog(out: Path, selected: list[dict[str, Any]], bgm: Path | None) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return
    plan = load_json(out / "pet_pov_vlog_plan_v2.json")
    clip_dir = out / "vlog_v2_clips"
    overlay_dir = out / "vlog_v2_overlays"
    clip_dir.mkdir(exist_ok=True)
    overlay_dir.mkdir(exist_ok=True)
    row_by_id = {x["row"]["segment_id"]: x["row"] for x in selected}
    clips: list[Path] = []
    order = 0
    for sec in plan["sections"]:
        for clip in sec["clips"]:
            src = Path(clip["file"])
            row = row_by_id.get(clip["segment_id"])
            if not src.exists() or not row:
                continue
            order += 1
            dur = max(0.5, fnum(clip["end"]) - fnum(clip["start"]))
            overlay = overlay_dir / f"overlay_{order:02d}.png"
            make_overlay(overlay, sec["section"], clip["subtitle"], "开篇" in sec["section"])
            out_clip = clip_dir / f"{order:02d}_{clip['segment_id']}.mp4"
            vf = vertical_filter() if is_vertical(row) else horizontal_filter()
            af = f"volume=0.70,aresample=44100,aformat=channel_layouts=stereo,afade=t=in:st=0:d=0.08,afade=t=out:st={max(0.25, dur - 0.12):.2f}:d=0.12"
            cmd = [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{fnum(clip['start']):.2f}",
                "-t",
                f"{dur:.2f}",
                "-i",
                str(src),
                "-i",
                str(overlay),
                "-filter_complex",
                vf,
                "-map",
                "[v]",
                "-map",
                "0:a:0?",
                "-af",
                af,
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
                str(out_clip),
            ]
            subprocess.run(cmd, check=False)
            if out_clip.exists() and out_clip.stat().st_size > 0:
                clips.append(out_clip)
    if not clips:
        return
    concat = out / "vlog_v2_concat.txt"
    concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in clips), encoding="utf-8")
    no_bgm = out / "vlog_v2_no_bgm.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(no_bgm),
        ],
        check=False,
    )
    final = out / "vlog_v2_pet_pov_story.mp4"
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
                "[0:a]volume=0.90[a0];[1:a]volume=0.22,afade=t=in:st=0:d=1.0[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
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


def vertical_filter() -> str:
    return (
        "[0:v]split=2[bgsrc][fgsrc];"
        "[bgsrc]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
        "gblur=sigma=24,eq=brightness=-0.08:saturation=1.12[bg];"
        "[fgsrc]scale=720:720:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[v0];"
        "[v0][1:v]overlay=0:0,fps=30,format=yuv420p[v]"
    )


def horizontal_filter() -> str:
    return (
        "[0:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
        "fps=30,format=rgba[v0];[v0][1:v]overlay=0:0,format=yuv420p[v]"
    )


def make_overlay(path: Path, section: str, subtitle: str, montage: bool) -> None:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    label_font = font(28)
    sub_font = font(44 if not montage else 38)
    draw.rounded_rectangle([42, 42, 310 if montage else 260, 92], radius=16, fill=(0, 0, 0, 122))
    draw.text((62, 52), "高光快切" if montage else section, font=label_font, fill=(255, 255, 255, 238))
    wrapped = wrap(subtitle, 18)
    y = 574 if "\n" not in wrapped else 536
    draw.rounded_rectangle([64, y - 20, 1216, 682], radius=26, fill=(0, 0, 0, 132))
    draw.multiline_text((96, y), wrapped, font=sub_font, fill=(255, 255, 255, 248), spacing=8)
    img.save(path)


def write_readme(path: Path) -> None:
    lines = [
        "# AUREN POV Test 002 Content V2",
        "",
        "这一版从 9 条测试素材重新切片、识别、打标并生成内容资产。核心变化是：打标使用 VLM 识别字段重新归类， diary/comic/vlog 各自按不同内容逻辑选材。",
        "",
        "## 输出",
        "",
        "- `recognition_highlights_v2.csv/json`: 重新打标后的高光证据表。",
        "- `pet_diary_story_v2.md/json`: 完整宠物口吻日记。",
        "- `comic_brief_looki_style.md`: 生成式漫画 brief。",
        "- `comic_minimax_prompt_v2.txt`: 可直接给 MiniMax 图像模型的 prompt。",
        "- `comic_page_looki_captioned.jpg`: 如果已提供 MiniMax 原图，则为叠加中文对白后的漫画页。",
        "- `comic_page_frame_based_fallback.jpg`: 证据帧漫画化草图，仅用于兜底和核对，不作为最终漫画方案。",
        "- `pet_pov_vlog_plan_v2.md/json`: 叙事剪辑方案。",
        "- `storyboard_dashboard_v2.html`: 分镜确认页。",
        "- `vlog_v2_pet_pov_story.mp4`: 带字幕、原声和 BGM 的 vlog 成片。",
        "",
        "## 仍需产品化",
        "",
        "声音事件目前主要来自原片音轨和 VLM 对画面的解释，后续应接入 ASR/音频事件识别，区分主人说话、狗叫、风声、水声和环境音量变化；漫画要进一步加入角色一致性参考；vlog 可以继续增加可交互分镜确认和节拍对齐。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def is_vertical(row: dict[str, Any]) -> bool:
    return int(row.get("video_height") or 0) > int(row.get("video_width") or 0)


def fnum(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def wrap(text: str, width: int) -> str:
    chunks: list[str] = []
    current = ""
    for ch in text:
        current += ch
        if len(current) >= width:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return "\n".join(chunks[:2])


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in [Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/simhei.ttf"), Path("C:/Windows/Fonts/arial.ttf")]:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def fit_cover(img: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / img.width, height / img.height)
    resized = img.resize((math.ceil(img.width * scale), math.ceil(img.height * scale)), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def comic_filter(img: Image.Image) -> Image.Image:
    img = ImageEnhance.Color(img).enhance(1.25)
    img = ImageEnhance.Contrast(img).enhance(1.10)
    img = ImageOps.posterize(img, 5)
    return img.filter(ImageFilter.EDGE_ENHANCE)


if __name__ == "__main__":
    main()
