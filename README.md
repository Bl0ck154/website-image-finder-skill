# Website Image Finder — Agent Skill

A lightweight Agent Skill for finding, reviewing, optimizing, and integrating public-web images into website projects.

It supports Google Images through SerpApi and DDGS image search as the no-key fallback. Search results are cached once, while image candidates are reviewed in additional batches without repeating the search API request.

## Highlights

- Provider-side filters for layout, size, type, color, time, license, and domains
- Google Images through SerpApi
- DDGS / DuckDuckGo Images fallback without an API key
- Local `results-cache.json` for resume and provenance
- Review batches via compact `candidates-XX.json`
- Dense justified `contact-sheet-XX.jpg` previews
- Next-batch downloads without another search-provider call
- Actual file validation, minimum dimensions, size limits, and duplicate filtering
- WebP/PNG/JPEG finalization with source sidecar metadata
- No virtual environment required

## Install

Copy the `website-image-finder` directory to:

```text
~/.agents/skills/website-image-finder
```

On Windows, run:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.agents\skills\website-image-finder\install.ps1"
```

For SerpApi only, without DDGS:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.agents\skills\website-image-finder\install.ps1" -SerpApiOnly
```

Check the installation:

```powershell
py -3 "$env:USERPROFILE\.agents\skills\website-image-finder\scripts\skill.py" check
```

## DDGS backend verification

DDGS backend availability varies by DDGS version. The skill verifies the actual source returned and does not assume that a requested backend was honored.

The provider chain is:

```text
SerpApi Google Images
  -> DDGS image search when no SerpApi key is configured or the SerpApi request fails
```

DDGS is one fallback provider, not a promise of two independent Bing and DuckDuckGo fallbacks. `--ddgs-backend bing` remains available for DDGS versions that actually provide Bing Images. If the installed DDGS version substitutes another engine, the command records the mismatch and exits with an error.

The search cache records runtime provenance:

```json
{
  "ddgs_version": "9.14.4",
  "requested_backend": "bing",
  "actual_sources": ["DuckDuckGo"]
}
```

In `auto` mode, output describes the behavior as: `DDGS image search using the backends available in the installed DDGS version.`

## Example

```text
Use $website-image-finder.

Find a wide hero photograph for this landing page, review the candidates,
optimize the best usable image to WebP, add it using the project's existing
conventions, preserve the source metadata, and verify the rendered page.
```

Explicit `$website-image-finder` invocation is the most reliable. Compatible agents may also invoke the skill implicitly from its description.

## Output workflow

The first search creates:

```text
.image-search/<run>/
├── results-cache.json
├── candidates-01.json
├── contact-sheet-01.jpg
└── downloaded candidate files
```

If the first batch is unsuitable:

```powershell
py -3 <SKILL_DIR>\scripts\skill.py more --root . --run .image-search\<run> --count 12
```

This uses the existing cache and creates the next batch without calling SerpApi, Bing, or DuckDuckGo search again.

## Copyright notice

Public availability does not grant permission to reuse an image. Search filters and provider metadata are not legal proof of licensing. Verify the original source page and applicable license before publication.

This is an independent community project and is not an official OpenAI product.

## License

MIT
