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

## Version 0.5.0: technical review and cross-run cache (2026-11-03)

A fresh temporary project used the public Openverse API with a landscape query, a commercial/modification metadata filter, and one review download.

- First run: 12 unique search results, 1 successfully downloaded image, 1 Openverse search-provider invocation.
- The generated review-batch-01.json contained 1 measurable image with a technical score of 68.5/100 for the observed 1024x768 raster. This is a metadata-based score, not a visual quality or licensing judgement.
- Running review over that cache created review-all.json without a provider request.
- A second matching search within the 24-hour window reused the cache, downloaded a candidate, and recorded 0 new search-provider invocations.
- The evaluator summarized both runs: 2 runs with successful downloads, 2 downloaded candidates, 1 Openverse invocation total, 1 cache reuse. The observed median initial search/first-batch duration was 1.538 seconds on that host at that time.

The temporary checkout and images were removed. The report does not establish time saved over a normal AI agent, independent user adoption, or legal reuse rights.
