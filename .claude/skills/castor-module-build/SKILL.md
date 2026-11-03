---
name: castor-module-build
description: "Build a documented backend module (e.g. /usuarios: list, get, create, update, deactivate) from Castor evidence, following the target project's own architecture. Use when the user asks to generate or migrate the backend of a domain so a frontend can connect to it later."
---

# Build a backend module from evidence

Goal: one domain folder with a tested API, a frontend client and a contract document, built on what the existing code proves. Planning lives in `castor-endpoint-plan`; this skill implements, so only use it when the user asked for code.

## 1. Locate the domain (evidence, not guesses)

1. Refresh the index: `python -m castor scan <project>`.
2. `python -m castor --output <project>/.castor endpoints "<main table or noun>"`. Keep endpoints whose **own** tables (not ones that only come from auth/layout includes) include the domain tables. Their `actions[]` are the operations that exist today, with their callers.
3. `python -m castor --output <project>/.castor query "<main table>" --depth 2` for implicit relations (`RELATES_TO`), then read the cited `file:line`.
4. Read the legacy endpoint in full and its front-end callers. Write down: each action, inputs, outputs, tables read/written, transactions and side effects (soft vs hard delete, audit columns, who-did-it columns).

## 2. Read the project's rules before writing

Read `AGENTS.md`/`CLAUDE.md`/`ARCHITECTURE.md` (or equivalents), the module skeleton, and one recently migrated module as a reference. Reuse the project's auth guard, permission check, CSRF, DB connection and password hashing; never create parallel ones. Follow its folder layout, naming and indentation.

## 3. Design the contract

- Separate reads (GET) from writes (POST + CSRF). One action per operation; split overloaded legacy actions (e.g. create/update in one).
- Collections sent by the client (permissions, assignments) are the **final state**; the server computes the diff.
- Keep legacy semantics that the data depends on (soft delete flags, status codes, column defaults) unless the user asks otherwise.
- Identity, actor and permission level come from the session, never from the request.
- Errors: 401/403 auth, 404 missing, 405 method, 409 business rule, 422 with per-field messages, 503 for missing migrations, 500 generic with detail only in the server log.
- Mark undecidable choices (ambiguous permission ids, level semantics) as **pending** in code comments and README, and fail closed.

## 4. Implement in layers

`api` (HTTP, guard, dispatch) → `service` (rules, no HTTP) → `repository` (SQL, bound parameters only) + pure `validation`. The service takes a repository interface so rules are testable in memory. Validate references that have no declared FK (Castor `CODE_OBSERVED`) before writing. Wrap multi-table writes in one transaction. Add a small frontend client (fetch wrapper with CSRF and typed errors).

## 5. Prove it

- Unit: validation and service with an in-memory repository (duplicates, references, diff sync, self-lockout, rollback).
- Integration: a disposable MySQL/MariaDB schema with only the columns the module uses; create and drop it inside the test; never point tests at real data.
- HTTP: the real guard through `php -S` and a temporary router outside the repo (401, 403, CSRF, 405, 422, 409).
- Client: node tests with a fake `fetch`.
State plainly what was not tested (production data, real permission ids).

## 6. Document and hand over

- `README.md`: purpose, files, dependencies, data map (from Castor), permissions, DB prerequisites, test commands, legacy routes, pending items.
- `docs/API.md`: every action with request/response, status codes and what the UI should do, a connection example, and a legacy-to-new equivalence table.
- `docs/MEJORAS.md` (or `IMPROVEMENTS.md`): **facts** found in the legacy code with `file:line` and risk, kept apart from **proposals** with their reason and effort.
- Register the module where the project tracks modules. Leave legacy endpoints untouched unless the user asks; propose the bridge.
