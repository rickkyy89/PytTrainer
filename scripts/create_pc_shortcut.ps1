$ErrorActionPreference = "Stop"

# Resolve paths from this script, not from the caller's current directory.
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$target = Join-Path $root "scripts\start_pc.cmd"
$icon = Join-Path $root "assets\pc\icon.ico"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "pyTrainer.lnk"

if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
    throw "Script di avvio non trovato: $target"
}
if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) {
    throw "Icona PC non trovata: $icon (eseguire build_pc_icon.py)"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = "$icon,0"
$shortcut.Description = "Avvia pyTrainer"
$shortcut.Save()

Write-Output "Collegamento aggiornato: $shortcutPath"
