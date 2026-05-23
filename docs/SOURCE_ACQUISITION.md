# Source Acquisition Policy

AUREN can only become a repeatable product if source footage is tracked with the same care as model outputs. Pet POV media often contains homes, owners, neighbors, voices, GPS-like route clues, and copyrighted platform content.

## Source Tiers

### Tier A: Product / Open Demo

Use for committed examples, public demos, and reproducible tests.

- User-owned footage with explicit permission.
- Public media with a license compatible with the repository and intended demo use.
- Synthetic or generated footage created specifically for AUREN tests.

Requirements:

- Keep attribution metadata.
- Remove private raw source media from the repo unless the owner explicitly wants it included.
- Prefer committing generated outputs, manifests, and small review artifacts rather than raw footage.

### Tier B: Local Algorithm Validation

Use for local model and workflow validation only.

- Academic or non-commercial datasets.
- Research supplementary videos with restrictions.
- Any footage whose license is clear enough for local experimentation but not compatible with public MIT examples.

Requirements:

- Do not commit raw media or derived media.
- Record the source URL, license, and limitation in the local run notes.
- Commit only code improvements and high-level findings.

### Tier C: Authorization Candidates

Do not download into the project until rights are resolved.

- YouTube, TikTok, Reddit, Instagram, Bilibili, Xiaohongshu, and similar platform videos unless the uploader provides a compatible license and platform terms allow the intended use.
- Brand, TV, documentary, or publisher footage.
- Any pet POV clip with people, voices, addresses, license plates, or identifiable homes.

Requirements:

- Save links only in a private candidate list.
- Ask for permission or use platform-approved APIs.
- Do not train, publish, or commit derived examples until permission is clear.

## Minimum Source Manifest Fields

Every run should have a `source_manifest.csv` or equivalent with:

- `source_id`
- `local_filename`
- `species`
- `pov_type`
- `owner`
- `license`
- `source_url`
- `allowed_use`
- `raw_media_committed`
- `derived_media_committed`
- `privacy_notes`
- `attribution`
