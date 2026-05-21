#!/usr/bin/env python3
"""Refine AUREN POV V1 heuristic labels into a richer V2 taxonomy.

V2 separates:
- pet_action: observable movement/behavior;
- pet_event: narrative interaction with the world;
- vlog/diary/comic scores: different content formats need different moments.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--segments", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-n", type=int, default=80)
    args = parser.parse_args()

    rows = read_rows(Path(args.segments))
    refined = [refine(row) for row in rows]
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    write_json(out_dir / "segments_v2.json", refined)
    write_csv(out_dir / "segments_v2.csv", refined)
    for mode in ["vlog", "diary", "comic"]:
        top = sorted(refined, key=lambda r: float(r[f"{mode}_score"]), reverse=True)[: args.top_n]
        write_json(out_dir / f"top_{mode}.json", top)
        write_csv(out_dir / f"top_{mode}.csv", top)
    write_human_queue(out_dir, refined, args.top_n)
    write_taxonomy(out_dir)
    write_review_html(out_dir, refined)

    print("Done")
    print(f"- segments_v2: {out_dir / 'segments_v2.csv'}")
    print(f"- top_vlog:    {out_dir / 'top_vlog.csv'}")
    print(f"- top_diary:   {out_dir / 'top_diary.csv'}")
    print(f"- top_comic:   {out_dir / 'top_comic.csv'}")
    print(f"- review:      {out_dir / 'review_v2.html'}")


def refine(row: dict[str, str]) -> dict[str, Any]:
    f = numeric(row)
    name = row["video_name"]
    scene = classify_scene(f, name)
    subjects = classify_subjects(f, name)
    action = classify_action(f, name, scene, subjects)
    event = classify_event(f, name, scene, subjects, action)
    quality = classify_quality(f)
    why = build_why(scene, subjects, action, event, quality)

    semantic = semantic_score(scene, subjects, action, event)
    visual = visual_score(f, quality)
    motion_story = clamp(f["motion"] * 0.55 + f["novelty"] * 0.30 + f["audio_energy"] * 0.15)
    clarity = 1.0 if quality == "good" else 0.62 if quality == "usable_but_blocked" else 0.22

    vlog_score = clamp(0.42 * motion_story + 0.22 * semantic + 0.22 * visual + 0.14 * clarity)
    diary_score = clamp(0.48 * semantic + 0.22 * motion_story + 0.18 * visual + 0.12 * clarity)
    comic_score = clamp(0.42 * visual + 0.30 * semantic + 0.18 * clarity + 0.10 * (1.0 - min(f["motion"], 1.0)))

    preferred = []
    if vlog_score >= 0.58:
        preferred.append("vlog")
    if diary_score >= 0.55:
        preferred.append("diary")
    if comic_score >= 0.58 and quality == "good":
        preferred.append("comic")
    if not preferred:
        preferred.append("review_only")

    out = dict(row)
    out.update({
        "scene_v2": "|".join(scene),
        "visible_subjects_v2": "|".join(subjects),
        "pet_action_v2": "|".join(action),
        "pet_event_v2": "|".join(event),
        "quality_v2": quality,
        "why_memorable_v2": why,
        "vlog_score": round(vlog_score * 100, 1),
        "diary_score": round(diary_score * 100, 1),
        "comic_score": round(comic_score * 100, 1),
        "preferred_formats": "|".join(preferred),
        "content_logic": content_logic(preferred, action, event),
    })
    return out


def classify_scene(f: dict[str, float], name: str) -> list[str]:
    labels = []
    if f["lower_blue_ratio"] > 0.18:
        labels.append("water_edge_or_water_surface")
    elif f["blue_ratio"] > 0.23:
        labels.append("sky_open_view")
    if f["green_ratio"] > 0.22:
        labels.append("grass_bush_or_park")
    if f["green_ratio"] < 0.08 and f["blue_ratio"] < 0.10 and f["brightness"] > 0.42:
        labels.append("pavement_or_open_ground")
    if f["brightness"] < 0.24:
        labels.append("shadow_or_indoor")
    if "beach" in name.lower():
        labels.append("beach")
    if "lake" in name.lower() or "river" in name.lower() or "水" in name:
        labels.append("water_trip")
    return dedupe(labels) or ["unclear_scene"]


def classify_subjects(f: dict[str, float], name: str) -> list[str]:
    labels = []
    if f["top_dark_ratio"] > 0.12:
        labels.append("dog_muzzle_or_head")
    if f["top_dark_ratio"] > 0.42:
        labels.append("camera_blockage")
    if "主人" in name or "owner" in name.lower():
        labels.append("owner_or_handler_likely")
    if "猫" in name or "cat" in name.lower():
        labels.append("cat_or_animal_likely")
    if "lake" in name.lower() or "river" in name.lower() or f["lower_blue_ratio"] > 0.18:
        labels.append("water")
    if f["green_ratio"] > 0.22:
        labels.append("grass_or_bush")
    if not labels:
        labels.append("unknown_subject")
    return dedupe(labels)


def classify_action(f: dict[str, float], name: str, scene: list[str], subjects: list[str]) -> list[str]:
    labels = []
    if "water_edge_or_water_surface" in scene and (f["motion"] > 0.34 or f["audio_energy"] > 0.38):
        labels.append("water_play_or_swim")
    if f["top_dark_ratio"] > 0.12 and f["motion"] < 0.70:
        if "grass_or_bush" in subjects:
            labels.append("sniff_grass_or_bush")
        else:
            labels.append("sniff_or_search_close")
    if "owner_or_handler_likely" in subjects:
        labels.append("watch_or_follow_human")
    if "cat_or_animal_likely" in subjects:
        labels.append("animal_interaction")
    if f["motion"] > 0.74:
        labels.append("quick_move_or_turn")
    elif f["motion"] > 0.42:
        labels.append("walk_explore")
    elif f["sharpness"] > 0.42:
        labels.append("pause_observe")
    else:
        labels.append("unclear_motion")
    if f["novelty"] > 0.62:
        labels.append("look_around_or_new_view")
    return dedupe(labels)


def classify_event(f: dict[str, float], name: str, scene: list[str], subjects: list[str], action: list[str]) -> list[str]:
    labels = []
    if "water_play_or_swim" in action:
        labels.append("water_adventure")
    if "sniff_grass_or_bush" in action:
        labels.append("grass_exploration")
    if "sniff_or_search_close" in action:
        labels.append("search_or_inspect")
    if "watch_or_follow_human" in action:
        labels.append("human_connection")
    if "animal_interaction" in action:
        labels.append("animal_social_moment")
    if "quick_move_or_turn" in action and not labels:
        labels.append("fast_transition")
    if "pause_observe" in action:
        labels.append("quiet_observation")
    if f["audio_energy"] > 0.70:
        labels.append("sound_triggered_attention")
    if f["novelty"] > 0.62:
        labels.append("new_scene_discovery")
    return dedupe(labels) or ["low_semantic_signal"]


def classify_quality(f: dict[str, float]) -> str:
    if f["brightness"] < 0.14:
        return "bad_dark"
    if f["brightness"] > 0.84:
        return "bad_overexposed"
    if f["sharpness"] < 0.18:
        return "bad_blurry"
    if f["top_dark_ratio"] > 0.45:
        return "usable_but_blocked"
    return "good"


def semantic_score(scene: list[str], subjects: list[str], action: list[str], event: list[str]) -> float:
    score = 0.0
    meaningful_events = {
        "water_adventure", "grass_exploration", "search_or_inspect",
        "human_connection", "animal_social_moment", "quiet_observation",
        "sound_triggered_attention", "new_scene_discovery",
    }
    score += min(len(set(event) & meaningful_events) * 0.20, 0.55)
    score += 0.14 if any(x in scene for x in ["water_edge_or_water_surface", "grass_bush_or_park", "beach"]) else 0.05
    score += 0.12 if any(x in subjects for x in ["owner_or_handler_likely", "cat_or_animal_likely", "grass_or_bush", "water"]) else 0.0
    score += 0.12 if any(x in action for x in ["sniff_grass_or_bush", "sniff_or_search_close", "water_play_or_swim", "animal_interaction"]) else 0.0
    return clamp(score)


def visual_score(f: dict[str, float], quality: str) -> float:
    score = 0.42 * f["sharpness"] + 0.22 * f["contrast"] + 0.20 * min(f["green_ratio"] + f["blue_ratio"], 0.45) / 0.45 + 0.16 * (1.0 - abs(f["brightness"] - 0.48))
    if quality.startswith("bad"):
        score *= 0.45
    if quality == "usable_but_blocked":
        score *= 0.75
    return clamp(score)


def build_why(scene: list[str], subjects: list[str], action: list[str], event: list[str], quality: str) -> str:
    pieces = []
    if "water_adventure" in event:
        pieces.append("water-side/swim-like interaction")
    if "grass_exploration" in event:
        pieces.append("grass/bush exploration")
    if "search_or_inspect" in event:
        pieces.append("close search/inspection behavior")
    if "human_connection" in event:
        pieces.append("likely owner/human attention moment")
    if "animal_social_moment" in event:
        pieces.append("likely animal interaction moment")
    if "new_scene_discovery" in event:
        pieces.append("new view or scene transition")
    if "quiet_observation" in event:
        pieces.append("stable observation moment")
    if quality != "good":
        pieces.append(f"quality={quality}")
    return "; ".join(pieces) if pieces else "candidate needs VLM/human review"


def content_logic(preferred: list[str], action: list[str], event: list[str]) -> str:
    notes = []
    if "vlog" in preferred:
        notes.append("vlog: motion/transition/ambient energy can carry rhythm")
    if "diary" in preferred:
        notes.append("diary: semantic event can become a pet-memory sentence")
    if "comic" in preferred:
        notes.append("comic: frame is readable enough for a storyboard panel")
    if not notes:
        notes.append("review: useful for training or false-positive analysis")
    return "; ".join(notes)


def numeric(row: dict[str, str]) -> dict[str, float]:
    keys = [
        "brightness", "sharpness", "contrast", "motion", "novelty", "audio_energy",
        "green_ratio", "blue_ratio", "top_dark_ratio", "lower_blue_ratio",
    ]
    return {k: safe_float(row.get(k, 0)) for k in keys}


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_human_queue(out_dir: Path, rows: list[dict[str, Any]], top_n: int) -> None:
    selected: dict[str, dict[str, Any]] = {}
    for mode in ["vlog", "diary", "comic"]:
        for row in sorted(rows, key=lambda r: float(r[f"{mode}_score"]), reverse=True)[:top_n]:
            selected[row["segment_id"]] = row
    fields = [
        "segment_id", "video_id", "video_name", "start", "end", "frame_path",
        "scene_v2", "pet_action_v2", "pet_event_v2", "quality_v2",
        "vlog_score", "diary_score", "comic_score", "preferred_formats",
        "human_action", "human_event", "human_highlight_score",
        "approve_vlog", "approve_diary", "approve_comic", "human_note",
    ]
    with (out_dir / "human_label_queue_v2.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in selected.values():
            writer.writerow({k: row.get(k, "") for k in fields})


def write_taxonomy(out_dir: Path) -> None:
    text = """# AUREN POV Label Taxonomy V2

## Principle

Do not treat every dynamic moment as `run_chase`. AUREN needs to know how the pet
interacts with the world: water, grass, humans, animals, objects, route changes,
searching, pausing, and reacting to sound.

## Fields

- `scene_v2`: visual environment, such as `water_edge_or_water_surface`, `grass_bush_or_park`, `beach`, `pavement_or_open_ground`.
- `visible_subjects_v2`: likely visible/expected subjects, such as `dog_muzzle_or_head`, `owner_or_handler_likely`, `cat_or_animal_likely`, `water`, `grass_or_bush`.
- `pet_action_v2`: observable behavior, such as `water_play_or_swim`, `sniff_grass_or_bush`, `sniff_or_search_close`, `watch_or_follow_human`, `animal_interaction`, `quick_move_or_turn`, `pause_observe`.
- `pet_event_v2`: narrative interaction, such as `water_adventure`, `grass_exploration`, `search_or_inspect`, `human_connection`, `animal_social_moment`, `quiet_observation`, `new_scene_discovery`.
- `vlog_score`: favors rhythm, motion, scene transitions, ambient energy.
- `diary_score`: favors semantic specificity and a writable pet-memory sentence.
- `comic_score`: favors clear, readable, stable visual panels.

## Known Limitation

V2 is still heuristic. It uses filename hints and visual/audio features. Real
owner/cat/dog/object recognition needs a vision-language model pass and human
correction.
"""
    (out_dir / "LABEL_TAXONOMY_V2.md").write_text(text, encoding="utf-8")


def write_review_html(out_dir: Path, rows: list[dict[str, Any]]) -> None:
    def cards(mode: str) -> str:
        top = sorted(rows, key=lambda r: float(r[f"{mode}_score"]), reverse=True)[:32]
        return "\n".join(card(out_dir, row, mode) for row in top)

    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>AUREN Prelabels V2</title>
  <style>
    body {{ margin:0; background:#f5f1ec; color:#2d241f; font-family:"Microsoft YaHei","Noto Sans SC",Arial,sans-serif; }}
    header {{ padding:30px 38px 18px; border-bottom:1px solid #dacbbe; }}
    main {{ padding:24px 28px 60px; }}
    h1 {{ margin:0 0 8px; font-size:28px; }}
    h2 {{ margin:34px 0 16px; font-size:21px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:16px; }}
    .card {{ background:#fffaf4; border:1px solid #d8c9ba; border-radius:8px; padding:12px; }}
    img {{ width:100%; border-radius:6px; border:1px solid #cab9a9; }}
    p {{ margin:6px 0; color:#6e5e53; font-size:13px; line-height:1.42; }}
    code {{ font-size:12px; }}
    .score {{ color:#2d241f; font-weight:700; }}
  </style>
</head>
<body>
  <header>
    <h1>AUREN Prelabels V2</h1>
    <p>V2 separates action, narrative event, and format-specific selection logic.</p>
  </header>
  <main>
    <section><h2>Top Vlog Candidates</h2><div class="grid">{cards("vlog")}</div></section>
    <section><h2>Top Diary Candidates</h2><div class="grid">{cards("diary")}</div></section>
    <section><h2>Top Comic Candidates</h2><div class="grid">{cards("comic")}</div></section>
  </main>
</body>
</html>"""
    (out_dir / "review_v2.html").write_text(doc, encoding="utf-8")


def card(root: Path, row: dict[str, Any], mode: str) -> str:
    rel = Path(row["frame_path"]).resolve()
    try:
        img = rel.relative_to(root).as_posix()
    except ValueError:
        img = rel.as_posix()
    return f"""<article class="card">
      <img src="{html.escape(img)}" />
      <p><span class="score">{html.escape(str(row[f'{mode}_score']))}</span> · {html.escape(row['segment_id'])} · {html.escape(row['start'])}-{html.escape(row['end'])}</p>
      <p><b>scene</b>: <code>{html.escape(str(row['scene_v2']))}</code></p>
      <p><b>action</b>: <code>{html.escape(str(row['pet_action_v2']))}</code></p>
      <p><b>event</b>: <code>{html.escape(str(row['pet_event_v2']))}</code></p>
      <p><b>formats</b>: <code>{html.escape(str(row['preferred_formats']))}</code></p>
      <p>{html.escape(str(row['why_memorable_v2']))}</p>
    </article>"""


def dedupe(values: list[str]) -> list[str]:
    out = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


if __name__ == "__main__":
    main()
