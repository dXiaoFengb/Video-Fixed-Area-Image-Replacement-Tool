param(
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot

$workPath = 'VideoImageOverlay/build/work'
$specPath = 'VideoImageOverlay/build/spec'
$distPath = 'VideoImageOverlay'
$toolDirectory = 'VideoImageOverlay/.build-tools'
if (Test-Path -LiteralPath (Join-Path $repoRoot $toolDirectory)) {
    $env:PYTHONPATH = "$(Join-Path $repoRoot $toolDirectory);$(Join-Path $repoRoot 'VideoImageOverlay')"
}
if ($Clean) {
    Remove-Item -LiteralPath (Join-Path $repoRoot 'VideoImageOverlay/build') -Recurse -Force -ErrorAction SilentlyContinue
}

$ffmpeg = Join-Path $repoRoot 'VideoImageOverlay/third_party/ffmpeg/ffmpeg.exe'
$ffprobe = Join-Path $repoRoot 'VideoImageOverlay/third_party/ffmpeg/ffprobe.exe'
$license = Join-Path $repoRoot 'VideoImageOverlay/third_party/ffmpeg/FFMPEG-LICENSE.txt'
$presetDirectory = Join-Path $repoRoot 'VideoImageOverlay/assets/presets'
$icon = Join-Path $repoRoot 'VideoImageOverlay/assets/app_icon.ico'
foreach ($required in @($ffmpeg, $ffprobe, $license, $presetDirectory, $icon)) {
    if (!(Test-Path -LiteralPath $required)) {
        throw "Missing required build input: $required"
    }
}

python -m PyInstaller --noconfirm --clean --onefile --windowed --name VideoImageOverlay --workpath $workPath --specpath $specPath --distpath $distPath --icon $icon --add-binary "$ffmpeg;." --add-binary "$ffprobe;." --add-data "$license;." --add-data "$presetDirectory;presets" --add-data "$icon;." VideoImageOverlay/main.py
