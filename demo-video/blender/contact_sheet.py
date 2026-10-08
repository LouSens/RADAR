"""Join the stills of every shot into one sheet, to judge the blocking at a glance."""

import sys
from pathlib import Path

from PIL import Image

stills = Path(__file__).resolve().parent / "stills"
shots = sorted({path.name[:5] for path in stills.glob("shot*.png")})
tiles = [[Image.open(stills / f"{shot}{part}.png").convert("RGB") for part in "abc"] for shot in shots]
width, height = (size // 2 for size in tiles[0][0].size)
sheet = Image.new("RGB", (width * 3, height * len(tiles)), "black")
for row, parts in enumerate(tiles):
    for column, tile in enumerate(parts):
        sheet.paste(tile.resize((width, height)), (column * width, row * height))
target = Path(sys.argv[1]) if len(sys.argv) > 1 else stills / "sheet.png"
sheet.save(target)
print(target, sheet.size)
