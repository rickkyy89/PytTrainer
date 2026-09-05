[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptDirectory ".."))
$versionPath = Join-Path $repoRoot "kivy_app\version.py"
$specPath = Join-Path $repoRoot "buildozer.spec"

if (-not (Test-Path -LiteralPath $specPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $repoRoot "kivy_app") -PathType Container)) {
    throw "Repository root not found or incomplete: $repoRoot"
}
if (-not (Test-Path -LiteralPath $versionPath -PathType Leaf)) {
    throw "Version file not found: $versionPath"
}

$originalVersion = [System.IO.File]::ReadAllText($versionPath)
$versionPattern = '(?m)^(__version__\s*=\s*["''])(\d+\.\d+\.\d+)\.(\d+)(["'']\s*)$'
$versionMatch = [regex]::Match($originalVersion, $versionPattern)
if (-not $versionMatch.Success) {
    throw 'Unsupported version.py format: expected __version__ = "MAJOR.MINOR.PATCH.BUILD"'
}

$versionName = $versionMatch.Groups[2].Value
$buildNumber = [int]$versionMatch.Groups[3].Value + 1
$updatedVersion = $versionMatch.Groups[1].Value + $versionName + "." + $buildNumber + $versionMatch.Groups[4].Value
$updatedVersion = $originalVersion.Substring(0, $versionMatch.Index) + $updatedVersion + $originalVersion.Substring($versionMatch.Index + $versionMatch.Length)

$succeeded = $false
try {
    [System.IO.File]::WriteAllText($versionPath, $updatedVersion, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Building pyTrainer $versionName, build $buildNumber"
    $buildStartedAt = Get-Date

    & python -m pytest -q
    if ($LASTEXITCODE -ne 0) {
        throw "pytest failed with exit code $LASTEXITCODE"
    }

    $wslRoot = (& wsl.exe -e wslpath -a $repoRoot).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($wslRoot)) {
        throw "Unable to convert repository path to WSL: $repoRoot"
    }

    $wslCommand = "cd '$wslRoot' && source ~/spike-builder/venv/bin/activate && buildozer android debug"
    & wsl.exe -e bash -lc $wslCommand
    if ($LASTEXITCODE -ne 0) {
        throw "Buildozer failed with exit code $LASTEXITCODE"
    }

    $expectedApk = "pyTrainer-$versionName.$buildNumber-arm64-v8a-debug.apk"
    $apk = Get-Item -LiteralPath (Join-Path $repoRoot "bin\$expectedApk") -ErrorAction SilentlyContinue
    if ($null -eq $apk -or $apk.LastWriteTime -lt $buildStartedAt) {
        throw "Buildozer returned success but no fresh APK was found in bin."
    }

    $succeeded = $true
    Write-Host "Android build completed: $($apk.FullName)"
    Write-Host "version.py remains at build $buildNumber."
}
finally {
    if (-not $succeeded) {
        [System.IO.File]::WriteAllText($versionPath, $originalVersion, [System.Text.UTF8Encoding]::new($false))
        Write-Warning "Build failed: restored the original version.py."
    }
}
