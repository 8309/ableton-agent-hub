# Use $args (not named parameters) to forward Python's flags verbatim.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'agent_python.ps1')
$python = Resolve-AgentPython -RepoRoot $repoRoot
$bridgeRoot = Join-Path $repoRoot 'ableton_agent\python'
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = if ($previousPythonPath) {
    "$bridgeRoot;$previousPythonPath"
} else { $bridgeRoot }
try {
    & $python @args
    exit $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $previousPythonPath
}
