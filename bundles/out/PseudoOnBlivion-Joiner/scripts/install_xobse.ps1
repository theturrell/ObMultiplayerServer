param(
    [string]$GamePath,
    [string]$ReleaseApiUrl = "https://api.github.com/repos/llde/xOBSE/releases/latest"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$findScript = Join-Path $scriptDir "find_oblivion.ps1"

if ([string]::IsNullOrWhiteSpace($GamePath) -and (Test-Path $findScript)) {
    $GamePath = & $findScript | Select-Object -First 1
}

if ([string]::IsNullOrWhiteSpace($GamePath) -or -not (Test-Path (Join-Path $GamePath "Oblivion.exe"))) {
    throw "Could not detect Oblivion automatically. Pass -GamePath explicitly."
}

$headers = @{
    "User-Agent" = "PseudoOnBlivionInstaller"
    "Accept" = "application/vnd.github+json"
}

$release = Invoke-RestMethod -Headers $headers -Uri $ReleaseApiUrl
$asset = $release.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1

if (-not $asset) {
    throw "Could not find a zip asset on the latest xOBSE release."
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("PseudoOnBlivion-xOBSE-" + [System.Guid]::NewGuid().ToString("N"))
$zipPath = Join-Path $tempRoot $asset.name
$extractRoot = Join-Path $tempRoot "extract"

New-Item -ItemType Directory -Force -Path $tempRoot, $extractRoot | Out-Null

try {
    Invoke-WebRequest -Headers $headers -Uri $asset.browser_download_url -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $extractRoot -Force
    Copy-Item (Join-Path $extractRoot "*") $GamePath -Recurse -Force
}
finally {
    Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Output "Installed xOBSE from $($asset.browser_download_url) to $GamePath"
