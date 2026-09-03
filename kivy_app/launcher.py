"""Open or share a URL with the platform mechanism (ticket 08).

PC uses the default browser; Android fires native ACTION_VIEW /
ACTION_SEND chooser intents through pyjnius (imported lazily so the module
stays importable everywhere).
"""

from __future__ import annotations

import sys
import webbrowser


def apri_url(url: str) -> bool:
    if sys.platform == "android":
        return _android_view(url)
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def condividi_url(url: str, testo: str = "") -> bool:
    if sys.platform == "android":
        return _android_share(url, testo)
    return apri_url(url)


def _android_intent(action: str, *, uri: str | None = None, type_: str | None = None,
                    extra_text: str | None = None) -> bool:
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
        chooser = Intent.createChooser(intent, "pyTrainer")
        chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        activity.startActivity(chooser)
        return True
    except Exception:
        return False


def _android_view(url: str) -> bool:
    return _android_intent("android.intent.action.VIEW", uri=url)


def _android_share(url: str, testo: str) -> bool:
    return _android_intent("android.intent.action.SEND", type_="text/plain",
                           extra_text=f"{testo} {url}".strip())
