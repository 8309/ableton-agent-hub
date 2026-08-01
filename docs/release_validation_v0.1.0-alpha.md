# v0.1.0-alpha Release Validation

Validated on 2026-08-01.

## Environment

| Component | Validated Value |
| --- | --- |
| Operating system | Windows |
| Ableton Live | Live 12.3.5 |
| Python package | `ableton-agent-hub 0.1.0a0` |
| Runtime transport | UDP request `7400`, reply `7401` |
| Runtime source checkpoint | `e8c22ce` |

## Clean Checkout

The release candidate was cloned into a new directory on a machine with
`core.autocrlf=true`. The first attempt exposed line-ending-sensitive export
hashes. Checkpoints `b5222fb` and `e8c22ce` added explicit LF attributes and
canonical manifest hashes.

After the fix:

- the clean checkout started with zero dirty entries;
- all 134 tests passed before the Hub build;
- the Hub and all declared JavaScript resources rebuilt deterministically;
- the checkout remained clean after build and resource synchronization;
- all 134 tests passed again after the build;
- built and packaged Hub SHA-256 values both equaled
  `beb3376305560b4b54da59aeb713a86c902e61e0734830646f4f427b186139f0`.

## Wheel And Temporary Installation

The wheel was installed into a new virtual environment. The CLI reported
version `0.1.0a0`.

- Installation dry-run into an empty target planned 24 files.
- Installation wrote and verified 24 files.
- A second dry-run planned zero changes.
- The validated wheel SHA-256 was
  `0dfbcecb21805464c38e187c612feec2b49c74ddf70ec6a5e75750550a99ff2b`.

## User Library Installation

The existing Hub directory was backed up and recorded with per-file SHA-256
values before installation. The release installer:

- kept all 31 existing files present;
- left 21 of 24 managed files unchanged;
- normalized line endings in three managed JavaScript files;
- left seven older unmanaged JavaScript files untouched;
- verified all 24 managed release files;
- reported zero remaining changes on the post-install dry-run.

No Live preferences, songs, ALS files, ports, or global Python installation were
changed.

## Live Validation

The installed Hub was manually loaded once in a disposable empty Live Set.

- `/ping` returned a correlated reply from localhost.
- `/tempo` read the current global tempo as `120 BPM`.
- `/track_management scan_hierarchy` used a two-item page size and completed
  four pages with one stable collection token, no warnings, and no partial
  result.
- The scan returned four ordinary tracks, two Return Tracks, and Main.
- A `120 -> 120` tempo dry-run reported no value change.
- A same-value commit completed and independent readback remained `120 BPM`.
- A final ping confirmed the Hub remained healthy.

## Known Validation Finding

The same-value tempo commit returns `changed:true` even though the before,
target, and readback values are all `120`. In this alpha that field means the
commit write path executed, not necessarily that the numeric value differed.
Callers should compare `tempo_before`, `target_tempo`, and readback when they need
value-change semantics.

## Result

The clean-checkout, package, installation, reload, read, bounded-read, dry-run,
minimal commit, and readback gates passed. GitHub remote creation, tagging, and
upload remain separate publication actions.
