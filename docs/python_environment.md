# Python Environment

Use a project-local `.venv`, never a global or agent-internal Python runtime.
The checkout pins Python in `.python-version` and Windows development dependencies
in `ableton_agent/requirements-mcp.lock.txt`. Create it with uv or the documented
venv workflow, then install the package and optional features with
`python -m pip install -e ".[mcp,audio]"` using that environment's interpreter.

PowerShell source-checkout commands use `scripts/python.ps1`. It resolves `.venv`
and forwards failures and exit codes. `ABLETON_AGENT_PYTHON` is an explicit
absolute interpreter override, not automatic fallback. `scripts/start_ableton_mcp.ps1`
starts the server through the same resolver. The sample in `examples/mcp.toml`
requires replacing the example interpreter path; no private machine config ships.

An installed wheel can run `python -m ableton_bridge.mcp_server` without checkout
scripts. Restart the agent's MCP process after updating Python code. Hub JavaScript
updates separately require the user to reload the device in the intended Set.
