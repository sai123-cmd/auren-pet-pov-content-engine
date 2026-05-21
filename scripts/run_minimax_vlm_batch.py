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
    print(f"Done: {len(parsed_rows)} processed in this run, {len(existing)} total parsed")


def build_strict_json_prompt(job: dict[str, Any]) -> str:
    v2 = job["v2_prelabels"]
    return f"""Return ONLY JSON. Use exact English keys: scene, subjects, action, event, description, quality.
All VALUES must be Simplified Chinese, not English. If any value is English, the answer is invalid.
Analyze actual visible evidence only. quality value is one of: good, usable, bad.
Code hints, do not copy language: scene={'|'.join(v2.get('scene', []))}; action={'|'.join(v2.get('pet_action', []))}; event={'|'.join(v2.get('pet_event', []))}; quality={v2.get('quality')}.
Correct hints if wrong. Do not overuse run/chase; distinguish sniff/search, grass/bush, water play/swim, human following, animal/social, quiet observation, path walk, object inspection.
Example shape: {{"scene":"河边沙滩","subjects":["水","沙滩","人"],"action":"从水里跑向岸边","event":"水边探险","description":"狗的第一视角从水面冲到岸边，水花溅起，人站在旁边。","quality":"good"}}"""


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

    base.update({
        "parse_ok": True,
        "scene": join_list(scene),
        "visible_subjects": join_list(subjects),
        "pet_action": join_list(action),
        "pet_event": join_list(event),
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
