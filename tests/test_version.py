from kivy_app.version import build_number, version_display, version_label, version_name


def test_version_is_exposed_consistently():
    assert version_name() == "0.2.0"
    assert build_number() >= 0
    assert version_label() == f"pyTrainer {version_name()} · build {build_number()}"
    assert version_display() == f"{version_name()} + build {build_number()}"
