param(
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
$toolDirectory = Join-Path $projectRoot '.build-tools'
if (Test-Path -LiteralPath $toolDirectory) {
    $env:PYTHONPATH = "$toolDirectory;$projectRoot"
}
if ($Clean) {
    Remove-Item -LiteralPath 'build' -Recurse -Force -ErrorAction SilentlyContinue
}
$ffmpegDirectory = Join-Path $projectRoot 'third_party\ffmpeg'
$ffmpeg = Join-Path $ffmpegDirectory 'ffmpeg.exe'
$ffprobe = Join-Path $ffmpegDirectory 'ffprobe.exe'
$license = Join-Path $ffmpegDirectory 'FFMPEG-LICENSE.txt'
$presetDirectory = Join-Path $projectRoot 'assets\presets'
if (!(Test-Path -LiteralPath $ffmpeg) -or !(Test-Path -LiteralPath $ffprobe) -or !(Test-Path -LiteralPath $license) -or !(Test-Path -LiteralPath $presetDirectory)) {
    throw 'Missing required FFmpeg runtime files or preset assets.'
}
python -m PyInstaller --noconfirm --clean --onefile --windowed --name VideoImageOverlay --workpath build\work --specpath build\spec --distpath . --add-binary "$ffmpeg;." --add-binary "$ffprobe;." --add-data "$license;." --add-data "$presetDirectory;presets" main.py
