"""Test headless della geometria del selettore di ritaglio."""

import pytest

from kivy_app.crop_layout import (
    CropInsets, Rect, clamp_crop_rect, crop_percentages_from_rect,
    displayed_image_rect, drag_crop_rect, hit_test_crop,
    rect_from_crop_percentages,
)


def test_contain_letterbox_orizzontale_e_verticale():
    assert displayed_image_rect(Rect(0, 0, 200, 200), (200, 100)) == Rect(0, 50, 200, 150)
    assert displayed_image_rect(Rect(0, 0, 200, 200), (100, 200)) == Rect(50, 0, 150, 200)


def test_percentuali_invertono_esattamente_asse_y():
    image = Rect(10, 20, 210, 120)
    selection = Rect(30, 35, 150, 100)
    assert crop_percentages_from_rect(image, selection) == CropInsets(10, 20, 30, 15)


def test_round_trip_percentuali_rettangolo():
    image = Rect(13, 27, 417, 233)
    crop = CropInsets(7.5, 12.25, 31.5, 4.75)
    selection = rect_from_crop_percentages(image, crop)
    result = crop_percentages_from_rect(image, selection)
    assert result.sinistra == pytest.approx(crop.sinistra)
    assert result.alto == pytest.approx(crop.alto)
    assert result.destra == pytest.approx(crop.destra)
    assert result.basso == pytest.approx(crop.basso)


def test_clamp_tutti_i_bordi_e_cap_quarantacinque_percento():
    image = Rect(0, 0, 100, 100)
    assert clamp_crop_rect(Rect(-20, -10, 130, 140), image, min_size=5) == image
    result = clamp_crop_rect(Rect(90, 90, 95, 95), image, min_size=5)
    crop = crop_percentages_from_rect(image, result)
    assert crop.sinistra <= 45 and crop.alto <= 45
    assert crop.destra <= 45 and crop.basso <= 45


@pytest.mark.parametrize("target", (
    "top_left", "top_right", "bottom_left", "bottom_right",
))
def test_dimensione_minima_su_ogni_angolo(target):
    image = Rect(0, 0, 100, 100)
    start = Rect(20, 20, 80, 80)
    result = drag_crop_rect(start, target, 1000, 1000, image, min_size=25)
    assert result.width >= 25
    assert result.height >= 25


def test_drag_corpo_preserva_dimensione_e_si_ferma_ai_limiti():
    image = Rect(0, 0, 100, 100)
    start = Rect(10, 20, 70, 80)
    result = drag_crop_rect(start, "body", 1000, -1000, image, min_size=10)
    assert result.width == start.width
    assert result.height == start.height
    assert result.right == image.right
    assert result.bottom == image.bottom


def test_hit_test_angoli_prima_del_corpo_vicino_e_fuori():
    selection = Rect(10, 10, 30, 30)
    assert hit_test_crop(selection, (11, 29), handle_radius=5) == "top_left"
    # Entrambi nel raggio: prevale quello geometricamente più vicino.
    assert hit_test_crop(selection, (19, 30), handle_radius=12) == "top_left"
    assert hit_test_crop(selection, (20, 20), handle_radius=3) == "body"
    assert hit_test_crop(selection, (50, 50), handle_radius=3) is None


@pytest.mark.parametrize("call", (
    lambda: displayed_image_rect(Rect(0, 0, 0, 10), (10, 10)),
    lambda: displayed_image_rect(Rect(0, 0, 10, 10), (0, 10)),
    lambda: displayed_image_rect(Rect(0, 0, 10, 10), (10, 10), fit_mode="cover"),
    lambda: clamp_crop_rect(Rect(8, 2, 1, 9), Rect(0, 0, 10, 10), min_size=1),
    lambda: crop_percentages_from_rect(Rect(9, 0, 1, 10), Rect(1, 1, 2, 2)),
    lambda: rect_from_crop_percentages(Rect(0, 10, 10, 0), CropInsets(0, 0, 0, 0)),
))
def test_input_non_validi(call):
    with pytest.raises(ValueError):
        call()
