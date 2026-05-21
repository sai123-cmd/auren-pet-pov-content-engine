#!/usr/bin/env python3
"""Evaluate AUREN generated content artifacts.

This is a lightweight regression check for the output standards. It does not
judge creative quality by itself, but it catches common failure modes:

- diary degraded into a scene list,
- highlight table is missing or too repetitive,
- comic/reference images are missing,
- vlog is missing video/audio streams or is too short.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-highlights", type=int, default=6)
    parser.add_argument("--min-vlog-duration", type=float, default=8.0)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.output_dir).resolve()
    if not out_dir.exists():
        raise SystemExit(f"Output directory not found: {out_dir}")

    report = {
        "output_dir": str(out_dir),
        "checks": [],
        "summary": {},
    }
    report["checks"].append(check_diary(out_dir))
    report["checks"].append(check_highlights(out_dir, args.min_highlights))
    report["checks"].append(check_images(out_dir))
    report["checks"].append(check_vlog(out_dir, args.min_vlog_duration))
    report["summary"]["passed"] = all(check["passed"] for check in report["checks"])
    report["summary"]["failed_checks"] = [check["name"] for check in report["checks"] if not check["passed"]]

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.write_report:
        (out_dir / "output_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "output_quality_report.md").write_text(markdown_report(report), encoding="utf-8")
    if not report["summary"]["passed"]:
        raise SystemExit(1)


def check_diary(out_dir: Path) -> dict[str, Any]:
    path = find_first(out_dir, ["*diary_story*.md", "*pet_diary_story*.md"])
    if not path:
        return fail("diary", "No diary story markdown found.")
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    bullet_lines = [line for line in lines if line.startswith(("-", "*", "1.", "2.", "3.", "4.", "5."))]
    paragraph_count = sum(1 for line in lines if not line.startswith("#") and not line.startswith(("<!--", "- ", "* ")))
    first_person_hits = sum(text.count(token) for token in ["我", "my ", "I ", "me "])
    passed = paragraph_count >= 4 and first_person_hits >= 5 and len(bullet_lines) <= 2
    return {
        "name": "diary",
        "passed": passed,
        "path": str(path),
        "paragraph_count": paragraph_count,
        "first_person_hits": first_person_hits,
        "bullet_lines": len(bullet_lines),
        "message": "Diary looks like a continuous first-person story." if passed else "Diary may have regressed into a list/report or lacks first-person voice.",
    }


def check_highlights(out_dir: Path, min_highlights: int) -> dict[str, Any]:
    path = find_first(out_dir, ["*highlights*.csv", "*recognition*.csv"])
    if not path:
        return fail("highlights", "No highlight CSV found.")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    sections = unique_nonempty(rows, "section")
    videos = unique_nonempty(rows, "video_name") or unique_nonempty(rows, "video_id")
    events = unique_nonempty(rows, "event")
    if not events:
        events = unique_nonempty(rows, "pet_event")
    passed = len(rows) >= min_highlights and len(sections) >= min(4, min_highlights) and len(videos) >= 2
    return {
        "name": "highlights",
        "passed": passed,
        "path": str(path),
        "row_count": len(rows),
        "unique_sections": len(sections),
        "unique_videos": len(videos),
        "unique_events": len(events),
        "message": "Highlight table has enough diversity." if passed else "Highlight table is missing, too short, or dominated by one source/section.",
    }


def check_images(out_dir: Path) -> dict[str, Any]:
    comic = find_first(out_dir, ["*comic*generated*.png", "*comic*generated*.jpg", "*comic_page*.png", "*comic_page*.jpg"])
    reference = find_first(out_dir, ["*comic_reference*.jpg", "*reference_real_scenes*.jpg", "*contact_sheet*.jpg"])
    details = []
    passed = True
    for label, path in [("comic", comic), ("reference", reference)]:
        if not path:
            passed = False
            details.append({"label": label, "path": None, "ok": False})
            continue
        try:
            with Image.open(path) as img:
                width, height = img.size
            if label == "comic":
                ok = width >= 900 and height >= 700
            else:
                ok = width >= 900 and height >= 500
            passed = passed and ok
            details.append({"label": label, "path": str(path), "ok": ok, "width": width, "height": height})
        except Exception as exc:
            passed = False
            details.append({"label": label, "path": str(path), "ok": False, "error": str(exc)})
    return {
        "name": "images",
        "passed": passed,
        "details": details,
        "message": "Comic/reference images exist at usable resolution." if passed else "Comic/reference image check failed.",
    }


def check_vlog(out_dir: Path, min_duration: float) -> dict[str, Any]:
    path = find_first(out_dir, ["*vlog*story*.mp4", "*pet_pov_story*.mp4", "*vlog*.mp4"])
    if not path:
        return fail("vlog", "No vlog mp4 found.")
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return fail("vlog", "ffprobe not found.")
    result = subprocess.run([
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-show_entries",
        "stream=codec_type,codec_name,width,height",
        "-of",
        "json",
        str(path),
    ], capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout)
    duration = float(payload.get("format", {}).get("duration") or 0)
    streams = payload.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    width = int(video_streams[0].get("width") or 0) if video_streams else 0
    height = int(video_streams[0].get("height") or 0) if video_streams else 0
    passed = bool(video_streams) and bool(audio_streams) and duration >= min_duration and width >= 720 and height >= 480
    return {
        "name": "vlog",
        "passed": passed,
        "path": str(path),
        "duration": round(duration, 3),
        "video_streams": len(video_streams),
        "audio_streams": len(audio_streams),
        "width": width,
        "height": height,
        "message": "Vlog has video, audio, and enough duration." if passed else "Vlog is missing a stream, too short, or too low resolution.",
    }


def find_first(folder: Path, patterns: list[str]) -> Path | None:
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(folder.glob(pattern))
    files = [p for p in matches if p.is_file()]
    if not files:
        return None
    return sorted(files, key=artifact_score, reverse=True)[0]


def artifact_score(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    score = 0
    if "looki" in name:
        score += 50
    if "generated" in name:
        score += 40
    if "reference_real_scenes" in name or "comic_reference" in name:
        score += 30
    if "contact_sheet" in name:
        score += 10
    if "grounded_v3" in name:
        score -= 20
    score += name.count("v")
    return score, name


def unique_nonempty(rows: list[dict[str, str]], key: str) -> set[str]:
    values: set[str] = set()
    for row in rows:
        value = (row.get(key) or "").strip()
        if value:
            values.add(value)
    return values


def fail(name: str, message: str) -> dict[str, Any]:
    return {"name": name, "passed": False, "message": message}


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# AUREN Output Quality Report",
        "",
        f"Output dir: `{report['output_dir']}`",
        "",
        f"Passed: `{report['summary']['passed']}`",
        "",
    ]
    for check in report["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        lines.append(f"## {check['name']} - {status}")
        lines.append("")
        lines.append(check.get("message", ""))
        lines.append("")
        for key, value in check.items():
            if key in {"name", "passed", "message"}:
                continue
            lines.append(f"- {key}: `{value}`")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
