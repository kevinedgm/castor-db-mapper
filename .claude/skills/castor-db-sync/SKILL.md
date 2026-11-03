---
name: castor-db-sync
description: "Refresh Castor's persisted code-to-database graph after project changes, reusing unchanged per-file analysis by SHA-256."
---

# Incremental sync

1. Run `python -m castor scan /path/to/project` (no `--full`); the scanner caches unchanged supported files and removes records for deleted files.
2. Compare `.castor/manifest.json` metrics `rescanned` and `cached` with expectations.
3. Query the affected business entity, review file:line citations and validate that reindexed relationships are still present.
4. For a suspected indexing bug or changed parsing rules, run again with `--full`.
5. Document warnings and unknowns. Avoid auto-running database introspection or code changes.

The incremental mode still rebuilds the small indexed SQLite representation from cached per-file records. Do not describe it as a full incremental graph database engine.
