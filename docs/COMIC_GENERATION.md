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
- render a fallback storyboard for QA,
- evaluate that comic/reference artifacts exist at usable resolution.

The final Looki-like redraw currently requires an image-conditioned generation step outside the deterministic local renderer. The model or product API must see the reference board or per-panel frames. Plain text-to-image is not acceptable for final output.

## Grounded Workflow

1. Segment the source videos and run VLM recognition.
2. Select comic candidates by readable frame, iconic posture, visible subject, event clarity, and story variety.
3. Build a 6-panel evidence board from primary frames.
4. Generate a redraw prompt that names the real events and forbids unrelated invention.
5. Use an image-reference capable model/API to redraw the board as a single comic page.
6. Add controlled captions locally if needed, so model text does not become unreadable.
7. Run output QA and human review against `docs/OUTPUT_STANDARDS.md`.

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
- unrelated fantasy additions that hide the source event.

## Species Notes

Dog comic beats usually work well with water, running, chasing, grass exploration, human greeting, toys, and owner-following.

Cat comic beats are subtler: threshold pauses, sudden attention, field patrol, prey/rustle tracking, hiding inspection, perches, windows, owner check-ins, and quiet surveillance. The comic should make those small moments visible with light imagination such as whisker radar, scent trails, paw-map marks, ear-alert marks, and blank thought bubbles.

## Automation Gap

The open-source pipeline can now prepare the correct grounded inputs. The remaining production gap is integrating a stable image-reference model/API that can redraw the selected frames without drifting away from the source scene. Until that integration exists, generated comic images are treated as assisted artifacts and are not fully reproducible from code alone.
