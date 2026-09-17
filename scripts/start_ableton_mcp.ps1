$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot 'python.ps1') -m ableton_bridge.mcp_server
exit $LASTEXITCODE
