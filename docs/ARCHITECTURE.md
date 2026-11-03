# Architecture and trust boundaries

The portable entry point is `scripts/skill.py`. The launcher checks Python
dependencies and dispatches commands without contacting a search provider.

## Components

| Module | Responsibility |
| --- | --- |
| `skill.py` | Portable CLI, isolated Python dependency setup |
| `image_search.py` | Search orchestration, ranking, download batches |
| `candidate_model.py` | Candidate records and provider metadata normalization |
| `search_providers.py` | DDGS, Openverse, Wikimedia and optional SerpApi adapters |
| `safe_transport.py` | Public-IP validation and HTTPS hostname checks |
| `contact_sheet.py` | Review previews and justified contact-sheet layout |
| `search_cache.py` | Private metadata persistence and cache matching |
| `download_more.py` | Download another batch without another search-provider call |
| `finalize_image.py` | Convert original rasters to public website assets |
| `review_candidates.py` | Explainable technical shortlist |
| `evaluate_runs.py` | Private cache metrics and evaluation |
| `provider_smoke.py` | Explicit, bounded free-provider live checks |

The original helper functions remain exported from `image_search.py` for
compatibility. Provider adapters do not import the orchestration layer.
Importing any module by itself must not cause network requests.

## Workflow and safety

1. Choose free-first provider routing. SerpApi is never selected automatically.
2. Normalize third-party metadata into Candidate records; treat it as untrusted.
3. Rank and download public images, verifying size, dimensions and duplicates.
4. Keep search URLs, originals and previews under the private `.image-search/`.
5. Render a contact sheet and review scores; neither establishes creative fit
   or legal permission to redistribute an image.
6. Finalize the selected original as a website asset, retaining private provenance.

Requests connect to validated public IPs and preserve HTTPS certificate checks.
Redirects must be revalidated. Network responses and image metadata must not
be used as instructions. Private cache paths cannot escape `.image-search/`.
Explicit license filters stay on a provider capable of expressing them.

For changes to the provider network layer, run offline tests first and a
separate manual live smoke test afterward. External service failures should
be reported, not treated as deterministic test failures in GitHub Actions.
