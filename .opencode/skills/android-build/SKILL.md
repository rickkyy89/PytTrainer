---
name: android-build
description: Build and deploy the pyTrainer Android APK with Buildozer. Use when asked to build, rebuild, package, or install the APK, or when `buildozer android` fails. Triggers: build, buildare, APK, buildozer, android debug, adb install, deploy su Android.
---

# Android build (Buildozer via WSL)

This repo builds its Android APK ONLY through WSL Ubuntu. The Windows-native
`buildozer.exe` cannot build Android (it raises
`NotImplementedError: Windows platform not yet working for Android`, and
`buildozer android debug` on Windows fails with `Unknown command/target android`).
Never try to install Android SDK/NDK on the Windows side.

## Fixed environment facts

| Item | Value |
|---|---|
| Repo (Windows path) | `C:\PyTrainer\PC\PytTrainer` |
| Repo (WSL path) | `/mnt/c/PyTrainer/PC/PytTrainer` |
| WSL distro | `Ubuntu` (access with `wsl -e bash -lc "..."`) |
| Build env (venv with buildozer + Cython) | `~/spike-builder/venv` (inside WSL, i.e. `/home/rickk/spike-builder/venv`) |
| APK output | Versioned file matching `bin/pyTrainer-*-arm64-v8a-debug.apk` |
| adb | `~/platform-tools/adb` (inside WSL) |

## Versioned build (official wrapper)

For every versioned build, prefer the repository wrapper from the repository
root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\build_android.ps1"
```

The wrapper increments the build number in `kivy_app/version.py` before
running `pytest` and the verified WSL Buildozer command. Buildozer reads the
same version literal through `version.regex`, so the APK metadata and filename
contain that build number. If tests, packaging, or the fresh-APK check fail,
the wrapper restores the original version; on success it keeps the increment.
The caller must provide any required long timeout. It does not install the APK.
Do not run this wrapper concurrently with another build, and do not delete
`.buildozer/` or generated APK artifacts.

## Raw diagnostic fallback (run from the Windows shell)

Use the raw command below only to diagnose the wrapper or Buildozer itself.
It does not increment or roll back the application build number.

1. Build the debug APK. This takes minutes (incremental) up to ~30+ min
   (first/clean build). ALWAYS pass a long timeout (>= 1800000 ms); the
   command is NOT hung when it looks quiet — Gradle output is verbose at the end.

   ```powershell
   wsl -e bash -lc "cd /mnt/c/PyTrainer/PC/PytTrainer && source ~/spike-builder/venv/bin/activate && buildozer android debug 2>&1 | tail -n 40"
   ```

2. Success markers (last lines of output):

   ```
   # Android packaging done!
   # APK pyTrainer-<version>-arm64-v8a-debug.apk available in the bin directory
   ```

   These messages are NORMAL and are NOT errors: `BUILD SUCCESSFUL` (Gradle),
   `failed to apply patch ... assuming it is already applied`,
   `No setup.py/pyproject.toml used, copying full private data into .apk`,
   `stty: standard input: Inappropriate ioctl for device`.

3. Verify the APK is fresh (timestamp must be after you started the build):

   ```powershell
   Get-ChildItem bin\*.apk | Sort-Object LastWriteTime -Descending | Select-Object -First 1 Name,LastWriteTime,Length
   ```

## Install on the connected phone (only if requested)

```powershell
wsl -e bash -lc "cd /mnt/c/PyTrainer/PC/PytTrainer && ~/platform-tools/adb devices"
wsl -e bash -lc 'cd /mnt/c/PyTrainer/PC/PytTrainer && APK=$(ls -t bin/*.apk | head -1) && ~/platform-tools/adb install -r "$APK"'
```

`adb devices` must list a device with state `device` (not `unauthorized`).
Install succeeds with `Performing Streamed Install` + `Success`.

## Failure signatures and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `Unknown command/target android` | Ran the Windows `buildozer.exe` | Use the WSL command from step 1 |
| `NotImplementedError('Windows platform not yet working for Android')` | Same as above | Same fix |
| `buildozer: command not found` (inside wsl) | venv not activated | Add `source ~/spike-builder/venv/bin/activate &&` |
| `Cython (cython) not found, please install it.` | venv not activated (Cython lives in the venv) | Activate the venv; do NOT pip-install Cython globally |
| Command seems stuck for minutes | Normal long build | Wait; increase tool timeout, do not kill it |
| `adb: device not found` / `unauthorized` | Phone unplugged/USB debugging not authorized | Ask the user to connect and approve the phone |
| Build truly fails (traceback, `ERROR:` lines) | Real error | Re-run WITHOUT `| tail` to get the full log and fix that error; do not delete `.buildozer/` (it caches a multi-hour dist build) |

## Rules

- Never delete `.buildozer/` or run `buildozer ... clean`/`distclean` to "fix" a build:
  the cached python-for-android distribution takes hours to rebuild.
- Never commit the APK, `bin/*.apk`, `.buildozer/`, or `build/` artifacts.
- Python tests (`pytest -q`) run on Windows and are unrelated to this skill.
