# AUREN Pet POV Content Engine

AUREN Pet POV Content Engine turns first-person pet footage into three content products:

1. a continuous pet-voice diary,
2. a grounded illustrated comic page,
3. a narrative short vlog with captions and music.

The project started as a validation pipeline for dog bodycam / collar-cam videos. It is designed to keep the analysis layer separate from final storytelling so the same highlight evidence can drive different outputs.

## What “Good Output” Means

The demo is not considered successful just because it produces files. AUREN uses stricter acceptance criteria:

- Diary: one continuous first-person pet diary, not a scene list or analysis report.
- Comic: Looki-like hand-drawn comic based on real keyframes and events, with light imaginative elements. It must not be a photo filter or pure text-to-image hallucination.
- Vlog: an edited story with pacing, captions, original ambience, BGM, and a narrative arc. It must not be a bland clip concatenation.

See [docs/OUTPUT_STANDARDS.md](docs/OUTPUT_STANDARDS.md).

## Pipeline

```text
raw pet POV video(s)
  -> video inventory and keyframes
  -> heuristic prelabels
  -> segment refinement
  -> VLM jobs
  -> multimodal recognition results
  -> diary / grounded comic / vlog plan
  -> final rendered assets
```

The current implementation uses `ffmpeg`/`ffprobe`, Python, Pillow, OpenCV, optional MiniMax VLM/image/music APIs, and local rendering.

## Quick Start

Install dependencies:

```bash
pip install -r requirements.txt
```

Make sure `ffmpeg` and `ffprobe` are available on `PATH`.

Prepare a POV evaluation pack:

```bash
python scripts/prepare_pov_eval_pack.py \
  --source-dir /path/to/pet_pov_videos \
  --output-dir outputs/run_001 \
  --samples 12
```

Generate candidate highlights:

```bash
python scripts/prelabel_pov_segments.py \
  --source-dir /path/to/pet_pov_videos \
  --output-dir outputs/run_001/prelabels_v1 \
  --interval 4 \
  --top-per-video 18 \
  --global-top 120

python scripts/refine_prelabels_v2.py \
  --segments outputs/run_001/prelabels_v1/segments.csv \
  --output-dir outputs/run_001/prelabels_v2 \
  --top-n 36
```

Prepare VLM jobs:

```bash
python scripts/prepare_vlm_jobs_v3.py \
  --v2-dir outputs/run_001/prelabels_v2 \
  --output-dir outputs/run_001/vlm_jobs_v3 \
  --per-mode 36
```

Run MiniMax VLM batch:

```bash
export MINIMAX_API_KEY=...
python scripts/run_minimax_vlm_batch.py \
  --jobs outputs/run_001/vlm_jobs_v3/vlm_jobs.jsonl \
  --output-dir outputs/run_001/minimax_vlm_v1
```

Build content outputs:

```bash
python scripts/build_auren_content_v2_generic.py \
  --results outputs/run_001/minimax_vlm_v1/minimax_vlm_results.json \
  --manifest outputs/run_001/manifest.csv \
  --output-dir outputs/run_001/final_content_v2
```

For cat-specific POV runs, use the dedicated builder:

```bash
python scripts/build_cat_pov_content_v2.py \
  --results outputs/cat_run/minimax_vlm_v1/minimax_vlm_results.json \
  --manifest outputs/cat_run/manifest.csv \
  --output-dir outputs/cat_run/final_content_cat_v2 \
  --bgm outputs/cat_run/cat_bgm.mp3
```

## Dog POV Example

The repository includes a small example output pack under [examples/dog_pov_test_002](examples/dog_pov_test_002):

- diary: `pet_diary_story_v2.md`
- recognition evidence: `recognition_highlights_v2.csv`
- grounded comic sample: `assets/comic_page_looki_grounded_generated.png`
- vlog contact sheet: `assets/vlog_v2_contact_sheet.jpg`
- rendered vlog: `assets/vlog_v2_pet_pov_story.mp4`

Raw source videos are not included.

## Cat POV Example

The repository also includes a cat-specific evaluation pack under [examples/cat_pov_eval_001](examples/cat_pov_eval_001).

This run uses openly licensed Wikimedia Commons supplementary videos from Lesica et al. 2006. The source clips are short, monochrome, and low resolution, so the cat workflow is intentionally different from the dog workflow:

- diary: quiet stalking/observation voice, not a dog-style outing,
- highlights: leaf-floor scanning, prey attention, sudden upward attention, brush/nest investigation,
- comic: black-and-white cat POV redraw with whisker radar, scent lines, and blank thought bubbles,
- vlog: short suspenseful observation edit.

Key files:

- `cat_diary_story_v1.md`
- `cat_pov_highlights_v1.csv`
- `assets/cat_comic_looki_grounded_generated.png`
- `assets/cat_vlog_contact_sheet_v1.jpg`
- `assets/cat_vlog_story_v1.mp4`
- `cat_pov_self_evaluation_v1.md`

An additional local CatCam iteration was tested with longer academic-use-only cat-mounted videos from Zenodo. Those derived media are not committed because the dataset is CC BY-NC / academic use only, but the v2 cat builder and source notes are included so the workflow can be repeated with licensed material.

## Safety and Licensing

Do not commit API keys, private videos, copyrighted source footage, or user-identifying raw media. For public demos, use your own footage or openly licensed videos with clear attribution.

This repository contains pipeline code and generated examples only.
