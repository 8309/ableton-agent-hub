# Release Validation: v0.2.0-alpha

This record covers the public export sourced from private development checkpoint
`3b25c6f044f7f5624f5ad2ecc96b4ef4400ffeca`.

## Required Checks

- Public export dry-run and actual export complete without private-path findings.
- Export manifest reports no working-tree overlay for exported files.
- Full public unit-test discovery passes.
- Hub rebuild and packaged-resource synchronization pass.
- Source distribution and wheel build successfully.
- Installed CLI reports `0.2.0a0` and exposes `initial-read`.
- Public repository contains no songs, handoff, local SQLite catalog, runtime
  cache, named Windows user profile, or private workspace path.

## Results

| Check | Result |
| --- | --- |
| Private development source | `3b25c6f044f7f5624f5ad2ecc96b4ef4400ffeca` |
| Export dry-run | 120 allowlisted files, passed |
| Export manifest | 120 files, `source_has_working_tree_overlay: false` |
| Development tests | 151 passed |
| Public tests | 148 passed |
| Packaged Hub resources | 24 files synchronized with SHA-256 records |
| Package version | `ableton-agent 0.2.0a0` |
| Installed CLI smoke test | `initial-read --depth quick` completed read-only |
| Smoke-test Set | 16 ordinary Tracks, 3 Groups, 2 Returns, Main, 120 clips |

## Artifacts

| Artifact | SHA-256 |
| --- | --- |
| `ableton_agent_hub-0.2.0a0-py3-none-any.whl` | `2c79d039bd8340e9771847312c10c02a142f0694c94502e776aebbb0a65b8ae4` |
| `ableton_agent_hub-0.2.0a0.tar.gz` | `4e7beace85322bbe7c210c25076acda431f26a66cf076a3bbca3ee29aca44c8c` |

The artifacts are rebuilt from the frozen release tree before the tag is
created; the hashes above are replaced if the final build changes them.
