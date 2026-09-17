# Hub Status Panel

The builder adds a passive request/reply observer and a 620x148 dark jsui dashboard
using Max mgraphics. Source routing and UDP messages remain unchanged. No new public route,
Python client, timer, LiveAPI read, playback or write is introduced.

The panel shows the last command, request ID, observed elapsed milliseconds,
brief error and state: IDLE, WAITING, OK, FAILED, UNKNOWN or REPLIED (ping).
OK means the module emitted `ok:true`, not that UDP delivery was confirmed or
that every write was independently verified. Inspect and partial reads can be OK;
the client structured result remains authoritative for applied/verified/partial.
Ping is explicitly not evidence of module readiness.

Only matching request ID and command can finish an operation. Parameter progress
does not finish it. Missing final replies leave WAITING; no automatic retry or
timeout inference is made. Max UI may not repaint while a synchronous LiveAPI
call blocks. This panel cannot independently diagnose a blocked Max scheduler.

The version label identifies the loaded patch build, not all its loaded modules.
Disk installation and MCP versions are unknown to the panel; use ableton_status
for those existing evidence sources and explicit module probes for readiness.
Build fingerprints already include mode, dependency directory, builder and all JS.

Overview shows transport, last operation, and last explicit module probes (not
continuous health). Unknown MCP/disk versions remain unknown. History retains 32
compact requests, five per page; selecting one opens Diagnostics. Diagnostics
shows the request ID, requested target IDs, action, outcome, and reported
applied/verified fields, with paginated errors. READ/INSPECT/WRITE describe request
intent; PROBE explicitly identifies health checks, including insertion checks.
No button sends Live commands. Tabs and arrows only navigate local UI state.

Text is measured before drawing and clipped with ellipses in overview/history.
Diagnostics wraps and paginates. Stored error text is bounded to 2048 characters;
client replies retain the original detailed error. Sending a bang to the observer
prints its latest diagnostic to Console; normal operations do not log.
Starting a new request before a final reply changes the old WAITING record to
UNKNOWN. It is not inferred to have failed or succeeded. UI history resets on
device reload; probe records reset on an observed different song ID.

Offline renders exercise the actual paint function through a canvas adapter;
these are visual checks, not evidence of native Max rendering or interaction.

## Acceptance Gate

Automated coverage: unchanged routing, original wire preservation, presentation
bounds, local dependency packaging, correlation, progress, errors and recovery.
Manual Live acceptance is pending: reload, confirm the version and normal device
view, run sequential status/read and a safe bad-target read, confirm recovery and
long-text readability. No deliberate Live hang or song write is required.
