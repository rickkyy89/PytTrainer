"""Open or share a URL with the platform mechanism (ticket 08).

PC uses the default browser; Android fires native ACTION_VIEW /
ACTION_SEND intents through pyjnius (imported lazily so the module
stays importable everywhere). ACTION_VIEW is tried first without
chooser so an installed YouTube app receives watch URLs directly.
"""

from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote

_ultimo_errore = ""


def ultimo_errore() -> str:
    """Message of the last failed open attempt (for status bars)."""
    return _ultimo_errore


def url_cartella_drive(folder_id: str) -> str:
    """Build the browser/app URL for a Google Drive folder."""
    return f"https://drive.google.com/drive/folders/{quote(folder_id, safe='')}"


def apri_url(url: str) -> bool:
    global _ultimo_errore
    _ultimo_errore = ""
    if sys.platform == "android":
        return _android_view(url)
    try:
        if webbrowser.open(url):
            return True
        _ultimo_errore = "Il sistema non ha aperto il collegamento."
        return False
    except Exception as exc:
        _ultimo_errore = f"{type(exc).__name__}: {exc}"
        return False


def condividi_url(url: str, testo: str = "") -> bool:
    if sys.platform == "android":
        return _android_share(url, testo)
    return apri_url(url)


def condividi_pdf(path, *, platform: str | None = None, android_sender=None,
                  pc_opener=None) -> bool:
    """Share a PDF attachment on Android or open its desktop association."""
    global _ultimo_errore
    _ultimo_errore = ""
    pdf = Path(path).expanduser().resolve()
    if not pdf.is_file():
        _ultimo_errore = f"Il PDF da condividere non esiste: {pdf}"
        return False
    selected_platform = sys.platform if platform is None else platform
    try:
        if selected_platform == "android":
            sender = android_sender or _android_share_pdf
            result = sender(str(pdf), "Condividi PDF pyTrainer")
            if result is False:
                raise RuntimeError("Android non ha aperto il pannello di condivisione.")
        else:
            opener = pc_opener or _pc_open_file
            result = opener(str(pdf))
            if result is False:
                raise RuntimeError("Il sistema non ha aperto il PDF.")
        return True
    except Exception as exc:
        _ultimo_errore = f"{type(exc).__name__}: {exc}"
        return False


def _pc_open_file(path: str):
    """Use the OS association (Acrobat/browser/etc.), not a file:// share."""
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
        return True
    return webbrowser.open(Path(path).as_uri())


def _android_share_pdf(path: str, chooser_title: str) -> bool:
    """Call the Java FileProvider bridge lazily to keep PC imports headless."""
    from jnius import autoclass

    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    bridge = autoclass("org.ptt.pyTrainer.PdfShareBridge")
    bridge.sharePdf(activity, path, chooser_title)
    return True


def _android_intent(action: str, *, uri: str | None = None, type_: str | None = None,
                    extra_text: str | None = None, chooser: bool = True) -> bool:
    global _ultimo_errore
    _ultimo_errore = ""
    try:
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        intent = Intent(action)
        if uri:
            intent.setData(Uri.parse(uri))
        if type_:
            intent.setType(type_)
        if extra_text is not None:
            intent.putExtra(Intent.EXTRA_TEXT, extra_text)
        if chooser:
            intent = Intent.createChooser(intent, "pyTrainer")
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        activity.startActivity(intent)
        return True
    except Exception as exc:
        _ultimo_errore = f"{type(exc).__name__}: {exc}"
        return False


def _android_view(url: str) -> bool:
    if _android_intent("android.intent.action.VIEW", uri=url, chooser=False):
        return True
    errore_diretto = _ultimo_errore
    if _android_intent("android.intent.action.VIEW", uri=url):
        return True
    _ultimo_errore = f"diretto: {errore_diretto} | chooser: {_ultimo_errore}"
    return False


def _android_share(url: str, testo: str) -> bool:
    return _android_intent("android.intent.action.SEND", type_="text/plain",
                           extra_text=f"{testo} {url}".strip())
