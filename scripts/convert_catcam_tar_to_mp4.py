#!/usr/bin/env python3
"""Convert Zenodo CatCam TIFF tar archives into MP4 files.

CatCam movies are distributed as tar archives containing numbered TIFF frames.
This helper keeps the raw dataset out of the repository while making local
validation repeatable.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tarfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True, help="Directory containing movieXX.tar files.")
    parser.add_argument("--output-dir", required=True, help="Directory for extracted frames and MP4 outputs.")
    parser.add_argument("--fps", type=float, default=25.0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--keep-frames", action="store_true")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    extract_dir = output_dir / "extracted"
    extract_dir.mkdir(exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg not found on PATH")

    archives = sorted(input_dir.glob("*.tar"))
    if not archives:
        raise SystemExit(f"No .tar files found in {input_dir}")

    for archive in archives:
        movie_dir = extract_archive(archive, extract_dir)
        out = output_dir / f"{archive.stem}_{movie_dir.name}.mp4"
        convert_movie(ffmpeg, movie_dir, out, args.fps, args.width, args.height, args.crf)
        print(f"{archive.name} -> {out}")
        if not args.keep_frames:
            shutil.rmtree(movie_dir, ignore_errors=True)


def extract_archive(archive: Path, extract_dir: Path) -> Path:
    with tarfile.open(archive, "r") as tar:
        names = [member.name for member in tar.getmembers() if member.name and "/" in member.name]
        roots = sorted({name.split("/", 1)[0] for name in names})
        if len(roots) != 1:
            raise RuntimeError(f"Expected one root folder in {archive}, found: {roots}")
        root = roots[0]
        movie_dir = extract_dir / root
        if movie_dir.exists() and any(movie_dir.glob("*.tif")):
            return movie_dir
        tar.extractall(extract_dir, filter="data")
        return movie_dir


def convert_movie(ffmpeg: str, movie_dir: Path, out: Path, fps: float, width: int, height: int, crf: int) -> None:
    frames = sorted(movie_dir.glob("*.tif"))
    if not frames:
        raise RuntimeError(f"No TIFF frames found in {movie_dir}")
    first = frames[0].stem
    digits = "".join(ch for ch in reversed(first) if ch.isdigit())[::-1]
    if not digits:
        raise RuntimeError(f"Cannot infer frame number padding from {frames[0].name}")
    prefix = first[: -len(digits)]
    pattern = str(movie_dir / f"{prefix}%0{len(digits)}d.tif")
    start_number = int(digits)
    vf = f"scale={width}:{height}:flags=lanczos,format=yuv420p"
    subprocess.run([
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        str(fps),
        "-start_number",
        str(start_number),
        "-i",
        pattern,
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-crf",
        str(crf),
        "-preset",
        "fast",
        str(out),
    ], check=True)


if __name__ == "__main__":
    main()
