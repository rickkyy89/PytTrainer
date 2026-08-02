@echo off
setlocal
title Workout Sheet Automator

rem Si posiziona sempre nella cartella del progetto, qualunque sia la
rem cartella da cui il .bat viene lanciato (serve perche' google_docs_helper
rem cerca credentials.json / token.json nella directory corrente).
cd /d "%~dp0"

rem --- Python presente? ---------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] Python non trovato nel PATH.
    echo Installa Python 3.11+ da https://www.python.org/downloads/
    echo e ricordati di spuntare "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

rem --- Streamlit installato? ----------------------------------------------
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Streamlit non risulta installato: installo i requirements...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERRORE] Installazione dei requirements fallita.
        pause
        exit /b 1
    )
)

rem --- Avvisi non bloccanti -----------------------------------------------
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [AVVISO] ffmpeg non trovato nel PATH: l'estrazione dei frame
    echo          START/FINISH fallira'. Installalo con: winget install Gyan.FFmpeg
    echo.
)

if not exist "credentials.json" if not exist "service_account.json" (
    echo [AVVISO] Nessuna credenziale Google trovata in questa cartella
    echo          ^(credentials.json o service_account.json^): la generazione
    echo          del Google Doc fallira'. Vedi il README, sezione
    echo          "Configurazione dell'accesso a Google".
    echo.
)

rem --- Avvio --------------------------------------------------------------
echo Avvio di Workout Sheet Automator...
echo Il browser si aprira' su http://localhost:8501
echo Per chiudere l'app: premi CTRL+C in questa finestra.
echo.
python -m streamlit run app.py

echo.
echo App terminata.
pause
endlocal
