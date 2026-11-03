# Changelog

## 0.5.1 (2026-11-03)

- Add image-purpose presets for hero photos, standard photos, logos, icons and illustrations; explicit size overrides remain available.
- Recover from unsuccessful image downloads by trying another free provider within the same attempt budget when automatic fallback is permitted.
- Maintain strict provider choice for license-sensitive searches and keep SerpApi paid access opt-in.
- Pin outgoing HTTP connections to prevalidated public IPs while retaining HTTPS certificate verification; disallow proxies that bypass DNS pinning.
- Preserve original downloaded raster bytes privately, avoiding a second lossy WebP encoding when finalizing.
- Restrict search runs and cached-source selection to the private `.image-search/` directory.
- Expand regression tests for Windows/macOS/Linux and live-test Wikimedia search, downloads, review, finalization and evaluation.

## 0.5.0

- Create a private technical shortlist after each downloaded batch. Scores use measured image dimensions, aspect ratio, search-title overlap and source metadata, with per-factor explanations.
- Add the review command for ranking all downloaded candidates in an existing run. The original candidate search rank remains the identifier used when finalizing a file.
- Add the evaluate command for privacy-safe operational comparisons of cached runs, reporting provider invocations, usable downloads, failures, duplicates, cache hits and available timings.
- Record first-search provider invocations, observed duration and download attempts in new caches.
- Add bounded retries for transient provider server errors (500, 502, 503, 504); do not retry HTTP 429 rate limits automatically.
- Add practical usage examples, a measurement protocol and issue/PR templates for outside contributors.
- Expand tests for ranking, path safety, evaluation metrics and retry settings.

## 0.4.0

- Never select paid SerpApi in automatic search mode, even when an API key exists; explicit `--provider serpapi` remains supported.
- Add Wikimedia Commons as a third no-key image source, alongside DDGS and Openverse.
- Automatically prepare isolated Python dependencies on the first image command when needed; opt out with `WEBSITE_IMAGE_FINDER_AUTO_SETUP=0`.
- Recognize managed Python environments in the `check` command and preserve the manual `setup` option.
- Reuse matching search results for 24 hours by default; opt out with `--reuse-cache-hours 0`.
- Strengthen offline tests for paid-provider isolation, Wikimedia metadata, automatic setup and portability.
- Add local Git ignore rules to protect private image caches and optional project-local dependencies by default.
- Update onboarding, compatibility notes and the skill prompt for a free-first experience.

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
