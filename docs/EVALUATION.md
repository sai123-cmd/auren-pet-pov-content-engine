# Evaluation

AUREN output evaluation has two layers:

1. automated regression checks that catch obvious product failures,
2. human review against `docs/OUTPUT_STANDARDS.md`.

The automated checks are intentionally lightweight. They do not judge whether a story is delightful or whether a comic has brand-level polish, but they stop common regressions before a result is handed off.

## Automated Checks

Run:

```bash
python scripts/evaluate_content_outputs.py \
  --output-dir outputs/run_001/final_content_v2 \
  --write-report
```

For larger validation runs, raise diversity thresholds:

```bash
python scripts/evaluate_content_outputs.py \
  --output-dir outputs/cat_run/final_content_cat_v2 \
  --min-videos 6 \
  --min-events 5 \
  --require-comic-plan \
  --write-report
```

The evaluator checks:

- diary is continuous prose with first-person voice,
- diary text is not mojibake,
- highlight CSV has enough rows, sections, source videos, event labels, and source attribution,
- when requested, comic imagination plan exists and every panel has event, joke, visual layer, and guardrail fields,
- comic and reference images exist at usable resolution,
- fallback/contact-sheet/storyboard images are not accepted as final comics,
- vlog has video, audio, enough duration, and usable resolution.

## Human Review

Human review should answer product questions that a script cannot answer yet:

- Does the diary feel like one pet day, not a list of clips?
- Are the highlight labels actually correct for scene/action/event?
- Is the comic grounded in real frames while still imaginative?
- Does the vlog have rhythm, an opening hook, middle development, and ending?
- Are captions varied and in pet voice?
- Does BGM support the edit without drowning the original ambience?

## Species Review Notes

Dog POV review should look for high-energy movement, owner/social contact, grass/water/toy interaction, and clear action changes.

Cat POV review should not overvalue speed. It should recognize subtle moments: threshold pauses, sudden attention, quiet stalking, hiding inspection, window/perch watching, owner check-ins, and prey/rustle tracking.

## Known Limits

The evaluator can verify that a final comic file is present and not a storyboard, reference board, contact sheet, or deterministic draft, but it cannot yet measure whether the image is mature enough or whether every imaginative element is naturally tied to the source event. Comic grounding still requires visual human review and should reject analysis-symbol pages even when file checks pass.
