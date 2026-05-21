# Workflow

## 0. One-Command Run

Use the orchestrator for normal local runs:

```bash
python scripts/run_auren_pipeline.py \
  --source-dir /path/to/pet_pov_videos \
  --output-dir outputs/run_001 \
  --profile cat
```

Add `--run-vlm --build-content` when MiniMax credentials are available and you want final content in the same command.
Run `--evaluate` only after the final comic image exists in the content folder, because the current comic generation step is still image-model assisted rather than deterministic local rendering.

Optional BGM:

```bash
MINIMAX_API_KEY=... python scripts/generate_minimax_bgm.py \
  --out outputs/run_001/bgm.mp3
```

## 1. Inventory

Use `prepare_pov_eval_pack.py` to inspect source videos, extract keyframes, and produce a manifest.

## 2. Candidate Segments

Use `prelabel_pov_segments.py` to sample segments and score them with local heuristics. This is intentionally cheap and broad.

## 3. Refined Prelabels

Use `refine_prelabels_v2.py` to split candidate usefulness by content product:

- diary,
- comic,
- vlog.

The same moment may be great for a vlog but weak for a comic, or vice versa.

## 4. VLM Jobs

Use `prepare_vlm_jobs_v3.py` to build frame strips and prompts for a vision-language model.

Use a species profile when known:

```bash
python scripts/prepare_vlm_jobs_v3.py \
  --v2-dir outputs/cat_run/prelabels_v2 \
  --output-dir outputs/cat_run/vlm_jobs_v3 \
  --per-mode 36 \
  --profile cat
```

The VLM output should answer:

- What is the scene?
- Who or what is visible?
- What is the pet doing?
- What event is happening?
- Why is it memorable?
- Is it suitable for diary/comic/vlog?

Profiles tune label hints without changing the strict output schema:

- `generic`: general pet POV labels.
- `dog`: dog-specific actions and events such as swim, chase, grass exploration, and human connection.
- `cat`: cat-specific actions and events such as stalk, hide, perch, threshold pause, prey tracking, sudden attention, and brush inspection.

`run_minimax_vlm_batch.py` also normalizes free-form model text back into the active profile labels. This is important because a VLM may describe an action as a sentence even when the prompt asks for label IDs.

## 5. Content Rendering

Use `build_auren_content_v2_generic.py` to create:

- diary narrative,
- diary evidence,
- comic panels,
- comic grounding plan,
- vlog edit plan,
- storyboard dashboard,
- rendered vlog.

For cat POV, use `build_cat_pov_content_v2.py`. It selects cat-specific beats rather than dog-style action beats:

- ground patrol,
- field or threshold crossing,
- prey or rustle attention,
- sudden head turn,
- brush or hiding inspection,
- quiet ending.

The cat builder also handles no-audio scientific footage by creating a silent bed before mixing BGM, so CatCam-like data can still produce a watchable vlog.

If using Zenodo CatCam tar archives locally, convert them first:

```bash
python scripts/convert_catcam_tar_to_mp4.py \
  --input-dir /path/to/catcam_tars \
  --output-dir outputs/catcam_mp4
```

For final comic rendering, follow `docs/COMIC_GENERATION.md`. The local pipeline prepares grounded frames and briefs, but final Looki-like redraw requires an image-reference generation step.

## 6. Human Acceptance

Human review should check output quality against `docs/OUTPUT_STANDARDS.md`, not just file existence.

Use `evaluate_content_outputs.py` before handoff:

```bash
python scripts/evaluate_content_outputs.py \
  --output-dir outputs/run_001/final_content_v2 \
  --write-report
```

The evaluator checks for common regressions:

- diary is a continuous first-person story rather than a scene list,
- highlights have enough sections and source diversity,
- the final comic/reference images exist at usable resolution,
- the rendered vlog has video, audio, and enough duration.
