# Castor DB Mapper architecture (0.1.0)

## Aim

Persistent and portable **evidence graph** linking source files, SQL operations, tables and columns. It is an index that helps agents locate original sources, not a full logical model or verified database ER diagram.

## Collection pipeline

`PHP/SQL files` → lightweight lexing (`scan_php_literals`, `sql_tokens`) → per-file records keyed by SHA-256 (`.castor/files.json`) → canonical graph (`.castor/graph.json`) → SQLite query index (`.castor/index.sqlite`) → filtered queries and offline HTML SVG.

No dependency on a running application, external service, Graphify, database credentials, or network.

## Nodes

- `file`: relative repo file path.
- `query`: observed SQL statement with source path/line, operation and sanitized excerpt.
- `table`: static table name found in SQL.
- `column`: column declared in DDL or observed in qualified join predicates.

## Edges

- `CONTAINS_QUERY`: file → query.
- `READ`, `WRITE`, `SCHEMA`: query → table.
- `HAS_COLUMN`: table → column.
- `RELATES_TO`: column → column, with `DECLARED` when found in `CREATE TABLE FOREIGN KEY`, or `CODE_OBSERVED` when an equality predicate connects two qualified table aliases.
- `POSSIBLE_RELATION`: low-confidence inferred naming similarity, never equivalent to a physical constraint.

Each edge has a deterministic ID, evidence and source line when available. Declarations and code observations can coexist. `DECLARED` means **found in source DDL**, not **verified in live production schema**.

## Access

`python -m castor scan PROJECT` performs a full first pass and later skips unchanged files. `python -m castor --output PROJECT/.castor query TERM --depth 2` retrieves a bounded subgraph. `visualize` emits a self-contained HTML with filtering and link evidence. Agent text instructions reside under `.claude/` and can be installed in other repositories via `install.py`.

## Boundaries and roadmap

- Initial tokenizer is conservative, not a PHP AST or a full SQL grammar; SQL split across PHP concatenations, heredoc, runtime query builders, complex CTEs, triggers and stored procedures can be incomplete. Results remain `CODE_OBSERVED` or unresolved, never invented.
- No live DB introspection, table row extraction, column types, PKs, unique constraints, cardinality validation, backend route analysis, Graphify integration, or endpoint generation engine in v0.1. Endpoint design is carried out by the Claude agent after inspecting original source code.
- SQLite is a searchable index, not a Neo4j-style engine or a guarantee of graph completeness.
- The scanner uses no model calls; human/LLM analysis enriches business meaning on demand. Future versions can add parser adapters (tree-sitter/sqlglot), database metadata adapters, full PHP call graphs, Graphify import with verified schema mapping, and privacy-safe consistency checks.
