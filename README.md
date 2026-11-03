# Website Image Finder — Agent Skill

[![skills.sh](https://skills.sh/b/Bl0ck154/website-image-finder-skill)](https://skills.sh/Bl0ck154/website-image-finder-skill)

Find **real web images for websites with AI coding agents**. Search, compare candidate previews, remove duplicates, optimize website assets, and keep the original source information private.

Works with compatible Agent Skills clients (including Claude Code, Codex, Cursor, and other coding agents that can run Python with network access). Search through Google Images (SerpApi), DDGS, or **Openverse**. No paid search key is required when using DDGS or Openverse. Results can be reviewed in batches without repeating provider searches.

<p align="center"><img src="assets/workflow.gif" alt="Illustrated workflow: image search, candidate review, cache reuse and optimized export" width="800" /></p>
<p align="center"><sub>Illustrative walkthrough with synthetic placeholders, not live search results. Verify image reuse rights before publication.</sub></p>

## Highlights

- Provider filters for layout, size, type, color, time and license; domain allow/block lists are applied locally after search
- Google Images through SerpApi
- DDGS / DuckDuckGo Images with Openverse as a fallback, without an API key
- Openverse for license-oriented image discovery (not automatic legal clearance)
- Local `results-cache.json` for resume and provenance, with opt-in reuse across runs
- Review batches via compact `candidates-XX.json`
- Dense justified `contact-sheet-XX.jpg` previews
- Next-batch downloads without another search-provider call
- Actual file validation, minimum dimensions, size limits, and duplicate filtering
- WebP/PNG/JPEG finalization with **private**, gitignored source metadata
- Explicit SerpApi request budget and sensible exit codes
- Python 3.10+; supports existing environments or virtual environments

## Install

### Using the Skills CLI (recommended)

```sh
npx skills add Bl0ck154/website-image-finder-skill
```

Choose your AI coding agent when prompted. The Skills CLI installs the skill files but **not** their Python dependencies. If your Python environment permits package installation, run `python -m pip install -r <SKILL_DIR>/requirements.txt` with the same Python executable your agent uses for this skill.

For an isolated Python environment on Linux/macOS, substitute the actual installed skill directory:
```sh
SKILL_DIR="$HOME/.agents/skills/website-image-finder"
python3 -m venv "$SKILL_DIR/.venv"
"$SKILL_DIR/.venv/bin/python" -m pip install -r "$SKILL_DIR/requirements.txt"
"$SKILL_DIR/.venv/bin/python" "$SKILL_DIR/scripts/skill.py" check
```

When using an isolated environment, instruct your AI agent to invoke the skill using that environment's Python. On Windows, use `$SKILL_DIR\.venv\Scripts\python.exe` for a virtual environment, or the included PowerShell installer for a user-wide installation.

### Manual installation

Copy the repository contents into a directory named `website-image-finder` at:

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

The provider selection in `--provider auto` mode is:

```text
--license creative-commons -> Openverse
Other searches:
  SerpApi Google Images (when an API key exists)
    -> DDGS (on failures / no results)
    -> Openverse (when DDGS fails or returns no results)
Without an API key: DDGS -> Openverse
```

You may select `--provider openverse` directly. It provides license metadata and uses public API endpoints without a key. Unsupported provider filters fail rather than being silently ignored. Explicit provider choices do not fall back; `--no-provider-fallback` also disables automatic fallback.

DDGS is one fallback provider, not a promise of two independent Bing and DuckDuckGo fallbacks. `--ddgs-backend bing` remains available for DDGS versions that actually provide Bing Images. If the installed DDGS version substitutes another engine, the command records the mismatch and exits with an error.

The search cache records runtime provenance, including the actual DDGS engine used:

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

This uses the existing cache and creates the next batch without calling any search provider again.

To reuse matching search results between separate runs (with identical queries, filters and provider selection), add `--reuse-cache-hours 24` to `search`. This reuses search **metadata**, not old downloaded images. It is opt-in; `0` disables reuse. The default region is `auto` instead of a country-specific locale.

For SerpApi, at most three search requests per run are allowed by default. Multi-query or multi-page searches can raise the cap explicitly with `--max-serpapi-requests N` (up to 15). Each SerpApi page can consume a search credit.

If downloads fail, `search` reports exit code `3` rather than incorrectly claiming complete success; `--batch-size 0` still succeeds when URLs are found. `more` also returns `3` if no additional usable candidates are produced.

## Source metadata, privacy and deployment

The finalizer writes source information to `.image-search/provenance/<asset-relative-path>.source.json` inside your project (not next to `public/images/...`). The repository ignores `.image-search/` in Git. Keep this directory **out of web hosting and version control**: original image URLs can contain temporary signed query parameters. Do not upload search caches to public storage.

Example with a locally downloaded candidate:

```sh
python scripts/skill.py search "cozy modern workspace" --provider openverse --license commercial-modify --root . --batch-size 12
python scripts/skill.py more --root . --run .image-search/<run> --count 12
python scripts/skill.py finalize --root . --cache .image-search/<run>/results-cache.json --candidate 7 --output public/images/hero.webp
```

The agent should inspect the contact sheet, choose a relevant candidate, verify the original source's reuse conditions and integrate the resulting local image with useful alt text. It must not infer permission to publish from the search engine's metadata alone.

## Compatibility and troubleshooting

| Environment | Status / notes |
| --- | --- |
| Windows + Python 3.12 | Covered by offline GitHub Actions tests; PowerShell installer available |
| macOS + Python 3.12 | Covered by offline tests; use pip or a virtual environment |
| Ubuntu + Python 3.10 / 3.13 | Covered by offline tests; use pip or a virtual environment |
| Other AI agents | Compatible with agents that recognize `SKILL.md` and can run Python/network commands |
| Live search providers | External service availability, rates, blocks, and download permissions can vary |

Quick diagnostics: `python scripts/skill.py check`, `python scripts/skill.py search --help`, and the `warnings`/candidate statuses in the run's cache. CI uses mocks and does **not** guarantee live external search.

## Copyright notice

Public availability does not grant permission to reuse an image. Search filters and provider metadata are not legal proof of licensing. Verify the original source page and applicable license before publication.

This is an independent community project and is not an official OpenAI product.

## License

MIT

## Contributing

Bug reports and improvements are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for local checks and privacy guidelines.
