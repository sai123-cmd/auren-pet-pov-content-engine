# Grounded Comic Generation

The comic product is not a photo filter and not pure text-to-image generation. It is an image-reference grounded redraw: real frames provide the scene, action, and layout evidence; the image model redraws those moments into a polished Looki-like page with small pet-imagination details.

## Why Text-Only Fails

A text prompt can describe "cat in grass" or "dog near river", but it loses the actual POV geometry: camera height, visible paws or collar angle, owner position, waterline, bushes, doorway, lighting, and the odd details that make the event feel real. That is why text-only generation often produces a pleasant but unrelated comic.

## Current Contract

The repository is responsible for deterministic steps:

- select VLM-reviewed highlights,
- pick primary evidence frames,
- create a real-scene reference board,
- write a panel brief that ties every panel to a source segment,
- render a storyboard for internal QA,
- render a user-facing grounded comic page with panel layout, comic treatment, captions, and event-linked imagination,
- evaluate that comic/reference artifacts exist at usable resolution.

The deterministic local renderer is acceptable for pipeline validation and demos, but the highest-quality Looki-like redraw still requires an image-conditioned generation step. The model or product API must see the reference board or per-panel frames. Plain text-to-image is not acceptable for final output.

## Grounded Workflow

1. Segment the source videos and run VLM recognition.
2. Select comic candidates by readable frame, iconic posture, visible subject, event clarity, and story variety.
3. Build a 6-panel evidence board from primary frames.
4. Generate an event-linked imagination plan for each panel.
5. Generate a redraw prompt that names the real events, panel-specific imagination gags, and forbids unrelated invention.
6. Render a local grounded comic page so users never see the storyboard as the final artifact.
7. For production polish, optionally use an image-reference capable model/API to redraw the board as a single comic page.
8. Add controlled captions locally if needed, so model text does not become unreadable.
9. Run output QA and human review against `docs/OUTPUT_STANDARDS.md`.

## Event-Linked Imagination

The imagination layer must be caused by the recognized pet event. Generic cute decorations are not enough.

Examples for cat POV:

- `ground_patrol`: paw-map marks, pebble buttons, low-camera route arrows.
- `prey_track`: whisker radar rings, leaf-rustle marks, a tiny suspicious shadow.
- `threshold_pause`: dashed safe/danger boundary, stealth path, exposure timer.
- `sudden_attention`: ear-alert lightning marks, sky/building signal pings.
- `brush_inspection`: hay secret door, question-mark crumbs, cautious paw reaching in.
- `owner_check_in`: distant human footsteps as oversized map pins.

This is the difference between a competent redraw and a comic: the real frame says where the cat is; the event-linked imagination says what the cat thinks is happening.

## Panel Selection

Good comic panels are often different from vlog clips. A vlog can use motion blur and quick transitions; a comic panel needs a readable single frame with a simple visual idea.

Prefer:

- clear scene geometry,
- one memorable action or reaction,
- visible object/person/animal cue,
- a change in distance or angle from adjacent panels,
- a small punchline or emotional beat.

Avoid:

- six panels from the same-looking ground texture,
- frames where motion makes the event unreadable,
- panel captions that carry the whole meaning while the image shows nothing,
- unrelated fantasy additions that hide the source event,
- generic whisker/scent overlays repeated on every panel without a panel-specific reason.

## Species Notes

Dog comic beats usually work well with water, running, chasing, grass exploration, human greeting, toys, and owner-following.

Cat comic beats are subtler: threshold pauses, sudden attention, field patrol, prey/rustle tracking, hiding inspection, perches, windows, owner check-ins, and quiet surveillance. The comic should make those small moments visible with light imagination such as whisker radar, scent trails, paw-map marks, ear-alert marks, and blank thought bubbles.

## Automation Gap

The open-source pipeline can now prepare the grounded inputs and render a user-facing comic page locally. The remaining production gap is integrating a stable image-reference model/API that can redraw the selected frames with more natural hand-drawn polish without drifting away from the source scene.
