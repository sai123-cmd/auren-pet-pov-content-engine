# Cat POV Self Evaluation

## What worked

- VLM correctly recognized the footage as low, monochrome animal POV in woodland/grass/building-edge settings.
- Cat-specific highlights differ from dog highlights: quiet scanning, prey tracking, sudden upward attention, brush/nest investigation.
- The diary reads as a quiet first-person cat narrative rather than a dog-style outing.

## Limitations

- Source material is only 3 clips x 5 seconds, 480x360, monochrome scientific footage.
- VLM sometimes says dog/animal instead of cat because the wearer is not visible and the footage is old low-res grayscale.
- Audio exists but is not semantically rich enough here; future cat workflow needs bell/meow/owner voice/prey sound classifiers.

## Next optimization

- Collect longer modern cat collar-cam samples with indoor shelves, windows, owner interaction, meow/bell audio, and outdoor stalking.
- Add cat-specific label schema: stalk, perch, hide, window_watch, threshold_pause, sudden_attention, prey_track, owner_call.
- Use image-reference grounded comic generation exactly as required for dog outputs.