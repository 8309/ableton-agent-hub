param([string]$Python = '')

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$venvRoot = Join-Path $repoRoot '.venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
$version = (Get-Content -LiteralPath (Join-Path $repoRoot '.python-version') -Raw).Trim()
$requirements = Join-Path $repoRoot 'ableton_agent\requirements-mcp.lock.txt'
$uv = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue
if (-not $uv) { throw 'uv is required. Install uv first; no system Python fallback is used.' }

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    if (Test-Path -LiteralPath $venvRoot) {
        throw 'The .venv directory already exists but is incomplete. Inspect it before retrying; it will not be overwritten.'
    }
    if ($Python) {
        if (-not [IO.Path]::IsPathRooted($Python) -or
            -not (Test-Path -LiteralPath $Python -PathType Leaf)) {
            throw '-Python must be an existing absolute interpreter path.'
        }
        $actual = & $Python -c 'import platform; print(platform.python_version())'
        if ($LASTEXITCODE -ne 0 -or $actual -ne $version) {
            throw "The supplied interpreter must match .python-version ($version)."
        }
        & $uv.Source venv --python $Python --no-python-downloads $venvRoot
    } else {
        & $uv.Source venv --python $version --managed-python $venvRoot
    }
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the project Python environment.' }
}

$actual = & $venvPython -c 'import platform; print(platform.python_version())'
if ($LASTEXITCODE -ne 0 -or $actual -ne $version) {
    throw "Existing .venv must match .python-version ($version). No packages were changed."
}
& $uv.Source pip sync --python $venvPython $requirements
if ($LASTEXITCODE -ne 0) { throw 'Failed to install pinned Ableton dependencies.' }
& $uv.Source pip check --python $venvPython
if ($LASTEXITCODE -ne 0) { throw 'Ableton dependency compatibility check failed.' }
& $venvPython -c "import mcp; print('Ableton Python environment ready')"
if ($LASTEXITCODE -ne 0) { throw 'MCP import verification failed.' }
