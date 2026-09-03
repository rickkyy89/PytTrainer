"""Platform file selection without tkinter.

On Windows the native common-dialog API is called through ctypes; on Android
(or any other Kivy platform) the selection runs through a Kivy FileChooser
popup, which is inherently asynchronous, so the same callback-based entry
point serves every platform.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


def choose_file(callback, *, title="Seleziona un file", parent=None, patterns=None):
    """Invoke the platform picker and call ``callback(path_or_None)``."""
    if sys.platform == "win32":
        callback(_win32_open_dialog(title, patterns))
        return
    _kivy_chooser(callback, title, parent, patterns)


def _win32_open_dialog(title: str, patterns) -> str | None:
    filter_blob = _win32_filter(patterns)
    buffer = ctypes.create_unicode_buffer(4096)

    class OpenInfoW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", ctypes.c_void_p),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", wintypes.LPVOID),
            ("dwReserved", wintypes.DWORD),
            ("dwReserved2", wintypes.DWORD),
        ]

    info = OpenInfoW()
    info.lStructSize = ctypes.sizeof(info)
    info.lpstrFile = ctypes.cast(buffer, wintypes.LPWSTR)
    info.nMaxFile = len(buffer)
    info.lpstrFilter = filter_blob
    info.lpstrTitle = title
    info.Flags = 0x00000008 | 0x00000100 | 0x00040000  # OFN_HIDEREADONLY | OFN_FILEMUSTEXIST | OFN_EXPLORER
    get_open_file_name = ctypes.windll.comdlg32.GetOpenFileNameW
    if not get_open_file_name(ctypes.byref(info)):
        return None
    return buffer.value or None


def _win32_filter(patterns):
    if not patterns:
        return "Tutti i file\0*.*\0\0"
    parts = []
    for label, globs in patterns:
        if isinstance(globs, str):
            globs = [globs]
        parts.append(label)
        parts.append(";".join(globs))
    parts.append("")
    return "\0".join(parts) + "\0"


def _plyer_chooser(callback, title: str, patterns) -> bool:
    """Try the native plyer/SAF chooser on Android; False when unavailable."""
    try:
        from plyer import filechooser
    except Exception:
        return False

    globs = None
    if patterns:
        globs = [g for _, glob in patterns for g in ([glob] if isinstance(glob, str) else glob)]

    def on_selection(selection):
        if not selection:
            callback(None)
            return
        primo = selection[0]
        percorso = primo.get("filename") if isinstance(primo, dict) else str(primo)
        callback(percorso or None)

    try:
        if globs:
            filechooser.open_file(title=title, filters=globs, on_selection=on_selection)
        else:
            filechooser.open_file(title=title, on_selection=on_selection)
        return True
    except Exception:
        return False


def _kivy_chooser(callback, title: str, parent, patterns):
    if sys.platform == "android" and _plyer_chooser(callback, title, patterns):
        return

    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.filechooser import FileChooserListView
    from kivy.uix.popup import Popup

    import os

    default_path = "/storage/emulated/0" if sys.platform == "android" else os.path.expanduser("~")
    chooser = FileChooserListView(path=default_path)
    if patterns:
        globs = [g for _, glob in patterns for g in ([glob] if isinstance(glob, str) else glob)]
        chooser.filters = [globs]

    buttons = BoxLayout(size_hint_y=None, height=44, spacing=8)
    ok = Button(text="Seleziona")
    cancel = Button(text="Annulla")
    buttons.add_widget(ok)
    buttons.add_widget(cancel)

    content = BoxLayout(orientation="vertical", spacing=8)
    content.add_widget(chooser)
    content.add_widget(buttons)
    popup = Popup(title=title, content=content, size_hint=(0.9, 0.9))

    def confirm(*_):
        popup.dismiss()
        selection = chooser.selection
        callback(selection[0] if selection else None)

    ok.bind(on_release=confirm)
    cancel.bind(on_release=lambda *_: (popup.dismiss(), callback(None)))
    popup.open()
