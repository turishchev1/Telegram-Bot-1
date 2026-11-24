"""Regenerates assets/banner.png (welcome image) and assets/logo.png (bot profile picture).

Run:  python assets/make_banner.py
To use your own artwork instead, just replace those two PNG files; the bot only needs assets/banner.png.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SCALE = 2  # draw at 2x, shrink at the end for smooth edges


def font(path, size):
    try:
        return ImageFont.truetype(path, size * SCALE)
    except OSError:  # font not installed: fall back to Pillow's built-in font
        return ImageFont.load_default()


def gradient(w, h, c1, c2):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = (x / w * 0.6 + y / h * 0.4)
            px[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
    return img


def bars_and_coin(draw, x0, y0, w, h):
    """Five rising bars and a coin: the 'save more over time' picture."""
    heights = [0.28, 0.42, 0.36, 0.62, 0.86]
    gap = w * 0.06
    bw = (w - gap * 4) / 5
    for i, frac in enumerate(heights):
        bh = h * frac
        x = x0 + i * (bw + gap)
        fill = (255, 255, 255, 235) if i < 4 else (237, 161, 0, 255)
        draw.rounded_rectangle([x, y0 + h - bh, x + bw, y0 + h], radius=bw * 0.18, fill=fill)
    # coin above the last bar
    r = bw * 0.62
    cx = x0 + 4 * (bw + gap) + bw / 2
    cy = y0 + h - h * heights[-1] - r * 1.5
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 255), outline=(237, 161, 0, 255), width=int(r * 0.16))
    f = font(FONT_BOLD, int(r * 1.15 / SCALE))
    draw.text((cx, cy), "$", font=f, fill=(24, 79, 149, 255), anchor="mm")


def banner():
    w, h = 1280 * SCALE, 640 * SCALE
    img = gradient(w, h, (42, 120, 214), (13, 54, 107)).convert("RGBA")
    d = ImageDraw.Draw(img)
    d.text((80 * SCALE, 215 * SCALE), "MoneyMate", font=font(FONT_BOLD, 128), fill=(255, 255, 255, 255), anchor="lm")
    d.text((84 * SCALE, 330 * SCALE), "Track.  Split.  Save.", font=font(FONT_REG, 46), fill=(205, 226, 251, 255), anchor="lm")
    d.rounded_rectangle([84 * SCALE, 400 * SCALE, 400 * SCALE, 408 * SCALE], radius=4 * SCALE, fill=(237, 161, 0, 255))
    d.text((84 * SCALE, 455 * SCALE), "EN  ·  RU  ·  UZ", font=font(FONT_REG, 30), fill=(158, 197, 244, 255), anchor="lm")
    bars_and_coin(d, 770 * SCALE, 130 * SCALE, 430 * SCALE, 400 * SCALE)
    img.convert("RGB").resize((1280, 640), Image.LANCZOS).save(HERE / "banner.png", optimize=True)


def logo():
    w = h = 640 * SCALE
    base = gradient(w, h, (42, 120, 214), (13, 54, 107)).convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], radius=130 * SCALE, fill=255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    d = ImageDraw.Draw(out)
    bars_and_coin(d, 130 * SCALE, 150 * SCALE, 380 * SCALE, 350 * SCALE)
    out.resize((640, 640), Image.LANCZOS).save(HERE / "logo.png", optimize=True)


if __name__ == "__main__":
    banner()
    logo()
    print("wrote", HERE / "banner.png", "and", HERE / "logo.png")
