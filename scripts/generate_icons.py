#!/usr/bin/env python3
"""Generate native Windows/macOS/Linux icons from a code-drawn open book.

Requires Pillow in the build job: pip install pillow
The SVG equivalent lives in frontend/public/book-icon.svg.
"""
from pathlib import Path
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "frontend" / "public"


def createIcon(size=1024):
    scale = size / 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def pos(points):
        return [(round(x * scale), round(y * scale)) for x, y in points]

    def stroke(points, color, width=5):
        draw.line(pos(points), fill=color, width=round(width * scale), joint="curve")

    draw.rounded_rectangle((8*scale, 8*scale, 248*scale, 248*scale),
                           radius=54*scale, fill="#192a47")
    draw.polygon(pos([(128, 202), (95, 180), (66, 177), (37, 187),
                      (37, 71), (68, 61), (100, 70), (128, 89),
                      (154, 70), (184, 61), (219, 71), (219, 187),
                      (184, 178), (157, 180)]), fill="#267c82")
    draw.polygon(pos([(128, 185), (105, 168), (73, 161), (43, 169),
                      (43, 64), (78, 54), (109, 65), (128, 83)]), fill="#dceafa")
    draw.polygon(pos([(128, 185), (154, 168), (185, 161), (213, 169),
                      (213, 64), (180, 54), (148, 65), (128, 83)]), fill="#f8fbff")
    stroke([(128, 83), (128, 185)], "#8196b7", 4)
    for y in (91, 112, 133):
        stroke([(57, y), (79, y-3), (101, y+1), (113, y+6)], "#adc0d8", 3)
        stroke([(143, y+6), (156, y+1), (179, y-3), (200, y)], "#adc0d8", 3)
    draw.polygon(pos([(169, 61), (191, 63), (191, 112),
                      (180, 104), (169, 112)]), fill="#28c4b8")
    return image


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    sourceImage = createIcon()
    sourceImage.save(OUTPUT / "book-icon.png", optimize=True)
    sourceImage.save(OUTPUT / "book-icon.ico", format="ICO",
                     sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                            (64, 64), (128, 128), (256, 256)])
    sourceImage.save(OUTPUT / "book-icon.icns", format="ICNS")
    print("Generated code-drawn PNG, ICO, ICNS open-book icons")


if __name__ == "__main__":
    main()
