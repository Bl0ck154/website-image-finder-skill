# Changelog

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
