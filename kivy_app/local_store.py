"""Visible local storage for .scheda bundles.

When Drive is unreachable the app must never drop edits into an invisible
internal cache.  On Android the bundle is mirrored to the public
``<Documenti|Download>/pyTrainer`` folder through the native ``StorageBridge``
(MediaStore on API 29+, direct write with the storage permission below), so a
file manager can find it.  On the PC there is no mirror: the save dialog picks
the exact destination instead.
"""

from __future__ import annotations

from pathlib import Path


class LocalStoreError(Exception):
    """A local save/import the platform refused to perform."""


class AndroidLocalStore:
    """Mirror bundles into a public Documents/Download subfolder.

    ``autoclass`` must run on the main thread (Kivy rule), so the Java handles
    are resolved eagerly at construction, exactly like the frame extractor.
    ``autoclass_factory`` is injectable for headless tests.
    """

    _ETICHETTE = {"documenti": "Documenti", "download": "Download"}
    _CARTELLE = {"documenti": "Documents/pyTrainer", "download": "Download/pyTrainer"}

    def __init__(self, autoclass_factory=None, kind: str = "documenti"):
        if autoclass_factory is None:
            from jnius import autoclass as autoclass_factory  # noqa: F401
        self._bridge_cls = autoclass_factory("org.ptt.pyTrainer.StorageBridge")
        self._activity = autoclass_factory("org.kivy.android.PythonActivity").mActivity
        self._kind = kind if kind in self._ETICHETTE else "documenti"

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def etichetta(self) -> str:
        return self._ETICHETTE[self._kind]

    @property
    def percorso_descrizione(self) -> str:
        return self._CARTELLE[self._kind]

    def set_kind(self, kind: str) -> None:
        if kind not in self._ETICHETTE:
            raise LocalStoreError("Destinazione di salvataggio non valida.")
        self._kind = kind

    def salva(self, src: str | Path, nome: str) -> str:
        esito = self._bridge_cls.salvaFile(self._activity, str(src), str(nome), self._kind)
        return self._esito(esito)

    def importa(self, percorso: str, dest_dir: str | Path) -> str:
        path = str(percorso)
        if path.startswith("content://"):
            return self._esito(self._bridge_cls.copiaUri(self._activity, path, str(dest_dir)))
        if not Path(path).is_file():
            raise LocalStoreError(f"File non trovato: {path}")
        return path

    @staticmethod
    def _esito(esito) -> str:
        testo = str(esito or "")
        if testo.startswith("ERR:"):
            raise LocalStoreError(testo[4:].strip())
        if not testo:
            raise LocalStoreError("il salvataggio locale non ha restituito un percorso.")
        return testo
