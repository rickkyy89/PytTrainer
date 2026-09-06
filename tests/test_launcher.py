"""Pure platform-launch seams; no Kivy, pyjnius or Android runtime."""

from pathlib import Path
import sys
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kivy_app import launcher


def test_apri_url_pc_sostituisce_un_vecchio_errore(monkeypatch):
    launcher._ultimo_errore = "vecchio errore PDF"
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    monkeypatch.setattr(launcher.webbrowser, "open", lambda _: False)

    assert not launcher.apri_url("https://drive.google.com/drive/folders/x")
    assert launcher.ultimo_errore() == "Il sistema non ha aperto il collegamento."


def test_condividi_pdf_android_delega_file_assoluto_al_content_bridge(tmp_path):
    pdf = tmp_path / "scheda.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    calls = []

    assert launcher.condividi_pdf(
        pdf, platform="android",
        android_sender=lambda path, title: calls.append((path, title)) or True,
    )

    assert calls == [(str(pdf.resolve()), "Condividi PDF pyTrainer")]


def test_condividi_pdf_pc_apre_col_gestore_predefinito(tmp_path):
    pdf = tmp_path / "scheda.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    opened = []

    assert launcher.condividi_pdf(
        pdf, platform="win32", pc_opener=lambda path: opened.append(path),
    )

    assert opened == [str(pdf.resolve())]


def test_condividi_pdf_rifiuta_file_mancante_e_conserva_errore(tmp_path):
    called = []

    assert not launcher.condividi_pdf(
        tmp_path / "missing.pdf", platform="android",
        android_sender=lambda *args: called.append(args),
    )

    assert called == []
    assert "non esiste" in launcher.ultimo_errore()


def test_condividi_pdf_non_inghiotte_errore_del_launcher(tmp_path):
    pdf = tmp_path / "scheda.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    def broken(_):
        raise OSError("associazione PDF assente")

    assert not launcher.condividi_pdf(pdf, platform="win32", pc_opener=broken)
    assert "associazione PDF assente" in launcher.ultimo_errore()


def test_risorse_android_dichiarano_fileprovider_cache_only():
    spec = (PROJECT_ROOT / "buildozer.spec").read_text(encoding="utf-8")
    manifest = (PROJECT_ROOT / "kivy_app/android/fileprovider/AndroidManifest.xml").read_text(
        encoding="utf-8"
    )
    paths = (PROJECT_ROOT / "kivy_app/android/fileprovider/res/xml/pytrainer_file_paths.xml").read_text(
        encoding="utf-8"
    )

    assert "android.add_aars = kivy_app/android/pytrainer-fileprovider.aar" in spec
    # p4a 2026.05.09 copies add_aars into dist/libs and emits a named AAR
    # dependency, but does not add that directory as a Gradle repository.
    assert "android.add_gradle_repositories = flatDir { dirs 'libs' }" in spec
    assert "${applicationId}.fileprovider" in manifest
    assert 'android:exported="false"' in manifest
    assert 'android:grantUriPermissions="true"' in manifest
    assert '<cache-path name="pdf_exports" path="pdf/"' in paths
    assert "external-path" not in paths

    aar_path = PROJECT_ROOT / "kivy_app/android/pytrainer-fileprovider.aar"
    # ZIP member separators are always '/', regardless of the host OS.  A
    # PowerShell-created archive once stored literal backslashes: Gradle then
    # treated the resource as a root file and AAPT could not resolve @xml/… .
    assert b"res\\xml\\pytrainer_file_paths.xml" not in aar_path.read_bytes()
    with zipfile.ZipFile(aar_path) as aar:
        assert "res/xml/pytrainer_file_paths.xml" in aar.namelist()
        assert not any("\\" in name for name in aar.namelist())
        assert aar.read("AndroidManifest.xml").decode("utf-8-sig") == manifest
        assert aar.read("res/xml/pytrainer_file_paths.xml").decode("utf-8-sig") == paths
