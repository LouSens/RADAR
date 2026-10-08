"""Cut the app's cards out of the photographed pages, for the faces of the glass cards.

    uv run python scripts/cards.py        (from demo-video/)

Each card is a rectangle of a still in public/desk, given in the page's own pixels (the
stills are twice that). The stills show the example portfolio and recorded market data
only: see scripts/capture.mjs.
"""

from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent.parent
SCALE = 2

# name: (still, left, top, width, height)
CARDS = {
    "range": ("range", 293, 159, 1118, 480),
    "risk": ("risk", 293, 159, 738, 310),
}

for name, (still, left, top, width, height) in CARDS.items():
    page = Image.open(HERE / "public" / "desk" / f"{still}.png").convert("RGB")
    box = (left * SCALE, top * SCALE, (left + width) * SCALE, (top + height) * SCALE)
    out = HERE / "public" / "cards" / f"{name}.png"
    page.crop(box).save(out)
