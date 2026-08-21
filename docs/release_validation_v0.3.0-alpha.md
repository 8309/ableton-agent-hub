# Release Validation: v0.3.0-alpha

This record covers the public export sourced from private development checkpoint
`4defdfa2fdc43819cdb86c1a00c6dbfda744fbe4`.

## Required Checks

- Public export completes from a clean detached source worktree.
- Export manifest reports no working-tree overlay for exported files.
- Full public unit-test discovery passes.
- Hub rebuild and packaged-resource synchronization pass.
- Source distribution and wheel build successfully.
- A clean temporary installation verifies all packaged Hub resources.
- Public repository contains no songs, handoff, local catalog database, runtime
  cache, named Windows user profile, or private workspace path.

## Results

| Check | Result |
| --- | --- |
| Private development source | `4defdfa2fdc43819cdb86c1a00c6dbfda744fbe4` |
| Export manifest | 130 files, `source_has_working_tree_overlay: false` |
| Public tests | 164 passed |
| Packaged Hub resources | 27 files rebuilt and synchronized |
| Package version | `ableton-agent 0.3.0a0` |
| Clean install smoke test | 27 files verified; second install changed 0 files |

## Artifacts

| Artifact | SHA-256 |
| --- | --- |
| `ableton_agent_hub-0.3.0a0-py3-none-any.whl` | `a6c958518cc149b46d9866f0f97639b77c0111cc72660d22b21dc83425bf0017` |
| `ableton_agent_hub-0.3.0a0.tar.gz` | `e83c9454da2e23d65b228ee796eed6437273a867bfc0fbfa4de01d2a7d4c4faa` |
| `Ableton Agent Hub.amxd` | `dd76d76ec7b89c951dd8c02aafb60d45620f57045f85eb7643ecbd9dc84d6b1e` |
