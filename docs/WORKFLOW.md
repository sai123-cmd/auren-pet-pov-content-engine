# Workflow

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

The VLM output should answer:

- What is the scene?
- Who or what is visible?
- What is the pet doing?
- What event is happening?
- Why is it memorable?
- Is it suitable for diary/comic/vlog?

## 5. Content Rendering

Use `build_auren_content_v2_generic.py` to create:

- diary narrative,
- diary evidence,
- comic panels,
- comic grounding plan,
- vlog edit plan,
- storyboard dashboard,
- rendered vlog.

## 6. Human Acceptance

Human review should check output quality against `docs/OUTPUT_STANDARDS.md`, not just file existence.

