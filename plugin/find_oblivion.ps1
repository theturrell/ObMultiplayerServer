function Get-CandidatePaths {
    $candidates = New-Object System.Collections.Generic.List[string]

    $registryPaths = @(
        "HKLM:\SOFTWARE\WOW6432Node\Bethesda Softworks\Oblivion",
        "HKLM:\SOFTWARE\Bethesda Softworks\Oblivion",
        "HKCU:\SOFTWARE\Bethesda Softworks\Oblivion"
    )

    foreach ($key in $registryPaths) {
        if (Test-Path $key) {
            $item = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
            foreach ($propertyName in @("Installed Path", "InstalledPath", "Path")) {
                $value = $item.$propertyName
                if ($value) {
                    $candidates.Add($value)
                }
            }
        }
    }

    $steamRoots = @(
        "${env:ProgramFiles(x86)}\Steam",
        "${env:ProgramFiles}\Steam"
    ) | Where-Object { $_ -and (Test-Path $_) }

    foreach ($steamRoot in $steamRoots) {
        $candidates.Add((Join-Path $steamRoot "steamapps\common\Oblivion"))

        $libraryVdf = Join-Path $steamRoot "steamapps\libraryfolders.vdf"
        if (Test-Path $libraryVdf) {
            $matches = Select-String -Path $libraryVdf -Pattern '"path"\s*"([^"]+)"' -AllMatches
            foreach ($match in $matches.Matches) {
                $libraryPath = $match.Groups[1].Value.Replace("\\", "\")
                if ($libraryPath -and (Test-Path $libraryPath)) {
                    $candidates.Add((Join-Path $libraryPath "steamapps\common\Oblivion"))
                }
            }
        }
    }

    $gogRoots = @(
        "${env:ProgramFiles(x86)}\GOG Galaxy\Games\The Elder Scrolls IV - Oblivion Game of the Year Edition",
        "${env:ProgramFiles}\GOG Galaxy\Games\The Elder Scrolls IV - Oblivion Game of the Year Edition",
        "C:\GOG Games\Oblivion",
        "C:\Games\Oblivion"
    )

    foreach ($path in $gogRoots) {
        $candidates.Add($path)
    }

    return $candidates
}

function Test-OblivionPath {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $false
    }

    $exe = Join-Path $Path "Oblivion.exe"
    return (Test-Path $exe)
}

$resolved = Get-CandidatePaths | Where-Object { Test-OblivionPath $_ } | Select-Object -Unique
if ($resolved) {
    $resolved
}
