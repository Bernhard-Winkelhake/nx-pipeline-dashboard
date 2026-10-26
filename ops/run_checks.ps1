param(
  [Parameter(Mandatory=$true)]
  [string]$RootParts,

  [Parameter(Mandatory=$true)]
  [string]$Framework,

  [string]$Project = "NX Quality",
  [int]$TimeoutMinutes = 120
)

$ErrorActionPreference = "Stop"

# Determine the project directory from this script:
# <project>\ops\run_checks.ps1 -> <project>
$Base = Split-Path -Parent $PSScriptRoot

$journal = Join-Path $Base "bin\batch_run_nx.py"
$reports = Join-Path $Base "reports"
$webData = Join-Path $Base "web\data"
$config  = Join-Path $Base ".pipeline-config.json"
$lock    = Join-Path $Base ".run.lock"

if (Test-Path $lock) {
  throw "Pipeline is already running: $lock"
}

New-Item -ItemType File -Path $lock -Force | Out-Null

try {
  if (-not (Test-Path $journal)) {
    throw "NX journal not found: $journal"
  }

  if (-not (Test-Path $RootParts -PathType Container)) {
    throw "Parts root folder not found: $RootParts"
  }

  if (-not (Test-Path (Join-Path $Framework "check_runner.py"))) {
    throw "nx-testframework not found. Expected: $(Join-Path $Framework 'check_runner.py')"
  }

  if (-not $env:UGII_BASE_DIR) {
    throw "UGII_BASE_DIR is not set. Start from an NX configured shell."
  }

  # NX versions/installations differ. Prefer NXBIN, then legacy ugii.
  $nxCandidates = @(
    (Join-Path $env:UGII_BASE_DIR "NXBIN\run_journal.exe"),
    (Join-Path $env:UGII_BASE_DIR "ugii\run_journal.exe"),
    (Join-Path $env:UGII_BASE_DIR "run_journal.exe")
  )

  $nxExe = $nxCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

  if (-not $nxExe) {
    throw "run_journal.exe not found below UGII_BASE_DIR=$env:UGII_BASE_DIR"
  }

  $stamp = (Get-Date).ToString("yyyy-MM-dd_HH-mm-ss")
  $out = Join-Path $reports $stamp
  New-Item -ItemType Directory -Path $out -Force | Out-Null

  # run_journal.exe treats additional command-line switches as its own.
  # Pass our configuration to the Python journal via JSON instead.
  $configObject = @{
    root      = (Resolve-Path $RootParts).Path
    framework = (Resolve-Path $Framework).Path
    report    = $out
    project   = $Project
  }

  $configObject |
    ConvertTo-Json -Depth 5 |
    Set-Content -Path $config -Encoding UTF8

  $env:NX_PIPELINE_CONFIG = $config

  Write-Host "NX executable : $nxExe"
  Write-Host "Journal       : $journal"
  Write-Host "Parts root    : $RootParts"
  Write-Host "Framework     : $Framework"
  Write-Host "Report folder : $out"

  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $nxExe
  $psi.Arguments = "`"$journal`""
  # Keep stdout/stderr attached to this console so progress and ETA
  # from the NX journal are visible immediately.
  $psi.RedirectStandardOutput = $false
  $psi.RedirectStandardError = $false
  $psi.UseShellExecute = $false

  # Explicitly pass the config path to the child process.
  $psi.EnvironmentVariables["NX_PIPELINE_CONFIG"] = $config

  $process = New-Object System.Diagnostics.Process
  $process.StartInfo = $psi
  [void]$process.Start()

  if (-not $process.WaitForExit($TimeoutMinutes * 60 * 1000)) {
    try { $process.Kill() } catch {}
    throw "NX pipeline timed out after $TimeoutMinutes minutes."
  }

  if ($process.ExitCode -ne 0) {
    throw "NX Journal ExitCode $($process.ExitCode). See the NX journal output above."
  }

  $json = Join-Path $out "results.json"
  if (-not (Test-Path $json)) {
    throw "Pipeline completed without results.json: $out"
  }

  New-Item -ItemType Directory -Path $webData -Force | Out-Null
  Copy-Item $json (Join-Path $webData "latest.json") -Force

  Write-Host ""
  Write-Host "Pipeline completed successfully."
  Write-Host "Report: $json"
  Write-Host "Latest: $(Join-Path $webData 'latest.json')"
}
finally {
  Remove-Item Env:NX_PIPELINE_CONFIG -ErrorAction SilentlyContinue
  if (Test-Path $config) { Remove-Item $config -Force -ErrorAction SilentlyContinue }
  if (Test-Path $lock)   { Remove-Item $lock -Force -ErrorAction SilentlyContinue }
}
