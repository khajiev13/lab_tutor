---
name: neo4j-cypher
description: Best practices for writing Neo4j Cypher queries using map projections, list comprehensions, and COLLECT subqueries instead of returning nodes
---

# Neo4j Cypher Best Practices

This skill enforces modern Cypher query patterns that are more performant, type-safe, and maintainable. The core tools are **map projections** (instead of returning nodes), **list comprehensions** (instead of `OPTIONAL MATCH` for unordered collections), and **`COLLECT {}` subqueries** (instead of `OPTIONAL MATCH` when ordering is needed).

## Core Rules

### 0. ALWAYS Use neo4j.int() for Integer Parameters

**CRITICAL:** JavaScript numbers are 64-bit floats. When passing integer parameters to Neo4j, you MUST wrap them with `neo4j.int()`:

**❌ DON'T:**

```typescript
session.run("MATCH (t:Team {id: $id}) RETURN t", { id: 123 });
// ERROR: "Expected INTEGER but was FLOAT"
```

**✅ DO:**

```typescript
import neo4j from "neo4j-driver";

session.run("MATCH (t:Team {id: $id}) RETURN t { .id, .name }", {
  id: neo4j.int(123),
});
```

**When to use `neo4j.int()`:**

- IDs: `neo4j.int(teamId)`
- LIMIT: `neo4j.int(limit)`
- Numeric filters: `neo4j.int(count)`
- Any integer parameter

### 0.5. ALWAYS Use toString() for DateTime Properties

**CRITICAL:** Neo4j DateTime objects must be converted to strings in the query using `toString()`:

**❌ DON'T:**

```cypher
RETURN m { .id, .dateTime } AS match
// Returns Neo4j DateTime object - hard to work with in JavaScript
```

**✅ DO:**

```cypher
RETURN m {
  .id,
  dateTime: toString(m.dateTime),
  lastUpdated: toString(m.lastUpdated)
} AS match
// Returns ISO 8601 string - easy to work with
```

**When to use `toString()`:**

- DateTime fields: `toString(m.dateTime)`
- Date fields: `toString(p.birthDate)`
- Any temporal type
- NULL-safe: `toString(null)` returns `null`

### 1. ALWAYS Use Map Projections, NEVER Return Node Objects

**❌ DON'T:**

```cypher
MATCH (t:Team {id: $id})
RETURN t
```

**✅ DO:**

```cypher
MATCH (t:Team {id: $id})
RETURN t { .id, .name, .abbreviation } AS team
```

### 2. ALWAYS Use List Comprehensions or COLLECT Subqueries, NEVER Use OPTIONAL MATCH

Choose based on whether the nested collection needs ordering:

| Need                                        | Pattern                                      |
| ------------------------------------------- | -------------------------------------------- |
| Simple traversal, order doesn't matter      | List comprehension `[(...) \| n { ... }]`    |
| Needs `ORDER BY` within the collection      | `COLLECT { MATCH ... RETURN ... ORDER BY }`  |
| Needs `WHERE`, `LIMIT`, or multi-step logic | `COLLECT { MATCH ... WHERE ... RETURN ... }` |

**❌ DON'T:**

```cypher
MATCH (p:Player {id: $id})
OPTIONAL MATCH (p)-[:PLAYS_FOR]->(t:Team)
RETURN p, t
```

**✅ DO (unordered — use list comprehension):**

```cypher
MATCH (p:Player {id: $id})
RETURN p {
  .id,
  .name,
  teams: [(p)-[:PLAYS_FOR]->(t:Team) | t { .id, .name }]
} AS player
```

**✅ DO (ordered — use COLLECT subquery):**

```cypher
MATCH (p:Player {id: $id})
RETURN p {
  .id,
  .name,
} AS player,
COLLECT {
  MATCH (p)-[:PLAYED_IN]->(m:Match)
  RETURN m { .id, .dateTime } AS match
  ORDER BY m.dateTime DESC
} AS matches
```

**Key properties of `COLLECT {}`:**

- Outer scope variables are available **without explicit import** (unlike `CALL {}`)
- Returns `[]` when the inner `MATCH` finds no rows — no null guards needed
- Supports `ORDER BY`, `WHERE`, and `LIMIT` inside the subquery
- The `RETURN` clause must return **exactly one column** (use an alias)

## Patterns and Examples

### Single Related Entity

Use `[0]` to extract single values:

```cypher
MATCH (m:Match {id: $matchId})
RETURN m {
  .id,
  .dateTime,
  homeTeam: [(m)-[:HOME_TEAM]->(t) | t { .id, .name }][0],
  awayTeam: [(m)-[:AWAY_TEAM]->(t) | t { .id, .name }][0]
} AS match
```

### Nested Relationships

```cypher
MATCH (m:Match {id: $matchId})
RETURN m {
  .id,
  .dateTime,
  competition: [
    (m)<-[:HAS_MATCH]-(i:Iteration)-[:PART_OF]->(c:Competition)
    | c { .id, .name }
  ][0]
} AS match
```

### Collections

```cypher
MATCH (t:Team {id: $teamId})
RETURN t {
  .id,
  .name,
  players: [
    (t)<-[:PLAYS_FOR]-(p:Player)
    | p { .id, .commonName, .primaryPosition }
  ]
} AS team
```

### Filtering in List Comprehensions

```cypher
MATCH (p:Player {id: $id})
RETURN p {
  .id,
  .name,
  recentMatches: [
    (p)-[:APPEARED_IN]->(m:Match)
    WHERE m.dateTime > datetime('2024-01-01')
    | m { .id, .dateTime }
  ]
} AS player
```

### Complex Nested Example

```cypher
MATCH (m:Match {id: $matchId})
RETURN m {
  .id,
  .dateTime,
  homeSquad: [(m)<-[:HOME_SQUAD]-(hs:Squad) | hs {
    .id,
    formation: [(hs)-[:USED_FORMATION]->(f) | f { .id, .name }][0],
    players: [
      (a:Appearance)-[:IN_SQUAD]->(hs)
      | a {
        shirtNumber: a.shirtNumber,
        player: [
          (a)-[:FOR_PLAYER_ITERATION]->(pi)<-[:HAS_PLAYER_ITERATION]-(p)
          | p { .id, .commonName }
        ][0],
        position: [(a)-[:IN_POSITION]->(pos) | pos { .id, .name }][0]
      }
    ]
  }][0]
} AS match
```

### COLLECT Subquery with Ordered Nested Collections

Use `COLLECT {}` when a nested collection needs to be ordered. Unlike list comprehensions, `COLLECT {}` supports `ORDER BY` and `WHERE` inline.

```cypher
-- Chapters with ordered sections, each section with its concepts
MATCH (cl:CLASS {id: $course_id})-[:USES_BOOK]->(b:BOOK)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER)
WITH b, ch ORDER BY ch.chapter_index

RETURN
    b.title AS book_title,
    b.authors AS book_authors,
    ch.chapter_index AS chapter_index,
    ch.title AS chapter_title,
    ch.summary AS chapter_summary,
    -- COLLECT {} used here because sections need ORDER BY section_index
    COLLECT {
        MATCH (ch)-[:HAS_SECTION]->(s:BOOK_SECTION)
        RETURN s {
            section_index: s.section_index,
            title: s.title,
            -- list comprehension still used here: concepts don't need ordering
            concepts: [(s)-[sm:MENTIONS]->(sc:CONCEPT) | {
                name: sc.name,
                description: sc.description,
                definition: sm.definition
            }]
        } AS section
        ORDER BY s.section_index
    } AS sections,
    -- list comprehension used here: skills don't need ordering
    [(ch)-[:HAS_SKILL]->(sk:BOOK_SKILL) | sk {
        .name,
        .description,
        concepts: [(sk)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c { .name, .description }]
    }] AS skills

ORDER BY ch.chapter_index
```

### Aggregations

**IMPORTANT:** When using aggregations like `collect()`, you must ORDER BY before the aggregation using WITH:

**❌ DON'T** - Can't order after aggregation:

```cypher
MATCH (t:Team)
RETURN collect(t { .id, .name }) AS teams
ORDER BY t.name  -- ERROR: can't access t after collect()
```

**✅ DO** - Order before aggregation with WITH:

```cypher
MATCH (t:Team)
WHERE toLower(t.name) CONTAINS toLower($query)
WITH t ORDER BY t.name ASC
LIMIT $limit
RETURN collect(t {
  .id,
  .name,
  .abbreviation
}) AS teams
```

### Complex Aggregations

```cypher
MATCH (t:Team)
RETURN collect(t {
  .id,
  .name,
  playerCount: size([(t)<-[:PLAYS_FOR]-(p) | p])
}) AS teams
```

## Benefits

1. **Performance**: Smaller result sets reduce network overhead
2. **Type Safety**: Returns plain objects instead of Neo4j node objects
3. **Clarity**: Query structure matches desired output structure
4. **No N+1 Queries**: Single query returns all nested data
5. **Maintainability**: Eliminates complex result mapping logic

## When to Apply

- Writing new Cypher queries
- Refactoring existing queries
- Creating repository methods
- API route database calls

## Sources

- [Cypher Refcard - Neo4j](https://neo4j.com/docs/cypher-refcard/current/)
- [CALL subqueries - Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/current/subqueries/call-subquery/)
- [COLLECT subqueries - Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/current/subqueries/collect/)
