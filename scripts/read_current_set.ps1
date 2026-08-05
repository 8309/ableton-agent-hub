[CmdletBinding()]
param(
    [ValidateSet("progressive", "quick", "full")]
    [string]$Depth = "progressive",
    [string]$Output,
    [switch]$PrintFull,
    [switch]$IncludeRawNotes,
    [string[]]$NotesTrack = @(),
    [int]$MaxNoteClips = 512,
    [double]$Timeout = 5.0,
    [double]$PingTimeout = 1.5,
    [double]$TotalTimeout = 30.0
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$bridgeRoot = Join-Path $repoRoot "ableton_agent\python"
if (-not $Output) {
    $Output = Join-Path $repoRoot "ableton_agent\runtime\current_set_initial_read.json"
}
$quickOutput = Join-Path $repoRoot "ableton_agent\runtime\current_set_initial_read.quick.json"
$pythonDepth = if ($Depth -eq "progressive") { "full" } else { $Depth }

# A requested first read invalidates prior current-Set caches before preflight.
foreach ($cachePath in @($quickOutput, $Output)) {
    if (Test-Path -LiteralPath $cachePath) {
        Remove-Item -LiteralPath $cachePath -Force
    }
}

$liveProcesses = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -like "Ableton Live*"
})
if ($liveProcesses.Count -eq 0) {
    [pscustomobject]@{
        ok = $false
        stage = "preflight"
        error_code = "ableton_not_running"
        error = "Ableton Live is not running. Open the target Live Set before the first read."
    } | ConvertTo-Json
    exit 1
}

function Resolve-AgentPython {
    if ($env:ABLETON_AGENT_PYTHON -and (Test-Path -LiteralPath $env:ABLETON_AGENT_PYTHON)) {
        return $env:ABLETON_AGENT_PYTHON
    }

    $bundled = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $bundled) {
        return $bundled
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    throw "No Python interpreter found. Set ABLETON_AGENT_PYTHON to python.exe."
}

$pythonExe = Resolve-AgentPython
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = if ($previousPythonPath) {
    "$bridgeRoot;$previousPythonPath"
} else {
    $bridgeRoot
}

$arguments = @(
    "-m", "ableton_bridge.initial_read",
    "--depth", $pythonDepth,
    "--output", $Output,
    "--max-note-clips", $MaxNoteClips,
    "--timeout", $Timeout,
    "--ping-timeout", $PingTimeout,
    "--total-timeout", $TotalTimeout
)
if ($pythonDepth -eq "full") {
    $arguments += @("--quick-output", $quickOutput)
}
if ($PrintFull) {
    $arguments += "--print-full"
}
if ($IncludeRawNotes) {
    $arguments += "--include-raw-notes"
}
foreach ($trackName in $NotesTrack) {
    $arguments += @("--notes-track", $trackName)
}

Write-Verbose "Python: $pythonExe"
Write-Verbose "Output: $Output"
try {
    & $pythonExe @arguments
    exit $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $previousPythonPath
}
