#!/usr/bin/env python3
"""Run the AUREN pet POV pipeline end to end.

The script is intentionally a thin orchestrator around the smaller tools. It is
safe to run without model calls; add `--run-vlm` when MiniMax credentials are
available and you want final content generation in the same command.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--profile", choices=["generic", "dog", "cat"], default="generic")
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--interval", type=int, default=2)
    parser.add_argument("--top-per-video", type=int, default=10)
    parser.add_argument("--global-top", type=int, default=70)
    parser.add_argument("--top-n", type=int, default=36)
    parser.add_argument("--per-mode", type=int, default=36)
    parser.add_argument("--run-vlm", action="store_true")
    parser.add_argument("--build-content", action="store_true")
    parser.add_argument("--evaluate", action="store_true", help="Run output QA after content build. Requires final comic assets to exist.")
    parser.add_argument("--min-videos", type=int, default=2, help="Minimum distinct source videos required by output QA.")
    parser.add_argument("--min-events", type=int, default=3, help="Minimum distinct event labels required by output QA.")
    parser.add_argument("--results", default="", help="Existing MiniMax result JSON, used when --build-content is set without --run-vlm.")
    parser.add_argument("--bgm", default="")
    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    run_py("prepare_pov_eval_pack.py", "--source-dir", source_dir, "--output-dir", out_dir, "--samples", args.samples)
    prelabels_v1 = out_dir / "prelabels_v1"
    run_py(
        "prelabel_pov_segments.py",
        "--source-dir",
        source_dir,
        "--output-dir",
        prelabels_v1,
        "--interval",
        args.interval,
        "--top-per-video",
        args.top_per_video,
        "--global-top",
        args.global_top,
    )
    prelabels_v2 = out_dir / "prelabels_v2"
    run_py("refine_prelabels_v2.py", "--segments", prelabels_v1 / "segments.csv", "--output-dir", prelabels_v2, "--top-n", args.top_n)
    vlm_jobs = out_dir / "vlm_jobs_v3"
    run_py("prepare_vlm_jobs_v3.py", "--v2-dir", prelabels_v2, "--output-dir", vlm_jobs, "--per-mode", args.per_mode, "--profile", args.profile)

    results = Path(args.results).resolve() if args.results else None
    if args.run_vlm:
        if not os.environ.get("MINIMAX_API_KEY"):
            raise SystemExit("MINIMAX_API_KEY is required when --run-vlm is set.")
        vlm_results_dir = out_dir / "minimax_vlm_v1"
        run_py("run_minimax_vlm_batch.py", "--jobs", vlm_jobs / "vlm_jobs.jsonl", "--output-dir", vlm_results_dir, "--sleep", 0.3)
        results = vlm_results_dir / "minimax_vlm_results.json"

    if args.build_content:
        if not results or not results.exists():
            raise SystemExit("--build-content requires --run-vlm or --results pointing to minimax_vlm_results.json.")
        final_dir = out_dir / ("final_content_cat_v2" if args.profile == "cat" else "final_content_v2")
        if args.profile == "cat":
            cmd = ["build_cat_pov_content_v2.py", "--results", results, "--manifest", out_dir / "manifest.csv", "--output-dir", final_dir]
            if args.bgm:
                cmd.extend(["--bgm", Path(args.bgm).resolve()])
            run_py(*cmd)
        else:
            run_py("build_auren_content_v2_generic.py", "--results", results, "--manifest", out_dir / "manifest.csv", "--output-dir", final_dir)
        if args.evaluate:
            run_py("evaluate_content_outputs.py", "--output-dir", final_dir, "--min-videos", args.min_videos, "--min-events", args.min_events, "--write-report")

    print("AUREN pipeline complete", flush=True)
    print(f"- output_dir: {out_dir}", flush=True)
    print(f"- vlm_jobs: {vlm_jobs / 'vlm_jobs.jsonl'}", flush=True)


def run_py(script_name: str, *args: object) -> None:
    script = SCRIPT_DIR / script_name
    cmd = [sys.executable, str(script)]
    cmd.extend(str(arg) for arg in args)
    print(">", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
