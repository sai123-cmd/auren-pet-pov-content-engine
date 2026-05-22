# Output Standards

These standards are part of the product definition. A run is not complete until the outputs match these expectations.

## Diary

The diary must read like one complete first-person pet diary.

Required:

- continuous first-person voice,
- amusing pet perspective,
- clear day-level arc,
- highlights woven into prose,
- no scene-by-scene headings in the reading experience,
- no analysis table inside the diary.

Allowed:

- a separate evidence file that lists source segments,
- a JSON version that keeps structured evidence for debugging.

Rejected:

- repeated segment summaries,
- bullet list of events,
- third-person analysis,
- captions pretending to be a diary.

## Comic

The comic target is Looki-like: a polished hand-drawn multi-panel illustration based on real events.

Required:

- each panel is grounded in one or more real evidence frames,
- the rendered panel is redrawn, not photo-filtered,
- real event and scene remain recognizable,
- pet imagination is added lightly and tied to the recognized event: scent trails for tracking, map marks for patrol, danger lines for thresholds, ear-alert marks for sudden attention,
- final text is added locally or in a controlled layout so model text does not become gibberish.

Rejected:

- pure text-to-image scene invention,
- edge-detection or posterize photo filters,
- collage screenshots presented as comics,
- panels that ignore the original scene or event,
- repeated generic "cute cat" overlays that do not express the specific action/event.

Implementation boundary:

- the pipeline may create reference boards, panel briefs, and fallback storyboards deterministically,
- final Looki-like art must use image-reference grounding or another method that preserves the real scene,
- plain text-to-image is useful only for experiments, not accepted as final comic output.

## Vlog

The vlog must feel edited.

Required:

- highlight sequence with narrative rhythm,
- opening hook,
- meaningful middle,
- emotional or funny ending,
- pet-voice captions,
- original ambience retained at a controlled level,
- BGM that supports rhythm,
- video aspect-ratio handling for vertical and horizontal clips.

Rejected:

- simple concatenation,
- identical captions on every clip,
- no music or unbalanced music,
- clips selected only by motion without event understanding.

## Species-Specific Notes

Dogs:

- more outdoor movement, social greeting, running, sniffing, owner-following,
- highlights often involve speed, social contact, exploration, water/grass/toys.

Cats:

- more quiet observation, stalking, hiding, vertical surfaces, thresholds, windows, sudden attention,
- audio may include meows, bells, indoor ambience, owner voice, prey-like sounds,
- highlights may be subtle and should not be judged only by motion.
