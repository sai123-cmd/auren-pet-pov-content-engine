# Cat POV Iteration Log

## 2026-05-22 Local v3

Goal: expand cat first-person validation beyond the three short Wikimedia Commons clips and test whether the cat-specific workflow remains stable with longer cat-mounted footage.

Local-only source mix:

- 3 Wikimedia Commons / PLOS supplementary clips, CC BY 2.5.
- 5 Zenodo CatCam clips: `movie01`, `movie07`, `movie12`, `movie13`, `movie16`.

License boundary:

- Wikimedia-derived example outputs may be used for open workflow evaluation with attribution.
- CatCam is CC BY-NC / academic-use-only, so CatCam raw media and derived outputs are not committed to this MIT repository.

Run summary:

- 8 source videos.
- 175 heuristic candidate segments.
- 58 MiniMax VLM-reviewed candidates.
- 58 parsed recognition results.
- 8 selected cat-specific highlights.

Generated local outputs:

- `cat_diary_story_v2.md`: continuous first-person cat diary.
- `cat_pov_highlights_v2.csv`: selected highlights and VLM evidence.
- `cat_comic_reference_real_scenes_v2.jpg`: real-frame grounding board.
- `cat_comic_looki_grounded_generated_v4.png`: Looki-like grounded comic render after profile-tag scoring.
- `cat_vlog_story_v2.mp4`: 1280x720 narrative cat POV vlog with AAC audio, about 15.8 seconds.
- `output_quality_report.md/json`: automated output regression report.
- `final_content_cat_v5_profile_canonical`: latest local profile-normalized output set, with `cat_comic_looki_grounded_generated_v5.png`.

What improved:

- More scene diversity: rocks, field rows, human legs in distance, apartment boundary, dry brush, sudden head turn, and ground-level movement.
- The v2 cat builder selected a broader cat-style arc instead of repeating one short clip.
- The vlog renderer handled no-audio scientific footage by creating a silent bed before BGM mixing.
- Automated QA passed for both the cat v3 output and the current dog v2 output after fixing artifact selection priority.
- VLM job preparation now supports a `cat` profile with cat-specific label hints for stalking, hiding, threshold pauses, sudden attention, prey tracking, window watching, and brush inspection.
- Cat content selection now understands cat-profile labels such as `prey_track`, `threshold_pause`, `sudden_attention`, `brush_inspection`, `window_watch`, `perch_or_climb`, and `ground_patrol`.
- MiniMax result parsing now reports `parse_ok` counts explicitly and normalizes free-form model action/event text back into profile label IDs while preserving raw model text.

Remaining gaps:

- Need modern color cat collar-cam clips with owner interaction, indoor shelves, windows, meows, bells, night scenes, and richer audio.
- Need a compatible-license public demo set or user-owned footage for committed cat examples.
- Need automated image-reference generation or API integration so the Looki-like comic can be regenerated deterministically from selected keyframes.
