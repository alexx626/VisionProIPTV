$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$python = Join-Path $projectRoot 'venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Missing venv\Scripts\python.exe. See BUILD_README.txt.' }
$env:PYTHONUTF8 = '1'
& $python -c 'import PyInstaller; from PyQt5 import QtCore, QtWidgets; import vlc'
if ($LASTEXITCODE -ne 0) { throw 'Build dependencies are missing. See BUILD_README.txt.' }
$archiveRoot = Join-Path $projectRoot ('build_archive\' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
foreach ($folder in @('dist', 'build')) {
    $source = [IO.Path]::GetFullPath((Join-Path $projectRoot $folder))
    if (!$source.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe build path.' }
    if (Test-Path -LiteralPath $source) {
        New-Item -ItemType Directory -Path $archiveRoot -Force | Out-Null
        Move-Item -LiteralPath $source -Destination (Join-Path $archiveRoot $folder)
    }
}
& $python -m PyInstaller --noconfirm --clean --distpath (Join-Path $projectRoot 'dist') --workpath (Join-Path $projectRoot 'build') (Join-Path $projectRoot 'visionpro.spec')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed. Previous output is preserved in build_archive.' }
Write-Host ('Build ready: ' + (Join-Path $projectRoot 'dist\VisionProIPTV\VisionProIPTV.exe'))
if (Test-Path -LiteralPath (Join-Path $projectRoot 'dist\VisionProIPTV\_internal\ffmpeg\ffmpeg.exe')) {
    Write-Host 'Keep the entire folder. VLC 64-bit is required. FFmpeg is bundled (_internal\ffmpeg).'
} else {
    Write-Host 'Keep the entire folder. VLC 64-bit is required; recording requires external FFmpeg (or put ffmpeg.exe in vendor\ffmpeg before building).'
}
