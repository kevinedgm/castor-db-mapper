---
name: castor-endpoint-plan
description: "Plan a safe endpoint using database graph lookups, existing API and query code, evidence, permissions and unresolved gaps."
---

# Endpoint planning

1. Restate the caller, required records, filters, sorting, pagination and response. Do not invent unspecified data semantics.
2. Refresh Castor's index, then run `python -m castor --output <project>/.castor endpoints "<noun>"` to see existing endpoints that touch each business noun: callers (`file:line`), tables read/written and the file each table comes from (`from`). Separate tables that come from shared includes (auth, session, navigation) from the endpoint's own data. When the file dispatches by action, use `actions[]` (each with its callers and tables) as the unit of reuse, and treat `unmatched_actions` as calls to verify, not as features that exist. Then `query` each noun and inspect the cited statements, controllers and routes.
3. Identify read paths and write paths, including implicit joins that are not enforced by constraints.
4. Classify data requirements as existing, partial, absent or unknown. Only claim absence after searching active source beyond the limited scanner.
5. Define endpoint method, URL, auth/role checks, validation, response schema, status codes, error handling, transaction/idempotency rules as applicable.
6. Show file ownership and smallest reuse-based change set, risks, rollback, tests and acceptance criteria.
7. Do not implement or mutate schema under a planning request; request a separate implementation action if needed.
