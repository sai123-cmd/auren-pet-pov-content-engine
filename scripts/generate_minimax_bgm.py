#!/usr/bin/env python3
"""Generate instrumental BGM with the MiniMax CLI."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


DEFAULT_PROMPT = (
    "quiet whimsical pet first-person vlog background music, light pizzicato strings, "
    "soft marimba, warm pads, subtle suspense, no vocals, loopable video background"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--out", required=True)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default="music-2.6")
    parser.add_argument("--format", default="mp3", choices=["mp3", "wav", "pcm"])
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    mmx = shutil.which("mmx")
    if not mmx:
        raise SystemExit("mmx CLI not found on PATH")
    api_key = args.api_key or os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        raise SystemExit("Set MINIMAX_API_KEY or pass --api-key.")

    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        mmx,
        "music",
        "generate",
        "--api-key",
        api_key,
        "--prompt",
        args.prompt,
        "--instrumental",
        "--model",
        args.model,
        "--format",
        args.format,
        "--out",
        str(out),
        "--non-interactive",
        "--quiet",
        "--timeout",
        str(args.timeout),
    ], check=True)
    print(out)


if __name__ == "__main__":
    main()
