"""Build the tracked PC ICO from the official Android source asset."""

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "android" / "icon.png"
OUTPUT = ROOT / "assets" / "pc" / "icon.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def build_icon() -> Path:
    """Create a multiresolution ICO and return its absolute path."""
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Icona sorgente non trovata: {SOURCE}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(SOURCE) as source:
        source = source.convert("RGBA")
        largest = source.resize((max(SIZES), max(SIZES)), Image.Resampling.LANCZOS)
        largest.save(
            OUTPUT,
            format="ICO",
            sizes=[(size, size) for size in SIZES],
        )
    return OUTPUT


if __name__ == "__main__":
    print(f"Generata {build_icon()} da {SOURCE} ({', '.join(map(str, SIZES))} px)")
