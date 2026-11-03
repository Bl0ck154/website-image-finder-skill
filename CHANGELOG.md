# Changelog

## 0.3.0

- Added Openverse search with source-license metadata and a no-key automatic fallback.
- Route Creative Commons searches to Openverse in automatic mode; stop treating DDGS as a verified CC filter.
- Default to region `auto` rather than `lt-lt`; omit fixed Google country/language settings and use DDGS worldwide routing.
- Save source provenance in private, gitignored `.image-search/provenance/` instead of alongside public website assets.
- Return non-success for searches or cached batches that download no usable images.
- Retry failed and undersized candidates with optional minimum-size overrides.
- Add opt-in cross-run search cache reuse (`--reuse-cache-hours`) and an explicit SerpApi request budget.
- Test providers, source safety, Windows, macOS and Ubuntu with expanded offline CI.
- Document installation, provider limitations, privacy, licensing and troubleshooting.

## 0.2.1

- Record the installed DDGS version, requested backend, and actual image-search sources in `results-cache.json`.
- Verify the DDGS engine actually used instead of assuming the CLI backend request was honored.
- Fail clearly when an explicitly requested DDGS backend returns results from another engine.
- Report `auto` mode as DDGS image search using the backends available in the installed DDGS version.
- Label DDGS candidates by the provider actually used rather than the requested backend.

## 0.2.0

- Fixed command dispatch on Windows when Python is installed under a path containing spaces.
- Added persistent search-result caching in `results-cache.json`.
- Added `more` to download later review batches without another provider search.
- Added compact `candidates-XX.json` files for agent review.
- Added `urls.json` for URL-only searches.
- Replaced the fixed white-cell contact sheet with a dense justified gallery.
- Increased default search coverage while keeping downloads batched.
- Added metadata-based size rejection before network download when dimensions are known.
- Removed the product-image ranking penalty.
- Replaced project-specific examples with neutral website examples.
