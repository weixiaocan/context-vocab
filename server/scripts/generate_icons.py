"""Generate PWA icons for the review app. Run from the server directory."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parents[1] / "app" / "static"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BACKGROUND = (110, 128, 98, 255)  # theme green
FOREGROUND = (255, 255, 255, 255)
GLYPH = "词"

FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_icon(size: int, filename: str, glyph_ratio: float) -> None:
    image = Image.new("RGBA", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(image)
    font = load_font(int(size * glyph_ratio))
    bbox = draw.textbbox((0, 0), GLYPH, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = (size - width) / 2 - bbox[0]
    y = (size - height) / 2 - bbox[1]
    draw.text((x, y), GLYPH, font=font, fill=FOREGROUND)
    image.save(OUT_DIR / filename)
    print("wrote", OUT_DIR / filename)


make_icon(192, "icon-192.png", 0.62)
make_icon(512, "icon-512.png", 0.62)
make_icon(512, "icon-maskable-512.png", 0.5)
