# Live Openverse smoke test

This is a record of a real search and asset-finalization run on 2026-11-03 using the v0.3.0 development branch. It is not a performance benchmark. Search availability, result ranking, file sizes and permissions can change.

## What was run

The following commands use an isolated, temporary project directory and Python with requests and Pillow installed:

```sh
python scripts/skill.py --version
python scripts/skill.py search "forest lake landscape" \
  --provider openverse --license commercial-modify \
  --root . --out .image-search/live \
  --max-results 12 --batch-size 1 --max-attempts 5 \
  --min-width 400 --min-height 300
# Select the downloaded candidate rank from .image-search/live/results-cache.json
python scripts/skill.py finalize --root . \
  --cache .image-search/live/results-cache.json \
  --candidate <downloaded-rank> \
  --output public/images/smoke.webp
```

## Observed result

- Search provider: Openverse (HTTP API query with license metadata).
- Unique results: 12.
- First review batch: 1 candidate downloaded in 1 network attempt.
- Outputs: candidates JSON, contact sheet JPEG, final WebP image.
- Final WebP file: 178,402 bytes in this run.
- Source metadata: written under `.image-search/provenance/public/images/smoke.webp.source.json`.
- No `public/images/smoke.webp.source.json` was created.

The image itself is intentionally not committed: a search result's license metadata is not sufficient to confirm redistribution rights. Verify attribution and licensing at the original source before placing an image on a production website.

## Testing scope

GitHub Actions runs offline tests on Ubuntu, macOS and Windows. Those tests use mocks instead of paying for live provider requests. The smoke test above independently exercised a real Openverse search, remote image download and local output finalization in a temporary checkout, which was removed afterward.
