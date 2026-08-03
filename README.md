# Website Image Finder — Agent Skill

A lightweight Agent Skill for finding, reviewing, optimizing, and integrating public-web images into website projects.

It supports Google Images through SerpApi and an optional DDGS fallback for Bing/DuckDuckGo. Search results are cached once, while image candidates are reviewed in additional batches without repeating the search API request.

## Highlights

- Provider-side filters for layout, size, type, color, time, license, and domains
- Google Images through SerpApi
- Optional DDGS fallback without an API key
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
