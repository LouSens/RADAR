"""Lay stills side by side on one sheet: python scripts/sheet.py out/look/sheet.png 3 a.png b.png ..."""
import sys
from PIL import Image, ImageDraw

out, cols, names = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
w = 1920 // cols if cols > 2 else 960
h = w * 9 // 16
rows = (len(names) + cols - 1) // cols
sheet = Image.new("RGB", (cols * w, rows * h), "#090a0e")
for i, name in enumerate(names):
    still = Image.open(name).convert("RGB").resize((w, h), Image.LANCZOS)
    ImageDraw.Draw(still).text((10, 8), name.replace("\\", "/").split("/")[-1][:-4], fill="#ffff00")
    sheet.paste(still, ((i % cols) * w, (i // cols) * h))
sheet.save(out)
