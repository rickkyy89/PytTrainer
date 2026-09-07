"""Repair and regenerate the branded Android artwork from the tracked assets."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent.parent
FONT_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")
FONT_BOLD_ITALIC = Path(r"C:\Windows\Fonts\arialbi.ttf")
ASSETS = (
    (ROOT / "assets" / "android" / "icon.png", (170, 895, 1085, 1090), 915, 170, "PNG"),
    (ROOT / "assets" / "android" / "presplash_portrait.jpg", (210, 860, 735, 990), 885, 92, "JPEG"),
    (ROOT / "assets" / "android" / "res" / "drawable-land" / "presplash.jpg",
     (580, 535, 1090, 650), 555, 82, "JPEG"),
)


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _paint_word(image: Image.Image, text: str, xy: tuple[int, int], font: ImageFont.FreeTypeFont,
                top: tuple[int, int, int], bottom: tuple[int, int, int]) -> int:
    """Paint one word with the teal-to-white vertical brand gradient."""
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).text(xy, text, font=font, fill=255, stroke_width=0)
    box = mask.getbbox()
    if box is None:
        return xy[0]
    gradient = Image.new("RGBA", image.size)
    pixels = gradient.load()
    height = max(box[3] - box[1], 1)
    for y in range(box[1], box[3]):
        ratio = (y - box[1]) / height
        color = tuple(round(a + (b - a) * ratio) for a, b in zip(top, bottom)) + (255,)
        for x in range(box[0], box[2]):
            pixels[x, y] = color
    image.paste(gradient, (0, 0), mask)
    return xy[0] + int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(text, font=font))


def _redraw_brand(path: Path, erase_box: tuple[int, int, int, int], y: int, size: int,
                  image_format: str) -> None:
    with Image.open(path) as original:
        image = original.convert("RGBA")

    # A feathered dark panel removes the erroneous rasterized lettering while
    # retaining the surrounding illustration and its low-light appearance.
    ImageDraw.Draw(image).rounded_rectangle(erase_box, radius=18, fill=(2, 7, 9, 255))
    panel = Image.new("L", image.size)
    ImageDraw.Draw(panel).rounded_rectangle(erase_box, radius=18, fill=255)
    panel = panel.filter(ImageFilter.GaussianBlur(radius=14))
    shadow = Image.new("RGBA", image.size, (2, 7, 9, 0))
    shadow.putalpha(panel)
    image.alpha_composite(shadow)

    py_font = _font(FONT_BOLD_ITALIC, size)
    trainer_font = _font(FONT_BOLD, size)
    measure = ImageDraw.Draw(Image.new("L", (1, 1)))
    py_width = int(measure.textlength("py", font=py_font))
    trainer_width = int(measure.textlength("Trainer", font=trainer_font))
    x = (image.width - py_width - trainer_width) // 2
    next_x = _paint_word(image, "py", (x, y), py_font, (48, 244, 228), (0, 205, 190))
    _paint_word(image, "Trainer", (next_x, y), trainer_font, (244, 247, 249), (190, 199, 207))

    if image_format == "JPEG":
        image.convert("RGB").save(path, format=image_format, quality=95, progressive=True)
    else:
        image.save(path, format=image_format)


def build_brand_assets() -> tuple[Path, ...]:
    """Correct the pyTrainer wordmark in every shipped Android artwork file."""
    for path, erase_box, y, size, image_format in ASSETS:
        _redraw_brand(path, erase_box, y, size, image_format)
    return tuple(path for path, *_ in ASSETS)


if __name__ == "__main__":
    for asset in build_brand_assets():
        print(f"Rigenerata {asset}")
