# Neo4j Cypher Query Fix Design

## Context

The production individual-learning profile approval flow fails before job search.
Neo4j Aura 2025.x rejects the CV-skill projection query with:

```text
WITH is required between SET and MATCH
```

The current repository tests assert query fragments through a fake session but do
not submit Cypher to a real parser. As a result, the invalid clause transition was
not detected before deployment.

## Scope

- Fix the CV-skill projection query in
  `backend/app/modules/individual_learning/neo4j_repository.py`.
- Audit every top-level query in that module against the production Aura parser.
- Add regression coverage for clause-boundary syntax in the CV-skill query.
- Preserve the existing graph model, parameters, write semantics, and public API.

Restoring historical graph data, changing the job-search provider, and refactoring
the individual-learning workflow are outside this change.

## Cypher Design

The minimal production fix carries `u` across the write/read clause boundary:

```cypher
CYPHER 25
MERGE (u:USER {id: $user_id})
SET u:INDIVIDUAL
WITH u
OPTIONAL MATCH (u)-[stale:HAS_SKILL]->(existing:SKILL:CV_SKILL)
```

The query continues to:

- `MERGE` the user on the existing `USER.id` uniqueness constraint;
- remove stale `HAS_SKILL` relationships for CV skills absent from the new CV;
- `MERGE` normalized `SKILL:CV_SKILL` nodes;
- `MERGE` relationships only after both endpoints are bound; and
- return the number of normalized skills written.

All top-level queries in the module will use the `CYPHER 25` prefix. Existing
labels, relationship types, directions, and property names remain unchanged.

## Validation Strategy

Validation is read-only against Neo4j Aura:

1. Inspect constraints and indexes before evaluating queries.
2. Extract each constant query passed to `session.run`.
3. Supply representative parameters for each query.
4. Submit `CYPHER 25 EXPLAIN ...` to Aura so Neo4j parses and plans the query
   without executing writes.
5. Reject any plan that reports a syntax error, missing schema object, Cartesian
   product, or label-free all-node scan introduced by this change.

No production graph writes are part of query validation.

## Automated Tests

The existing fake-session tests remain responsible for parameters and intended
graph semantics. A focused regression test will require the CV-skill query to
carry `u` through `WITH` before `OPTIONAL MATCH`, and will fail against the current
deployed query before production code is changed.

Verification will run in Docker:

- targeted individual-learning Neo4j repository tests;
- targeted profile-review and job-workflow tests;
- backend Ruff check and format check; and
- read-only Aura `EXPLAIN` validation for every query in the module.

## Rollout and Recovery

The code change will be isolated on `fix/neo4j-cypher-queries`. No deployment or
production write is included until the tests and Aura `EXPLAIN` audit pass. After
deployment, the user can retry profile approval; the existing idempotent `MERGE`
operations will create the CV-skill projection in the new Aura instance.

Rollback consists of routing Azure Container Apps traffic back to the prior
backend revision. PostgreSQL profile data and target titles remain available if
the retry fails.
