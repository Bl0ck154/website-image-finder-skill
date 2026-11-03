# Measuring whether the skill helps

The offline evaluator reports operational statistics from saved searches. It does not estimate artistic quality, human preference, user demand or image licensing.

## A repeatable comparison

Use the same site, agent and selection criteria for each approach. Suggested tasks are finding a homepage photograph for a coworking website, a licensed article illustration and a small set of tourism photos.

For each task, compare two workflows: this skill, and the agent's native image/web search without this skill. Alternate the order across tasks to limit practice effects. Record the time a human spends reviewing images, the number of usable candidates, layout suitability, the original source's usage rights, and whether a finished image was actually inserted.

Publish a speed-up or quality percentage only when both workflows have been measured with the same criteria. Successful downloading is not proof of visual relevance.

## Recorded operational metrics

~~~sh
python3 <SKILL_DIR>/scripts/skill.py evaluate --root . --latest 10
~~~

Or compare chosen runs:

~~~sh
python3 <SKILL_DIR>/scripts/skill.py evaluate --root . \
  --run .image-search/<run-one> --run .image-search/<run-two> \
  --output .image-search/evaluations/comparison.json
~~~

The report includes runs with a usable download, the number of search-provider function invocations, median first-search duration, candidate failures and duplicates, and cache reuse. Search-provider invocation counts exclude individual image downloads and HTTP library retries. Measured elapsed time covers initial search and first-batch work, excluding subsequent review and extra batches.

Older caches do not contain all metrics, so those fields are marked missing rather than estimated. Sensitive image URLs are omitted from the evaluation output, which should remain under .image-search/.

## Measuring actual interest

Stars, forks, GitHub issues and installation reports show attention, but are not proof of user benefit. The most useful evidence is an independent user completing a website task and describing how the skill helped or got in the way. Request a reproducible bug description and sanitized environment details, never API keys or an unredacted search cache.
