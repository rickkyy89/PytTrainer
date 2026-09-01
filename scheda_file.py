"""
Gestione del file scheda unico (estensione ".scheda"): uno zip che raccoglie
in un solo file portabile tutto ciò che descrive un allenamento, invece di un
CSV sciolto più una cartella "frames/" condivisa tra tutte le schede.

Layout dell'archivio:

    mia_scheda.scheda            (zip standard, ZIP_DEFLATED)
    ├── scheda.csv               obbligatorio — manifest 11 colonne (formato
    │                            csv_utils invariato); FrameStartPath e
    │                            FrameFinishPath sono sempre relativi
    │                            all'archivio: "frames/<slug>_start.jpg"
    ├── frames/                  i JPEG dei frame START/FINISH, più gli
    │                            eventuali backup pre-ritaglio *_orig.jpg
    ├── metadata.json            opzionale — metadati della scheda (titolo)
    └── state.json               opzionale — stato di ripresa del Google Doc
                                 ({"doc_id", "titolo", "esercizi"})

Poiché ffmpeg, PIL e l'upload su Google Drive lavorano solo su file reali,
il caricamento estrae il contenuto in una cartella di lavoro deterministica
accanto al bundle ("<percorso>.work/") e riscrive i percorsi dei frame nei
dizionari esercizio verso i file estratti. La cartella di lavoro è una cache
usa-e-getta (cancellarla è sempre sicuro): la fonte di verità è il bundle,
che il salvataggio ricompatta in modo atomico (file temporaneo + os.replace).

Il percorso deterministico della cartella di lavoro (non una tempdir casuale)
preserva l'idempotenza tra esecuzioni: scegli_ed_estrai() salta i frame già
presenti su disco e create_workout_document() riprende dallo state.json.

Nota sulle collisioni: come nella vecchia cartella "frames/" condivisa, due
esercizi con lo stesso slug producevano gli stessi nomi file (last-wins).
Ora _scrivi_zip garantisce nomi unici aggiungendo _2, _3 se necessario.
"""

from __future__ import annotations

import io
import json
import os
import posixpath
import zipfile

from csv_utils import esercizi_csv_bytes, parse_esercizi_csv

SUFFISSO_SCHEDA = ".scheda"
NOME_MANIFEST = "scheda.csv"
NOME_METADATA = "metadata.json"
NOME_STATO = "state.json"
CARTELLA_FRAMES = "frames"


class SchedaFileError(Exception):
    """Sollevata quando un file .scheda è mancante, corrotto o non valido."""


def cartella_lavoro_per_bundle(percorso_bundle: str) -> str:
    """
    Percorso deterministico della cartella di lavoro (cache di estrazione) di
    un bundle: "<percorso_bundle>.work". Non crea nulla su disco.
    """
    return f"{percorso_bundle}.work"


def cartella_frames(cartella_lavoro: str) -> str:
    """
    Sottocartella dei frame dentro la cartella di lavoro (creata se assente).
    È il valore da passare come output_dir a extract_start_finish_frames() /
    scegli_ed_estrai() quando si lavora con un bundle.
    """
    percorso = os.path.join(cartella_lavoro, CARTELLA_FRAMES)
    os.makedirs(percorso, exist_ok=True)
    return percorso


def percorso_stato(cartella_lavoro: str) -> str:
    """
    Percorso dello state.json (ripresa Google Doc) dentro la cartella di
    lavoro, da passare come state_path a create_workout_document() /
    update_exercise_media(). Crea la cartella di lavoro se assente, così il
    file di stato è sempre scrivibile.
    """
    os.makedirs(cartella_lavoro, exist_ok=True)
    return os.path.join(cartella_lavoro, NOME_STATO)


def titolo_scheda(cartella_lavoro: str) -> str | None:
    """Restituisce il titolo salvato nel bundle, o None per bundle legacy."""
    percorso = os.path.join(cartella_lavoro, NOME_METADATA)
    try:
        with open(percorso, encoding="utf-8") as file_metadata:
            metadata = json.load(file_metadata)
    except (OSError, ValueError):
        return None
    titolo = metadata.get("titolo") if isinstance(metadata, dict) else None
    return titolo if isinstance(titolo, str) else None


def _valida_nomi_membri(nomi: list[str]) -> None:
    """
    Guardia anti zip-slip: rifiuta archivi con membri a percorso assoluto,
    con componenti ".." o con lettera di unità Windows.
    """
    for nome in nomi:
        normalizzato = nome.replace("\\", "/")
        parti = normalizzato.split("/")
        percorso_assoluto = normalizzato.startswith("/")
        lettera_unita = len(parti[0]) == 2 and parti[0][1] == ":"
        if percorso_assoluto or lettera_unita or ".." in parti:
            raise SchedaFileError(
                f"Il file scheda contiene un membro con percorso non sicuro: '{nome}'."
            )


def _estrai_da_zip(archivio: zipfile.ZipFile, cartella_lavoro: str) -> list[dict]:
    """
    Logica condivisa di carica_scheda() e carica_scheda_da_file_like():
    valida l'archivio, estrae frame e stato nella cartella di lavoro
    (sovrascrivendo la cache), parsa il manifest e riscrive frame_start /
    frame_finish di ogni esercizio sul percorso reale estratto.
    """
    nomi = archivio.namelist()
    _valida_nomi_membri(nomi)
    if NOME_MANIFEST not in nomi:
        raise SchedaFileError(
            f"Il file scheda non contiene il manifest '{NOME_MANIFEST}': "
            "non è un file .scheda valido."
        )

    dir_frames = cartella_frames(cartella_lavoro)
    prefisso_frames = f"{CARTELLA_FRAMES}/"
    for nome in nomi:
        normalizzato = nome.replace("\\", "/")
        if not normalizzato.startswith(prefisso_frames) or normalizzato.endswith("/"):
            continue
        destinazione = os.path.join(dir_frames, posixpath.basename(normalizzato))
        with open(destinazione, "wb") as file_frame:
            file_frame.write(archivio.read(nome))

    # Metadati e stato sovrascrivono (o rimuovono) quanto rimasto nella cache:
    # il bundle è la fonte di verità anche per titolo e ripresa del Google Doc.
    for nome_file in (NOME_METADATA, NOME_STATO):
        destinazione = os.path.join(cartella_lavoro, nome_file)
        if nome_file in nomi:
            with open(destinazione, "wb") as file_cache:
                file_cache.write(archivio.read(nome_file))
        elif os.path.exists(destinazione):
            os.remove(destinazione)

    esercizi = parse_esercizi_csv(io.BytesIO(archivio.read(NOME_MANIFEST)))

    # I percorsi dei frame nel manifest (relativi all'archivio, o legacy
    # assoluti/con cartella: si usa solo il basename) vengono riscritti sul
    # file realmente estratto; se il file non è nell'archivio la chiave torna
    # a None, così la ri-estrazione a valle può rigenerarlo.
    for esercizio in esercizi:
        for chiave in ("frame_start", "frame_finish"):
            valore = esercizio.get(chiave)
            if not valore:
                esercizio[chiave] = None
                continue
            basename = posixpath.basename(str(valore).replace("\\", "/"))
            percorso_reale = os.path.join(dir_frames, basename)
            esercizio[chiave] = percorso_reale if os.path.exists(percorso_reale) else None
    return esercizi


def carica_scheda(
    percorso_bundle: str, cartella_lavoro: str | None = None
) -> tuple[list[dict], str]:
    """
    Apre un file .scheda, ne estrae frame e stato nella cartella di lavoro
    (default: cartella_lavoro_per_bundle(percorso_bundle)) e restituisce
    (esercizi, cartella_lavoro). I dizionari esercizio hanno frame_start /
    frame_finish già puntati ai file estratti (o None se assenti dal bundle).

    Solleva SchedaFileError se il file manca, non è uno zip valido, contiene
    membri con percorsi non sicuri o non contiene il manifest; propaga il
    ValueError di parse_esercizi_csv() se il manifest è malformato.
    """
    if cartella_lavoro is None:
        cartella_lavoro = cartella_lavoro_per_bundle(percorso_bundle)
    if not os.path.exists(percorso_bundle):
        raise SchedaFileError(f"Il file scheda '{percorso_bundle}' non esiste.")
    try:
        with zipfile.ZipFile(percorso_bundle) as archivio:
            esercizi = _estrai_da_zip(archivio, cartella_lavoro)
    except zipfile.BadZipFile as exc:
        raise SchedaFileError(
            f"Il file scheda '{percorso_bundle}' non è uno zip valido: {exc}"
        ) from exc
    return esercizi, cartella_lavoro


def carica_scheda_da_file_like(file_like, cartella_lavoro: str) -> list[dict]:
    """
    Variante di carica_scheda() per contenuti già in memoria (es. l'upload
    dell'interfaccia Streamlit): la cartella di lavoro va indicata
    esplicitamente perché non esiste un percorso del bundle da cui dedurla.
    """
    try:
        with zipfile.ZipFile(file_like) as archivio:
            return _estrai_da_zip(archivio, cartella_lavoro)
    except zipfile.BadZipFile as exc:
        raise SchedaFileError(f"Il file caricato non è un file .scheda valido: {exc}") from exc


def _percorso_backup_frame(percorso_frame: str) -> str:
    """Percorso convenzionale del backup pre-ritaglio di un frame (vedi app.py)."""
    radice, _ = os.path.splitext(percorso_frame)
    return f"{radice}_orig.jpg"


def _scrivi_zip(
    esercizi: list[dict], destinazione, state_path: str | None, titolo: str | None
) -> None:
    """
    Builder condiviso di salva_scheda() e scheda_bytes(): scrive l'archivio
    completo (manifest con percorsi frame normalizzati, frame esistenti su
    disco con i loro backup *_orig.jpg, titolo e stato se presenti) su
    'destinazione' (percorso o file-like).
    """
    frame_da_includere: dict[str, str] = {}
    esercizi_normalizzati = []
    # Traccia i nomi membro già usati per evitare collisioni su slug duplicati
    membri_usati: set[str] = set()
    for esercizio in esercizi:
        copia = dict(esercizio)
        for chiave in ("frame_start", "frame_finish"):
            percorso = copia.get(chiave)
            if percorso and os.path.exists(percorso):
                base = os.path.basename(percorso)
                membro = f"{CARTELLA_FRAMES}/{base}"
                # Se due esercizi diversi puntano allo stesso basename (slug duplicato), rinomina il secondo
                if membro in membri_usati:
                    radice, ext = os.path.splitext(base)
                    n = 2
                    while True:
                        candidato = f"{CARTELLA_FRAMES}/{radice}_{n}{ext}"
                        if candidato not in membri_usati:
                            membro = candidato
                            # Copia fisica già esistente: il file su disco ha il nome originale, ma nel bundle
                            # lo salviamo con nome unico. Aggiorniamo la copia del percorso per il manifest.
                            break
                        n += 1
                membri_usati.add(membro)
                frame_da_includere[membro] = percorso
                copia[chiave] = membro
                backup = _percorso_backup_frame(percorso)
                if os.path.exists(backup):
                    # Il backup deve seguire il nome assegnato al frame nel bundle:
                    # dopo il caricamento app.py lo cerca come <frame>_orig.jpg.
                    radice_membro, _ = os.path.splitext(membro)
                    backup_membro = f"{radice_membro}_orig.jpg"
                    membri_usati.add(backup_membro)
                    frame_da_includere[backup_membro] = backup
            else:
                # Frame referenziato ma non (più) esistente su disco: cella
                # vuota nel manifest, nessun errore (verrà ri-estratto).
                copia[chiave] = None
        esercizi_normalizzati.append(copia)

    with zipfile.ZipFile(destinazione, "w", zipfile.ZIP_DEFLATED) as archivio:
        archivio.writestr(NOME_MANIFEST, esercizi_csv_bytes(esercizi_normalizzati))
        if titolo is not None:
            archivio.writestr(NOME_METADATA, json.dumps({"titolo": titolo}, ensure_ascii=False))
        for membro, percorso in frame_da_includere.items():
            archivio.write(percorso, membro)
        if state_path and os.path.exists(state_path):
            archivio.write(state_path, NOME_STATO)


def salva_scheda(
    esercizi: list[dict],
    percorso_bundle: str,
    state_path: str | None = None,
    titolo: str | None = None,
) -> None:
    """
    Salva (o sovrascrive) il file .scheda con il manifest CSV, tutti i frame
    attualmente esistenti su disco referenziati dagli esercizi (più i backup
    pre-ritaglio) e, se state_path esiste, lo stato di ripresa del Google
    Doc e il titolo della scheda. La scrittura è atomica: prima su
    "<percorso>.tmp", poi os.replace, così un'interruzione non corrompe mai
    un bundle esistente.
    """
    percorso_temporaneo = f"{percorso_bundle}.tmp"
    try:
        _scrivi_zip(esercizi, percorso_temporaneo, state_path, titolo)
        os.replace(percorso_temporaneo, percorso_bundle)
    finally:
        if os.path.exists(percorso_temporaneo):
            try:
                os.remove(percorso_temporaneo)
            except OSError:
                pass


def scheda_bytes(
    esercizi: list[dict], state_path: str | None = None, titolo: str | None = None
) -> bytes:
    """
    Genera in memoria (nessun file su disco) lo stesso archivio prodotto da
    salva_scheda(), per il bottone di download dell'interfaccia Streamlit.
    """
    buffer = io.BytesIO()
    _scrivi_zip(esercizi, buffer, state_path, titolo)
    return buffer.getvalue()
