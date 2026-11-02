# Contributing

Bug reports, documentation fixes, and small compatibility improvements are welcome.

## Before opening an issue

Search existing issues first. For a broken search backend, include your operating system, Python version, installed `ddgs` version, the exact command and a **redacted** error message. Explain which backend was requested and which backend actually served the results, if known.

Do not attach API keys, browser sessions, image files you lack permission to redistribute, or unredacted search logs.

## Running checks

```sh
python -m pip install -r requirements.txt
python -m compileall -q scripts tests
python -m unittest discover -s tests -v
python scripts/skill.py --version
```

These are the checks used by CI. Changes that depend on live provider responses should also document the provider version and any rate-limit or availability assumptions; offline tests should not rely on live search services.

## Pull requests

- Keep changes focused; explain the real problem, how you reproduced it, and what you tested.
- Update `SKILL.md` or `README.md` when commands or behavior change.
- Preserve image source metadata and license warnings. A search result is not evidence that an image can legally be republished.
- Never claim a fallback provider was used unless the runtime actually confirmed it.

The repository uses the [MIT license](LICENSE). By submitting a contribution, you agree to license it under the same terms.
