# Shared resolver only: no process startup, installation, or fallback search.
function Resolve-AgentPython {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    $candidate = if ($env:ABLETON_AGENT_PYTHON) {
        $env:ABLETON_AGENT_PYTHON
    } else {
        Join-Path $RepoRoot '.venv\Scripts\python.exe'
    }
    if (-not [IO.Path]::IsPathRooted($candidate) -or
        -not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Ableton Python is unavailable at '$candidate'. Run scripts\install_ableton_mcp.ps1, or set ABLETON_AGENT_PYTHON to an existing absolute python.exe path. No fallback was attempted."
    }
    return $candidate
}
