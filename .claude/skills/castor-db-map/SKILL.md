---
name: castor-db-map
description: "Look up tables, SQL operations, implicit relationships, writers/readers, and file evidence from Castor's local knowledge graph."
---

# Query the knowledge graph

1. Ensure the `.castor/` catalog exists and is up-to-date.
2. Run `python -m castor --output /path/to/project/.castor query '<entity-name>' --depth 2 --limit 100` from Castor's installation directory.
3. Extract the relevant `nodes` and `edges` with their source references. Open each cited source file for critical details.
4. If an edge has `evidence.kind=DECLARED`, it was recognized in SQL DDL; `CODE_OBSERVED` signals a query association, `INFERRED` is merely a naming hypothesis.
5. When a result is not located, check coverage and perform a bounded code search before declaring that it doesn't exist.

To give a person a visual overview, run `python -m castor --output /path/to/project/.castor map` and point them to `.castor/relations.html`.

For relation questions, report source/target, direction where known, proof, certainty, and unresolved cardinality. Do not infer one-to-many solely from names.
