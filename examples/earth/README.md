# Real website example: NASA Blue Marble

Open `index.html` in a browser. This is a small static editorial landing page using one **real, locally optimized** image. The example has no JavaScript, accounts, analytics, image hotlinks or API keys.

## Where this image came from

- Original work: [NASA Blue Marble 2002](https://science.nasa.gov/earth/earth-observatory/the-blue-marble-true-color-global-imagery-at-1km-resolution/)
- File description and public-domain status: [Wikimedia Commons — Blue Marble 2002.jpg](https://commons.wikimedia.org/wiki/File:Blue_Marble_2002.jpg)
- Downloaded thumbnail: [1280-pixel JPEG](https://upload.wikimedia.org/wikipedia/commons/thumb/5/51/Blue_Marble_2002.jpg/1280px-Blue_Marble_2002.jpg)
- Credit: NASA Goddard Space Flight Center; image by Reto Stöckli; enhancements by Robert Simmon
- Rights: marked public domain in the United States on the file page as a NASA-created image. Other usage restrictions and jurisdictional differences may apply. See [NASA media usage guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/).

No NASA logo is used, and the page does not imply NASA endorsement.

## Reproducing the optimization

The actual source was a JPEG at 1280×640 pixels, 149,430 bytes, SHA-256:
`ed48d6b8214261080a24d2760200dfe3cac60fb5b25e09de54fa1362e3265419`.

The file was downloaded to the project's private `.image-search/` directory and converted using the skill's own finalizer:

```sh
python3 scripts/skill.py finalize \
  --root . \
  --input .image-search/demo-source.jpg \
  --output examples/earth/assets/blue-marble.webp \
  --max-width 1280
```

The committed result is a **1280×640 WebP (105,736 bytes)**, verified with Pillow. The page references that local WebP through a relative path and includes descriptive alt text and visible source credit.

The image was selected from a known, documented NASA source for a deterministic demo. **Do not interpret this as a fresh automated search benchmark or proof that every image returned by a search provider is legally reusable.**
