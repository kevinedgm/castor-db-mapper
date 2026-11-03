# Castor DB Mapper

**Portable backend/database knowledge graph for Claude Code.** Analyze repositories that talk to SQL databases, keep a local searchable evidence index, identify implicit table relationships, map which front-end code calls which endpoint and which tables each endpoint touches, and plan endpoints based on existing code.

The core is language-agnostic; language support lives in small adapters (`castor/adapters/`). v0.2 ships adapters for PHP, `.sql` files and endpoint references from JS/TS/Vue/HTML/PHP.

> **Status: v0.2 experimental.** The initial functional scanner is deliberately narrow. It does not run PHP, connect to databases or claim that code-observed relationships are physical `FOREIGN KEY` constraints.

## Quick start

Python 3.10+; no external Python dependencies.

```bash
# From this repository
python -m castor scan /path/to/other-project
python -m castor --output /path/to/other-project/.castor report
python -m castor --output /path/to/other-project/.castor query "muestras" --depth 2
python -m castor --output /path/to/other-project/.castor visualize --term "muestras"
python -m castor --output /path/to/other-project/.castor endpoints "muestras"
```

Open `/path/to/other-project/.castor/graph.html` in a browser. It is an offline HTML graph of the relevant subgraph with node filtering and evidence details. Scan again after code changes; unchanged files are reused by SHA-256.

## Install Claude Code agents and skills in another project

```bash
python install.py /path/to/other-project
```

This copies **two agents** and **five skills** under the target `.claude/` directory. Existing files are never overwritten unless `--force` is explicitly supplied. You can also copy them to your global Claude Code configuration as appropriate. For projects without Castor source installed, call the scanner from the Castor checkout (`cd /path/to/castor-db-mapper` and run `python -m castor scan /your/project`).

Example in Claude Code:

> Usa el agente `castor-db-mapper` para mapear todas las escrituras y lecturas de muestras. Identifica qué tablas tienen relaciones lógicas sin una FK declarada y registra su evidencia.

> Usa `castor-endpoint-architect` para planear un endpoint que consulte el historial de análisis de un cliente. Reutiliza PHP existente y señala lo que no pudiste comprobar.

## What's actually indexed

- PHP literals containing SQL, plus `.sql` files.
- Static `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `REPLACE` and basic `CREATE/ALTER` table references.
- Source file/line references, read/write evidence, tables and columns from basic `CREATE TABLE` DDL.
- `alias.field = alias.field` cross-table predicates as **CODE_OBSERVED** relationship evidence.
- Recognized `CREATE TABLE ... FOREIGN KEY ... REFERENCES ...` as **DECLARED** evidence from the source file.
- Optional **INFERRED** low-confidence table associations from `_id` / `id_` naming.
- Unresolved statements, source hashes, bounded graph queries and HTML export.
- **Endpoint map** (`endpoints`): string literals naming a server file (`axios.get('mod/api.php')`, `fetch(...)`, `href`, `include/require`) become `CALLS_ENDPOINT` / `INCLUDES` edges, resolved only against files that exist in the repo. For each endpoint you get its callers (`file:line`, mechanism) and the tables it reads/writes, following includes, with the file each table comes from.

## Adding a language

Write a class with `name`, `extensions` and `statements(path, source) -> list[Statement]` in `castor/adapters/`, and append it to `QUERY_ADAPTERS` in `castor/adapters/__init__.py`. The SQL analysis, graph, index and endpoint map are reused unchanged. Endpoint file types are listed in `ENDPOINT_SUFFIXES` (`castor/adapters/entries.py`).

**Important:** `DECLARED` indicates an FK found in the SQL source, **not** proof that the live database has the constraint. All graphs describe what the scanner observed, not necessarily every behavior of the running system. See [architecture and limits](docs/ARCHITECTURE.md).

## Persistent project catalog

```text
project/.castor/
  files.json       Per-file analysis, SHA cache and findings
  graph.json       Normalized nodes/edges and provenance
  index.sqlite     Local searchable index
  manifest.json    Coverage, unresolved count and limitations
  graph.html       Interactive offline graph (on demand)
```

Generated catalogs can reveal database structure, so keep them private unless intentionally shared. This repository ignores `.castor/` by default.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests exercise missing-FK joins, explicit FK declarations, read/write operations, dynamic SQL warnings, incremental sync and deletion.

## Roadmap

Query adapters for Python/JS/Java/Go string SQL, schema adapters for migrations and ORM models (Prisma, Django, Eloquent), per-action endpoint dispatch (`?accion=`), better PHP AST/SQL grammar adapters, more SQL dialects, live schema *metadata-only* adapters, confirmed Graphify ingestion format, route/permission traces, and stronger business entity modeling. These are **not** present in v0.2.
