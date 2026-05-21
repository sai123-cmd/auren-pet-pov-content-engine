#!/usr/bin/env python3
"""Run MiniMax image understanding over AUREN VLM jobs.

Reads MINIMAX_API_KEY from the process environment. The key is never written to
disk by this script.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=0.4)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise SystemExit("MINIMAX_API_KEY is required in environment")
    mmx = shutil.which("mmx") or shutil.which("mmx.cmd") or shutil.which("mmx.exe")
    if not mmx:
        raise SystemExit("mmx CLI not found")

    jobs = read_jsonl(Path(args.jobs))
    end = len(jobs) if args.limit <= 0 else min(len(jobs), args.start + args.limit)
    jobs = jobs[args.start:end]

    out_dir = Path(args.output_dir).resolve()
    raw_dir = out_dir / "raw"
    parsed_dir = out_dir / "parsed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True, exist_ok=True)

    parsed_rows = []
    for local_idx, job in enumerate(jobs, args.start + 1):
        cid = job["custom_id"]
        raw_path = raw_dir / f"{cid}.json"
        parsed_path = parsed_dir / f"{cid}.json"
        if raw_path.exists() and parsed_path.exists() and not args.force:
            print(f"[{local_idx}] skip {cid}")
            parsed_rows.append(load_json(parsed_path))
            continue

        print(f"[{local_idx}] MiniMax describe {cid}")
        prompt = build_strict_json_prompt(job)
        result = subprocess.run([
            mmx,
            "vision",
            "describe",
            "--api-key",
            api_key,
            "--image",
            job["evidence"]["strip"],
            "--prompt",
            prompt,
            "--output",
            "json",
            "--non-interactive",
            "--quiet",
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")

        raw_payload: dict[str, Any]
        if result.returncode != 0:
            raw_payload = {"error": result.stderr or result.stdout, "returncode": result.returncode}
        else:
            raw_payload = safe_json(result.stdout) or {"raw_stdout": result.stdout}
        write_json(raw_path, raw_payload)

        parsed = parse_response(job, raw_payload)
        write_json(parsed_path, parsed)
        parsed_rows.append(parsed)
        time.sleep(args.sleep)

    existing = []
    for path in sorted(parsed_dir.glob("*.json")):
        existing.append(load_json(path))
    write_json(out_dir / "minimax_vlm_results.json", existing)
    write_csv(out_dir / "minimax_vlm_results.csv", existing)
    write_review_md(out_dir / "minimax_review_summary.md", existing)
    ok_count = sum(1 for row in existing if row.get("parse_ok"))
    failed_count = len(existing) - ok_count
    print(f"Done: {len(parsed_rows)} processed in this run, {ok_count}/{len(existing)} parse_ok, {failed_count} failed")


def build_strict_json_prompt(job: dict[str, Any]) -> str:
    v2 = job["v2_prelabels"]
    profile = job.get("profile", "generic")
    schema = profile_schema(profile)
    return f"""Return ONLY JSON. Use exact English keys: scene, visible_subjects, pet_action, pet_event, description, quality, vlog_fit, diary_fit, comic_fit, why_memorable, diary_sentence, comic_panel_caption, corrections_to_v2.
Analyze actual visible evidence only. quality value is one of: good, usable, bad.
Profile: {profile}.
For pet_action and pet_event, choose 1-3 exact label IDs from the allowed lists below. Do not write a long sentence in these two fields.
For scene, visible_subjects, description, why_memorable, diary_sentence, and comic_panel_caption, use concise Simplified Chinese.
Allowed visible_subjects: {json.dumps(schema["visible_subjects"], ensure_ascii=False)}.
Allowed pet_action: {json.dumps(schema["pet_action"], ensure_ascii=False)}.
Allowed pet_event: {json.dumps(schema["pet_event"], ensure_ascii=False)}.
Code hints, do not copy language: scene={'|'.join(v2.get('scene', []))}; action={'|'.join(v2.get('pet_action', []))}; event={'|'.join(v2.get('pet_event', []))}; quality={v2.get('quality')}.
Correct hints if wrong. Do not overuse run/chase; distinguish sniff/search, grass/bush, water play/swim, human following, animal/social, quiet observation, path walk, object inspection.
Example shape: {{"scene":["河边沙滩"],"visible_subjects":["water","human"],"pet_action":["swim"],"pet_event":["water_adventure"],"description":"第一视角从水面冲到岸边，水花溅起，人站在旁边。","quality":"good","vlog_fit":4,"diary_fit":4,"comic_fit":3,"why_memorable":"水和人的位置变化清楚，动作有起伏。","diary_sentence":"我从水里冲出来，把岸边也踩成了浪。","comic_panel_caption":"上岸！","corrections_to_v2":["把run改为swim"]}}"""


def profile_schema(profile: str) -> dict[str, list[str]]:
    base_subjects = ["owner", "human", "dog", "cat", "animal", "water", "grass", "brush", "toy", "food", "ground", "building", "vehicle", "unknown"]
    if profile == "cat":
        return {
            "visible_subjects": base_subjects + ["window", "shelf", "fence", "tree", "prey", "bird", "rodent", "litter_box", "scratching_post"],
            "pet_action": ["walk", "creep", "stalk", "sniff", "search", "look_around", "look_up", "hide", "perch", "climb", "jump", "pause_observe", "approach_human", "approach_animal", "unclear"],
            "pet_event": ["ground_patrol", "prey_track", "brush_inspection", "threshold_pause", "sudden_attention", "window_watch", "perch_or_climb", "owner_check_in", "quiet_observation", "new_scene_discovery", "sound_triggered_attention", "low_signal"],
        }
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


def build_chinese_prompt(job: dict[str, Any]) -> str:
    v2 = job["v2_prelabels"]
    return f"""只输出一个JSON对象。首字符必须是{{，末字符必须是}}。不要markdown，不要解释。
任务：给宠物第一视角三连帧打标，只根据画面证据判断。
V2预标签: scene={'|'.join(v2.get('scene', []))}; action={'|'.join(v2.get('pet_action', []))}; event={'|'.join(v2.get('pet_event', []))}; quality={v2.get('quality')}.
JSON字段:
{{
  "scene": [],
  "visible_subjects": [],
  "pet_action": [],
  "pet_event": [],
  "quality": "good|usable|bad",
  "vlog_fit": 0-5,
  "diary_fit": 0-5,
  "comic_fit": 0-5,
  "why_memorable": "",
  "diary_sentence": "",
  "comic_panel_caption": "",
  "corrections_to_v2": []
}}"""


def parse_response(job: dict[str, Any], raw_payload: dict[str, Any]) -> dict[str, Any]:
    content = raw_payload.get("content") if isinstance(raw_payload, dict) else None
    content = repair_mojibake(content or "")
    parsed = extract_json(content or "")
    if isinstance(parsed, dict):
        parsed = repair_obj(parsed)
    base = {
        "segment_id": job["custom_id"],
        "video_id": job["segment"]["video_id"],
        "video_name": job["segment"]["video_name"],
        "start": job["segment"]["start"],
        "end": job["segment"]["end"],
        "strip": job["evidence"]["strip"],
        "primary_comic_frame": job["evidence"]["primary_comic_frame"],
        "profile": job.get("profile", "generic"),
        "v2_scene": "|".join(job["v2_prelabels"]["scene"]),
        "v2_action": "|".join(job["v2_prelabels"]["pet_action"]),
        "v2_event": "|".join(job["v2_prelabels"]["pet_event"]),
        "v2_vlog_score": job["v2_prelabels"]["vlog_score"],
        "v2_diary_score": job["v2_prelabels"]["diary_score"],
        "v2_comic_score": job["v2_prelabels"]["comic_score"],
    }
    if parsed is None:
        base.update({
            "parse_ok": False,
            "raw_content": content or json.dumps(raw_payload, ensure_ascii=False),
        })
        return base

    scene = first_present(parsed, "scene", "场景", "环境", "地点")
    subjects = first_present(parsed, "visible_subjects", "subjects", "主体", "可见主体", "画面主体", "物体")
    action = first_present(parsed, "pet_action", "action", "动作", "动作名称", "动作描述", "活动")
    event = first_present(parsed, "pet_event", "event", "事件", "标签", "高光事件")
    description = first_present(parsed, "description", "描述", "画面描述", "动作描述")
    why = first_present(parsed, "why_memorable", "why", "原因", "动作描述", "高光原因", "description", "描述")
    diary = first_present(parsed, "diary_sentence", "diary", "日记", "日记句子")
    comic_caption = first_present(parsed, "comic_panel_caption", "comic_caption", "漫画标题", "漫画字幕", "分镜字幕")
    corrections = first_present(parsed, "corrections_to_v2", "corrections", "修正", "修正建议")
    quality = parsed.get("quality", parsed.get("质量", job["v2_prelabels"].get("quality", "")))
    vlog_fit = parsed.get("vlog_fit", parsed.get("vlog", fallback_fit(job, "vlog_score")))
    diary_fit = parsed.get("diary_fit", parsed.get("diary_score", fallback_fit(job, "diary_score")))
    comic_fit = parsed.get("comic_fit", parsed.get("comic_score", fallback_fit(job, "comic_score")))
    if scene in (None, "", []):
        scene = job["v2_prelabels"].get("scene", [])
    if action in (None, "", []):
        action = description
    if event in (None, "", []):
        event = job["v2_prelabels"].get("pet_event", [])
    if subjects in (None, "", []):
        subjects = infer_subjects(join_list(description))

    profile = job.get("profile", "generic")
    raw_action = join_list(action)
    raw_event = join_list(event)
    context = " ".join(join_list(x) for x in [scene, subjects, action, event, description, why]).lower()
    normalized_action = normalize_profile_labels(profile, "pet_action", raw_action, context)
    normalized_event = normalize_profile_labels(profile, "pet_event", raw_event, context)

    base.update({
        "parse_ok": True,
        "scene": join_list(scene),
        "visible_subjects": join_list(subjects),
        "pet_action": "|".join(normalized_action) if normalized_action else raw_action,
        "pet_event": "|".join(normalized_event) if normalized_event else raw_event,
        "model_pet_action_raw": raw_action,
        "model_pet_event_raw": raw_event,
        "description": join_list(description),
        "quality": quality,
        "vlog_fit": vlog_fit,
        "diary_fit": diary_fit,
        "comic_fit": comic_fit,
        "why_memorable": join_list(why),
        "diary_sentence": join_list(diary),
        "comic_panel_caption": join_list(comic_caption),
        "corrections_to_v2": join_list(corrections),
    })
    return base


def normalize_profile_labels(profile: str, field: str, value: str, context: str) -> list[str]:
    schema = profile_schema(profile).get(field, [])
    value_text = value.lower()
    combined = f"{value_text} {context}"
    exact = [label for label in schema if label in value_text]
    if exact:
        return dedupe(exact)[:3]
    if profile == "cat":
        if field == "pet_action":
            rules = [
                ("look_up", ["look up", "looking up", "upward", "sky"]),
                ("hide", ["hide", "hidden", "obscured", "under", "behind"]),
                ("stalk", ["stalk", "prey", "rodent", "small animal", "tracking"]),
                ("search", ["inspect", "search", "sniff", "brush", "hay", "straw", "grass"]),
                ("creep", ["slow", "creep", "low", "through grass", "undergrowth"]),
                ("walk", ["walk", "walking", "moving forward", "moves forward", "traversing"]),
                ("look_around", ["look around", "turn", "pan", "scanning", "observe"]),
                ("pause_observe", ["pause", "static", "quiet observation", "stabilizes"]),
                ("approach_human", ["person", "human", "owner", "legs", "feet"]),
                ("approach_animal", ["animal", "dog", "cat", "rodent", "bird"]),
            ]
        else:
            rules = [
                ("prey_track", ["prey", "rodent", "small animal", "animal interaction", "hidden movement"]),
                ("brush_inspection", ["brush", "hay", "straw", "dry grass", "undergrowth", "foliage"]),
                ("threshold_pause", ["building", "post", "paved", "edge", "boundary", "courtyard"]),
                ("sudden_attention", ["quick turn", "sudden", "look up", "upward", "new view"]),
                ("ground_patrol", ["gravel", "rocks", "stones", "ground", "field rows", "walking"]),
                ("owner_check_in", ["owner", "person", "human", "legs", "feet"]),
                ("quiet_observation", ["quiet", "observe", "observation", "static", "pauses"]),
                ("new_scene_discovery", ["new scene", "discover", "reveal", "clearing", "wide-angle"]),
            ]
        return labels_from_rules(rules, combined)[:3]
    if profile == "dog":
        if field == "pet_action":
            rules = [
                ("swim", ["swim", "water", "river", "lake"]),
                ("run", ["run", "running", "fast"]),
                ("chase", ["chase", "following animal", "pursuit"]),
                ("sniff", ["sniff", "nose", "smell"]),
                ("search", ["search", "inspect", "grass", "bush"]),
                ("play", ["toy", "ball", "stick", "play"]),
                ("approach_human", ["human", "person", "owner"]),
                ("approach_animal", ["dog", "animal"]),
                ("walk", ["walk", "walking", "path", "trail"]),
            ]
        else:
            rules = [
                ("water_adventure", ["water", "river", "lake", "swim"]),
                ("grass_exploration", ["grass", "bush", "sniff"]),
                ("search_or_inspect", ["search", "inspect", "object"]),
                ("human_connection", ["human", "person", "owner"]),
                ("animal_social_moment", ["dog", "animal"]),
                ("run_or_chase", ["run", "chase", "fast"]),
                ("quiet_observation", ["quiet", "observe", "pause"]),
                ("new_scene_discovery", ["new scene", "discover", "reveal"]),
            ]
        return labels_from_rules(rules, combined)[:3]
    return []


def labels_from_rules(rules: list[tuple[str, list[str]]], text: str) -> list[str]:
    labels = []
    for label, keywords in rules:
        if any(keyword in text for keyword in keywords):
            labels.append(label)
    return dedupe(labels)


def dedupe(values: list[str]) -> list[str]:
    out = []
    seen = set()
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out


def extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.S)
    if fenced:
        cleaned = fenced.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start:end + 1]
    try:
        return json.loads(cleaned)
    except Exception:
        return None


def safe_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def repair_mojibake(text: str) -> str:
    if not text:
        return text
    if any(marker in text for marker in ("鍔", "涓", "瑙", "姘", "馃")):
        for encoding in ("gbk", "cp936"):
            try:
                repaired = text.encode(encoding, errors="strict").decode("utf-8", errors="strict")
            except Exception:
                continue
            if count_cjk(repaired) > count_cjk(text):
                return repaired
    return text


def repair_obj(value: Any) -> Any:
    if isinstance(value, dict):
        return {repair_mojibake(str(k)): repair_obj(v) for k, v in value.items()}
    if isinstance(value, list):
        return [repair_obj(v) for v in value]
    if isinstance(value, str):
        return repair_mojibake(value)
    return value


def count_cjk(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", []):
            return value
    return ""


def fallback_fit(job: dict[str, Any], score_key: str) -> float:
    value = float(job["v2_prelabels"].get(score_key, 0) or 0)
    return round(max(0.0, min(5.0, value / 20.0)), 1)


def infer_subjects(text: str) -> list[str]:
    candidates = {
        "水": ("水", "湖", "河", "水花", "岸"),
        "沙滩": ("沙", "沙滩"),
        "草地": ("草", "草地", "草丛", "灌木"),
        "人": ("人", "主人", "腿", "行人"),
        "路面": ("路", "步道", "道路", "小径"),
        "树木": ("树", "树林"),
        "动物": ("狗", "动物", "鸟", "同伴"),
        "玩具或物体": ("球", "玩具", "物体", "设备"),
    }
    found = [label for label, words in candidates.items() if any(word in text for word in words)]
    return found


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    keys = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_review_md(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = ["# MiniMax VLM Review Summary", ""]
    ok = [r for r in rows if r.get("parse_ok")]
    lines.append(f"- parsed: {len(ok)} / {len(rows)}")
    lines.append("")
    for row in ok[:40]:
        lines.append(f"## {row['segment_id']} · {row['start']}-{row['end']}")
        lines.append("")
        lines.append(f"- scene: {row.get('scene')}")
        lines.append(f"- subjects: {row.get('visible_subjects')}")
        lines.append(f"- action: {row.get('pet_action')}")
        lines.append(f"- event: {row.get('pet_event')}")
        lines.append(f"- fit: vlog {row.get('vlog_fit')} / diary {row.get('diary_fit')} / comic {row.get('comic_fit')}")
        lines.append(f"- why: {row.get('why_memorable')}")
        lines.append(f"- diary: {row.get('diary_sentence')}")
        lines.append(f"- comic: {row.get('comic_panel_caption')}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def join_list(value: Any) -> str:
    if isinstance(value, list):
        return "|".join(str(v) for v in value)
    return "" if value is None else str(value)


if __name__ == "__main__":
    main()
