# Data Sources

## Dog POV Example

The dog POV example outputs were generated from local user-provided test videos. Raw dog source videos are not included in this repository.

## Cat POV Example

The cat POV example uses openly licensed Wikimedia Commons files:

- `Video recorded by a freely roaming cat - pbio.0040209.sv001.ogv`
- `Video recorded by a freely roaming cat - pbio.0040209.sv002.ogv`
- `Video recorded by a freely roaming cat - pbio.0040209.sv003.ogv`

License: Creative Commons Attribution 2.5.

Attribution: Lesica N, Weng C, Jin J, Yeh C, Alonso J, Stanley G (2006), supplementary videos from the referenced PLOS Biology article.

Commons category:

https://commons.wikimedia.org/wiki/Category:Videos_recorded_by_cats

Notes:

- Raw cat source clips are not committed.
- The example outputs are generated derivatives for workflow evaluation.
- Longer modern cat collar-cam footage is still needed for better product validation.

## CatCam Iteration Source

A local v2 cat workflow was also tested with two clips from the Zenodo CatCam dataset:

- `CatCam - complete dataset`
- Zenodo record: https://zenodo.org/records/46481
- Reference paper: Betsch BY, Einhauser W, Kording KP, Konig P (2004), "The World from a Cat's Perspective - Statistics of Natural Videos"

Important licensing boundary:

- The CatCam record is licensed CC BY-NC 2.0 and the readme says the data is freely available for academic use only.
- It is useful for local algorithm validation of cat-mounted POV behavior.
- Do not commit CatCam raw clips or derived media into an MIT/commercial demo repository unless a compatible license or permission is obtained.

Recommended use:

- Use CatCam locally to stress-test cat-specific recognition: low camera height, field/soil rows, distant humans, leaf-floor movement, sudden attention, and brush inspection.
- Keep open-source examples based on user-owned media or clearly compatible open-license material.
