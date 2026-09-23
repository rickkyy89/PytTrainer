"""Geometria pura del selettore di ritaglio dei frame.

Le coordinate sono quelle Kivy (origine in basso a sinistra); soltanto la
conversione finale in percentuali inverte l'asse verticale dell'immagine.
Il modulo non importa Kivy, così geometria e gesture restano testabili anche
in ambienti headless.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Rect:
    left: float
    bottom: float
    right: float
    top: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom


@dataclass(frozen=True)
class CropInsets:
    sinistra: float
    alto: float
    destra: float
    basso: float


def _rect_valido(rect: Rect, nome: str) -> None:
    valori = (rect.left, rect.bottom, rect.right, rect.top)
    if not all(math.isfinite(v) for v in valori) or rect.width <= 0 or rect.height <= 0:
        raise ValueError(f"{nome} deve avere dimensioni positive.")


def _misura_minima(min_size) -> tuple[float, float]:
    if isinstance(min_size, (int, float)):
        larghezza = altezza = float(min_size)
    else:
        try:
            larghezza, altezza = (float(v) for v in min_size)
        except (TypeError, ValueError) as exc:
            raise ValueError("min_size deve essere un numero o una coppia.") from exc
    if (not math.isfinite(larghezza) or not math.isfinite(altezza)
            or larghezza <= 0 or altezza <= 0):
        raise ValueError("min_size deve avere dimensioni positive.")
    return larghezza, altezza


def _percentuale_massima(max_crop_pct: float) -> float:
    valore = float(max_crop_pct)
    if not math.isfinite(valore) or valore < 0 or valore >= 50:
        raise ValueError("max_crop_pct deve essere compreso tra 0 e 50.")
    return valore


def displayed_image_rect(viewport: Rect, image_size: tuple[float, float], *,
                         fit_mode="contain") -> Rect:
    """Restituisce il rettangolo letterbox centrato per ``fit_mode='contain'``."""
    _rect_valido(viewport, "viewport")
    if fit_mode != "contain":
        raise ValueError(f"fit_mode non supportato: {fit_mode}")
    try:
        image_width, image_height = (float(v) for v in image_size)
    except (TypeError, ValueError) as exc:
        raise ValueError("image_size deve essere una coppia positiva.") from exc
    if (not math.isfinite(image_width) or not math.isfinite(image_height)
            or image_width <= 0 or image_height <= 0):
        raise ValueError("image_size deve avere dimensioni positive.")
    scala = min(viewport.width / image_width, viewport.height / image_height)
    larghezza = image_width * scala
    altezza = image_height * scala
    left = viewport.left + (viewport.width - larghezza) / 2
    bottom = viewport.bottom + (viewport.height - altezza) / 2
    return Rect(left, bottom, left + larghezza, bottom + altezza)


def _intervallo_con_minimo(a: float, b: float, minimo: float,
                           limite_a: tuple[float, float],
                           limite_b: tuple[float, float]) -> tuple[float, float]:
    a = min(max(a, limite_a[0]), limite_a[1])
    b = min(max(b, limite_b[0]), limite_b[1])
    if b - a >= minimo:
        return a, b
    centro = (a + b) / 2
    a = centro - minimo / 2
    b = centro + minimo / 2
    if a < limite_a[0]:
        b += limite_a[0] - a
        a = limite_a[0]
    if b > limite_b[1]:
        a -= b - limite_b[1]
        b = limite_b[1]
    a = min(max(a, limite_a[0]), limite_a[1])
    b = min(max(b, limite_b[0]), limite_b[1])
    if b - a < minimo - 1e-9:
        raise ValueError("min_size supera lo spazio di ritaglio disponibile.")
    return a, b


def clamp_crop_rect(selection: Rect, image_rect: Rect, *, min_size,
                    max_crop_pct=45.0) -> Rect:
    """Limita selezione, dimensione minima e ritaglio massimo per ciascun lato."""
    _rect_valido(selection, "selection")
    _rect_valido(image_rect, "image_rect")
    min_width, min_height = _misura_minima(min_size)
    massimo = _percentuale_massima(max_crop_pct) / 100
    if min_width > image_rect.width or min_height > image_rect.height:
        raise ValueError("min_size supera le dimensioni dell'immagine.")
    left, right = _intervallo_con_minimo(
        selection.left, selection.right, min_width,
        (image_rect.left, image_rect.left + massimo * image_rect.width),
        (image_rect.right - massimo * image_rect.width, image_rect.right),
    )
    bottom, top = _intervallo_con_minimo(
        selection.bottom, selection.top, min_height,
        (image_rect.bottom, image_rect.bottom + massimo * image_rect.height),
        (image_rect.top - massimo * image_rect.height, image_rect.top),
    )
    return Rect(left, bottom, right, top)


def crop_percentages_from_rect(image_rect: Rect, selection: Rect, *,
                               max_crop_pct=45.0) -> CropInsets:
    """Converte la selezione Kivy Y-up negli inset immagine Y-down."""
    _rect_valido(image_rect, "image_rect")
    _rect_valido(selection, "selection")
    massimo = _percentuale_massima(max_crop_pct)

    def limita(valore):
        valore = min(max(float(valore), 0.0), massimo)
        if math.isclose(valore, 0.0, abs_tol=1e-7):
            return 0.0
        if math.isclose(valore, massimo, abs_tol=1e-7):
            return massimo
        return valore

    return CropInsets(
        limita(100 * (selection.left - image_rect.left) / image_rect.width),
        limita(100 * (image_rect.top - selection.top) / image_rect.height),
        limita(100 * (image_rect.right - selection.right) / image_rect.width),
        limita(100 * (selection.bottom - image_rect.bottom) / image_rect.height),
    )


def rect_from_crop_percentages(image_rect: Rect, crop: CropInsets) -> Rect:
    """Inversa di :func:`crop_percentages_from_rect`."""
    _rect_valido(image_rect, "image_rect")
    valori = (crop.sinistra, crop.alto, crop.destra, crop.basso)
    if not all(math.isfinite(float(v)) and 0 <= float(v) <= 45 for v in valori):
        raise ValueError("Le percentuali di ritaglio devono essere tra 0 e 45.")
    result = Rect(
        image_rect.left + image_rect.width * float(crop.sinistra) / 100,
        image_rect.bottom + image_rect.height * float(crop.basso) / 100,
        image_rect.right - image_rect.width * float(crop.destra) / 100,
        image_rect.top - image_rect.height * float(crop.alto) / 100,
    )
    _rect_valido(result, "selection")
    return result


def hit_test_crop(selection: Rect, point, *, handle_radius):
    """Restituisce prima l'angolo più vicino, poi il corpo della selezione."""
    _rect_valido(selection, "selection")
    radius = float(handle_radius)
    if not math.isfinite(radius) or radius < 0:
        raise ValueError("handle_radius non può essere negativo.")
    try:
        x, y = (float(v) for v in point)
    except (TypeError, ValueError) as exc:
        raise ValueError("point deve essere una coppia.") from exc
    angoli = {
        "top_left": (selection.left, selection.top),
        "top_right": (selection.right, selection.top),
        "bottom_left": (selection.left, selection.bottom),
        "bottom_right": (selection.right, selection.bottom),
    }
    vicini = [(math.hypot(x - cx, y - cy), nome)
              for nome, (cx, cy) in angoli.items()
              if math.hypot(x - cx, y - cy) <= radius]
    if vicini:
        return min(vicini, key=lambda item: item[0])[1]
    if selection.left <= x <= selection.right and selection.bottom <= y <= selection.top:
        return "body"
    return None


def drag_crop_rect(selection: Rect, target, dx, dy, image_rect: Rect, *,
                   min_size, max_crop_pct=45.0) -> Rect:
    """Applica lo spostamento totale della gesture alla selezione iniziale."""
    _rect_valido(selection, "selection")
    _rect_valido(image_rect, "image_rect")
    min_width, min_height = _misura_minima(min_size)
    massimo = _percentuale_massima(max_crop_pct) / 100
    selection = clamp_crop_rect(selection, image_rect, min_size=(min_width, min_height),
                                max_crop_pct=max_crop_pct)
    dx, dy = float(dx), float(dy)
    if not math.isfinite(dx) or not math.isfinite(dy):
        raise ValueError("Lo spostamento deve essere finito.")
    if target == "body":
        dx = min(max(dx, image_rect.left - selection.left,
                     (image_rect.right - massimo * image_rect.width) - selection.right),
                 image_rect.right - selection.right,
                 (image_rect.left + massimo * image_rect.width) - selection.left)
        dy = min(max(dy, image_rect.bottom - selection.bottom,
                     (image_rect.top - massimo * image_rect.height) - selection.top),
                 image_rect.top - selection.top,
                 (image_rect.bottom + massimo * image_rect.height) - selection.bottom)
        return Rect(selection.left + dx, selection.bottom + dy,
                    selection.right + dx, selection.top + dy)

    lim_left = image_rect.left + massimo * image_rect.width
    lim_right = image_rect.right - massimo * image_rect.width
    lim_bottom = image_rect.bottom + massimo * image_rect.height
    lim_top = image_rect.top - massimo * image_rect.height
    if target == "top_left":
        return Rect(min(max(selection.left + dx, image_rect.left),
                        min(lim_left, selection.right - min_width)),
                    selection.bottom, selection.right,
                    min(max(selection.top + dy, max(lim_top, selection.bottom + min_height)),
                        image_rect.top))
    if target == "top_right":
        return Rect(selection.left, selection.bottom,
                    min(max(selection.right + dx, max(lim_right, selection.left + min_width)),
                        image_rect.right),
                    min(max(selection.top + dy, max(lim_top, selection.bottom + min_height)),
                        image_rect.top))
    if target == "bottom_left":
        return Rect(min(max(selection.left + dx, image_rect.left),
                        min(lim_left, selection.right - min_width)),
                    min(max(selection.bottom + dy, image_rect.bottom),
                        min(lim_bottom, selection.top - min_height)),
                    selection.right, selection.top)
    if target == "bottom_right":
        return Rect(selection.left,
                    min(max(selection.bottom + dy, image_rect.bottom),
                        min(lim_bottom, selection.top - min_height)),
                    min(max(selection.right + dx, max(lim_right, selection.left + min_width)),
                        image_rect.right), selection.top)
    raise ValueError(f"Target di trascinamento non valido: {target}")
