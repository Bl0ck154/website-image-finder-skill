# Examples for real website work

The skill finds existing photographs and illustrations, provides review grids and exports local images for a website. Confirm reuse rights and attribution on the original source page before publishing.

## Homepage hero photo

Ask your coding agent:

> Find wide photographs of a bright coworking studio for our homepage. Show the candidates, explain the shortlist, check the source and attribution requirements, then add a suitable WebP to the hero.

Use the scripts directly from your website project root if preferred:

~~~sh
python3 <SKILL_DIR>/scripts/skill.py search "bright coworking studio interior" \
  --root . --orientation wide --min-width 1200 --min-height 700 --batch-size 8
~~~

Open the resulting contact-sheet-01.jpg. The first download also creates review-batch-01.json with deterministic technical scores. Those scores cover dimensions, aspect ratio, title overlap and source metadata. They cannot verify subject relevance or visual style.

Review every downloaded candidate across batches:

~~~sh
python3 <SKILL_DIR>/scripts/skill.py review --root . --run .image-search/<run> --top 5
~~~

To finalize, use the candidate's original *search rank*, not its position in the shortlist:

~~~sh
python3 <SKILL_DIR>/scripts/skill.py finalize --root . \
  --cache .image-search/<run>/results-cache.json \
  --candidate 3 --output public/images/home-hero.webp
~~~

## Article illustration with license metadata

~~~sh
python3 <SKILL_DIR>/scripts/skill.py search "forest ecology illustration" \
  --root . --provider openverse --license creative-commons \
  --orientation wide --batch-size 8
~~~

Openverse can supply license information, but its metadata alone does not establish permission to use the file. Check the creator and licensing terms at the original page. Include attribution when required.

## Brand logos and product photos

Use the brand's official media kit or images supplied with permission when possible. Brand marks may involve trademark issues, and a public product photo is not automatically free to republish. The skill does not grant redistribution rights or bypass restricted websites.

## Measuring searches

~~~sh
python3 <SKILL_DIR>/scripts/skill.py evaluate --root . --latest 10
python3 <SKILL_DIR>/scripts/skill.py evaluate --root . --latest 10 \
  --output .image-search/evaluations/last-ten.json
~~~

The evaluation report is private and omits original image URLs. See [Measuring results](EVALUATION.md) before making performance or time-savings claims.
