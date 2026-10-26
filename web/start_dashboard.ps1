param([int]$Port = 8080)

$ErrorActionPreference = "Stop"
$WebRoot = $PSScriptRoot
$Url = "http://localhost:$Port/"

Write-Host "NX Quality Dashboard"
Write-Host "Web root: $WebRoot"
Write-Host "URL: $Url"

$python = Get-Command py -ErrorAction SilentlyContinue
if ($python) {
    Start-Process $Url
    & py -m http.server $Port --directory $WebRoot
    exit $LASTEXITCODE
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    Start-Process $Url
    & python -m http.server $Port --directory $WebRoot
    exit $LASTEXITCODE
}

throw "Python wurde nicht gefunden. Installiere Python oder starte einen lokalen HTTP-Server im Ordner: $WebRoot"
