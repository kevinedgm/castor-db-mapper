---
name: castor-endpoint-plan
description: "Plan a safe endpoint using database graph lookups, existing API and query code, evidence, permissions and unresolved gaps."
---

# Endpoint planning

1. Restate the caller, required records, filters, sorting, pagination and response. Do not invent unspecified data semantics.
2. Refresh Castor's index then query separately for each business noun. Inspect linked PHP statements, controllers, service functions, and routes.
3. Identify read paths and write paths, including implicit joins that are not enforced by constraints.
4. Classify data requirements as existing, partial, absent or unknown. Only claim absence after searching active source beyond the limited scanner.
5. Define endpoint method, URL, auth/role checks, validation, response schema, status codes, error handling, transaction/idempotency rules as applicable.
6. Show file ownership and smallest reuse-based change set, risks, rollback, tests and acceptance criteria.
7. Do not implement or mutate schema under a planning request; request a separate implementation action if needed.
