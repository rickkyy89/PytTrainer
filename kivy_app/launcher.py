"""Open or share a URL with the platform mechanism (ticket 08).

PC uses the default browser; Android fires native ACTION_VIEW /
ACTION_SEND intents through pyjnius (imported lazily so the module
stays importable everywhere). ACTION_VIEW is tried first without
chooser so an installed YouTube app receives watch URLs directly.
"""

from __future__ import annotations

import sys
import webbrowser

_ultimo_errore = ""


def ultimo_errore() -> str:
    """Message of the last failed open attempt (for status bars)."""
    return _ultimo_errore


def apri_url(url: str) -> bool:
    if sys.platform == "android":
        return _android_view(url)
    try:
        return bool(webbrowser.open(url))
    except Exception as exc:
        globals()["_ultimo_errore"] = f"{type(exc).__name__}: {exc}"
        return False


def condividi_url(url: str, testo: str = "") -> bool:
    if sys.platform == "android":
        return _android_share(url, testo)
    return apri_url(url)


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
