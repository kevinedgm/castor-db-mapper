---
name: castor-db-audit
description: "Inspect evidence quality, potential orphan relationships, unsupported dynamic SQL, missing schema declarations, and stale code-to-database mapping."
---

# Audit evidence quality

1. Run `python -m castor --output /project/.castor report` and inspect unresolved items first.
2. Compare `DECLARED` links against `CODE_OBSERVED`; do not assume either is correct at runtime without schema/environment verification.
3. Identify `INFERRED` links from naming similarity and recommend source inspection or authorized read-only integrity checks.
4. Detect files with zero parsed queries that appear to use indirect repositories, heredoc statements, or an unsupported language. Classify as coverage gaps.
5. Report exactly which relation is uncertain, why, its source paths, consequences and safe verification method.
6. Never generate automatic DDL changes or run write queries. This is a diagnosis, not a migration.
