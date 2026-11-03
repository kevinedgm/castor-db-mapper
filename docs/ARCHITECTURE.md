# Castor DB Mapper architecture (0.3.0)

## Aim

Persistent and portable **evidence graph** linking source files, SQL operations, tables and columns. It is an index that helps agents locate original sources, not a full logical model or verified database ER diagram.

## Collection pipeline

Source files → **adapter** chosen by extension (`castor/adapters/`) → `Statement(sql, line, dynamic)` → language-agnostic SQL analysis (`scan_sql`, `sql_tokens`) → per-file records keyed by SHA-256 (`.castor/files.json`) → canonical graph (`.castor/graph.json`) → SQLite query index (`.castor/index.sqlite`) → filtered queries and offline HTML SVG.

No dependency on a running application, external service, Graphify, database credentials, or network.

## Adapters

- **Query adapters** (`QueryAdapter` in `adapters/base.py`): know where SQL lives in one file type. Shipped: `php` (string literals), `sql` (statements).
- **Entry adapter** (`adapters/entries.py`): records raw references to endpoint files from JS/TS/Vue/HTML/PHP. The core resolves them against scanned files: root-relative, then caller-relative (includes try caller-relative first), then a unique path suffix (strips deployment prefixes such as `/app/`). Unresolved references become warnings, never edges.
- **Dispatch** (`adapters/dispatch.py`, used by the PHP adapter's optional `structure()`): masks strings/comments, finds function spans by brace matching, and treats a `switch` on an action-like parameter (`action`, `accion`, `op`, ...) or any top-level `switch` as dispatch. Each `case 'x'` becomes an action whose reach is its case body plus same-file functions it calls, transitively. The front-end action sent with a call is read from the call line, the following lines, or the payload built in the preceding lines (stopping at another endpoint reference or a function boundary).
- Planned: schema adapters (migrations, ORM models) and query adapters for other languages.

Per-file records carry an `analyzer` version; when it changes, cached records are rebuilt.

## Nodes

- `file`: relative repo file path.
- `query`: observed SQL statement with source path/line, operation and sanitized excerpt.
- `table`: static table name found in SQL.
- `column`: column declared in DDL or observed in qualified join predicates.
- `action`: one dispatched operation inside an endpoint file.

## Edges

- `CONTAINS_QUERY`: file → query.
- `READ`, `WRITE`, `SCHEMA`: query → table.
- `HAS_COLUMN`: table → column.
- `RELATES_TO`: column → column, with `DECLARED` when found in `CREATE TABLE FOREIGN KEY`, or `CODE_OBSERVED` when an equality predicate connects two qualified table aliases.
- `CALLS_ENDPOINT`: file → server file referenced by a URL literal (meta: `via`, `resolution`, `raw`).
- `INCLUDES`: server file → file it includes/requires.
- `HAS_ACTION`: file → `action:<file>#<name>`.
- `RUNS_QUERY`: action → query reachable from it.
- `CALLS_ACTION`: caller file → action, when the call's action name exists in the target (or is resolved later through includes by `endpoints`).
- `POSSIBLE_RELATION`: low-confidence inferred naming similarity, never equivalent to a physical constraint.

Each edge has a deterministic ID, evidence and source line when available. Declarations and code observations can coexist. `DECLARED` means **found in source DDL**, not **verified in live production schema**.

## Access

`python -m castor scan PROJECT` performs a full first pass and later skips unchanged files. `python -m castor --output PROJECT/.castor query TERM --depth 2` retrieves a bounded subgraph. `visualize` emits a self-contained HTML with filtering and link evidence. Agent text instructions reside under `.claude/` and can be installed in other repositories via `install.py`.

## Table map

`relations_map()` aggregates `RELATES_TO` and `POSSIBLE_RELATION` edges into one link per unordered table pair (strongest evidence kind wins: DECLARED > CODE_OBSERVED > INFERRED), with column pairs, query and file counts, and up to 8 evidence locations. `export_relations_html()` injects it into `castor/templates/relations.html` (self-contained; seeded force layout, no external JS).

## Boundaries and roadmap

- Initial tokenizer is conservative, not a PHP AST or a full SQL grammar; SQL split across PHP concatenations, heredoc, runtime query builders, complex CTEs, triggers and stored procedures can be incomplete. Results remain `CODE_OBSERVED` or unresolved, never invented.
- No live DB introspection, table row extraction, column types, PKs, unique constraints, cardinality validation, framework router analysis, in-file action dispatch, Graphify integration, or endpoint generation engine in v0.1. Endpoint design is carried out by the Claude agent after inspecting original source code.
- SQLite is a searchable index, not a Neo4j-style engine or a guarantee of graph completeness.
- The scanner uses no model calls; human/LLM analysis enriches business meaning on demand. Future versions can add parser adapters (tree-sitter/sqlglot), database metadata adapters, full PHP call graphs, Graphify import with verified schema mapping, and privacy-safe consistency checks.
