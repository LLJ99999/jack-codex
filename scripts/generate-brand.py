#!/usr/bin/env python3
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = Path(r"C:\Windows\Fonts\arialbd.ttf")

def make(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / max(1, 2 * size - 2)
            pixels[x, y] = (round(20 + 16 * t), round(70 + 86 * t), round(128 + 75 * t), 255)
    draw = ImageDraw.Draw(image)
    margin = round(size * 0.055)
    radius = round(size * 0.23)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((margin, margin, size - margin, size - margin), radius=radius, fill=255)
    image.putalpha(mask)
    font = ImageFont.truetype(str(FONT), round(size * 0.62)) if FONT.exists() else ImageFont.load_default()
    box = draw.textbbox((0, 0), "J", font=font, stroke_width=max(1, size // 80))
    width, height = box[2] - box[0], box[3] - box[1]
    draw.text(((size - width) / 2 - box[0], (size - height) / 2 - box[1] - size * 0.025), "J", font=font,
              fill=(255, 255, 255, 255), stroke_width=max(1, size // 80), stroke_fill=(255, 255, 255, 255))
    return image

icon = make(512)
icon.save(ROOT / "build" / "icon.png")
icon.resize((256, 256), Image.Resampling.LANCZOS).save(ROOT / "build" / "icon-256.png")
icon.resize((256, 256), Image.Resampling.LANCZOS).save(ROOT / "src" / "assets" / "brand.png")
icon.save(ROOT / "build" / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Generated Jack brand PNG and ICO assets.")
