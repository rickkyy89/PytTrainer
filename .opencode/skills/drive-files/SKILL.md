---
name: drive-files
description: Carica, scarica o elenca file CSV e .scheda nella cartella Google Drive di pyTrainer. Usa quando l'utente chiede upload/download su Drive, sincronizzazione di CSV o bundle, oppure di vedere i file remoti.
---

# File pyTrainer su Google Drive

Usa `scripts/drive_files.py` dalla root del repository per trasferire file
`.csv` e `.scheda`. Lo script usa `credentials.json`/`token.json` tramite
`LocalCredentialsProvider` e, salvo override, la cartella
`kivy_app.config.DEFAULT_FOLDER_ID`.

## Operazioni

Elenca tutti i file supportati:

```powershell
python scripts/drive_files.py list
python scripts/drive_files.py list --kind csv
python scripts/drive_files.py list --kind scheda
```

Carica un file. Se nella cartella esiste esattamente un file con lo stesso
nome, viene aggiornato; altrimenti viene creato:

```powershell
python scripts/drive_files.py upload "percorso\file.csv"
python scripts/drive_files.py upload "percorso\file.scheda"
```

Per assegnare un nome remoto diverso o aggiornare un ID preciso:

```powershell
python scripts/drive_files.py upload "percorso\file.csv" --name "catalogo.csv"
python scripts/drive_files.py upload "percorso\file.csv" --file-id "ID_DRIVE"
```

Scarica per nome esatto. Lo script non sovrascrive un file locale senza
`--force`:

```powershell
python scripts/drive_files.py download "catalogo.csv" --output "destinazione\catalogo.csv"
python scripts/drive_files.py download "allenamento.scheda" --output "destinazione\allenamento.scheda"
python scripts/drive_files.py download "ID_DRIVE" --file-id --output "destinazione\file.scheda"
```

Per una cartella diversa aggiungi l'opzione globale prima del comando:

```powershell
python scripts/drive_files.py --folder-id "ID_CARTELLA" list
```

## Regole

- Verifica sempre che il file locale esista prima dell'upload.
- Usa solo `.csv` e `.scheda`; non rinominare un tipo come l'altro.
- Per upload ripetuti preferisci l'aggiornamento per nome, cosi non si creano duplicati.
- Se esistono piu file remoti con lo stesso nome, elencali e usa `--file-id`.
- Non usare `--force` in download se l'utente non ha autorizzato la sostituzione.
- Se mancano `credentials.json` e `service_account.json`, fermati e chiedi le credenziali all'utente.
- Comunica sempre azione, nome, ID e URL Drive dopo un upload riuscito.
- Comunica nome remoto e percorso locale dopo un download riuscito.

Le modifiche a questa skill diventano visibili alle nuove sessioni dopo il
riavvio di OpenCode.
