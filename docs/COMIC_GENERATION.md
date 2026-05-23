# Grounded Comic Generation

The comic product is not a photo filter and not pure text-to-image generation. It is an image-reference grounded redraw: real frames provide the scene, action, and layout evidence; the image model redraws those moments into a polished Looki-like page with small pet-imagination details.

## Why Text-Only Fails

A text prompt can describe "dog near river", but it loses the actual POV geometry: camera height, visible paws or collar angle, owner position, waterline, bushes, doorway, lighting, and the odd details that make the event feel real. That is why text-only generation often produces a pleasant but unrelated comic.

## Current Contract

The repository is responsible for deterministic steps:

- select VLM-reviewed highlights,
- pick primary evidence frames,
- create a real-scene reference board,
- write a panel brief that ties every panel to a source segment,
- render a storyboard for internal QA,
- render a draft grounded comic layout for internal QA,
- evaluate that comic/reference artifacts exist at usable resolution.

The deterministic local renderer is acceptable for pipeline validation only. The user-facing Looki-like redraw requires an image-conditioned generation step or equivalent mature redraw process. The model or product API must see the reference board or per-panel frames. Plain text-to-image is not acceptable for final output.

## POV Lock

Grounding is not enough if the redraw changes camera position. A valid POV comic must preserve the source frame's camera angle, horizon, object scale, occlusion, and visible subject boundaries. Do not add a recurring pet avatar, ears, paws, face, whiskers, or body unless that exact element is already visible in that panel's source frame. Do not convert collar-cam or first-person footage into third-person, over-the-shoulder, or cinematic external camera shots.

The pipeline should keep a `pov_lock_qa` artifact that is rendered directly from exact source frames. This is an internal perspective contract, not a user-facing comic. Do not present it as final content. A prettier generated image is still rejected if it drifts away from the POV QA artifact.

## Grounded Workflow

1. Segment the source videos and run VLM recognition.
2. Select comic candidates by readable frame, iconic posture, visible subject, event clarity, and story variety.
3. Build a 6-panel evidence board from primary frames.
4. Generate an event-linked imagination plan for each panel.
5. Generate a redraw prompt that names the real events, panel-specific imagination gags, and forbids unrelated invention.
6. Render a local POV QA page from exact source frames for internal perspective review only.
7. Use an image-reference capable model/API to redraw the board as a mature single comic page, while preserving the POV-locked composition.
8. Add controlled captions locally if needed, so model text does not become unreadable.
9. Run output QA and human review against `docs/OUTPUT_STANDARDS.md`.

## Event-Linked Imagination

The imagination layer must be caused by the recognized pet event. Generic cute decorations are not enough.

Examples for dog POV:

- `grass_exploration`: grass, leaves, and scent trails become a readable little discovery.
- `water_adventure`: splashes, shoreline, and wet light carry the joke or emotion.
- `human_connection`: owner legs, leash, hands, or footsteps stay in the real scene, not UI pins.
- `animal_social_moment`: another animal becomes the focus of greeting, curiosity, or surprise.
- `search_or_inspect`: objects, bushes, wheels, doors, or benches become a small mystery grounded in the frame.
- `new_scene_discovery`: a doorway, path, park opening, or river reveal gets a visual payoff.

This is the difference between a competent redraw and a comic: the real frame says where the pet is; the event-linked imagination says what the pet thinks is happening. Do not use radar circles, warning triangles, route maps, or debug icons in the final page.

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

## Dog Notes

Dog comic beats usually work well with water, running, chasing, grass exploration, human greeting, toys, and owner-following.

## Automation Gap

The open-source pipeline can now prepare the grounded inputs and an internal draft. The remaining production gap is integrating a stable image-reference model/API that can redraw the selected frames into mature hand-drawn comic art without drifting away from the source scene.
