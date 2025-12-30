# Cypher Queries for Fetching Unique CONCEPT Names

## Basic Query - Return as List of Rows
Returns each unique concept name as a separate row:
```cypher
MATCH (c:CONCEPT)
RETURN DISTINCT c.name AS name
ORDER BY c.name ASC
```

## Return as Single List/Array
Returns all unique concept names as a single array:
```cypher
MATCH (c:CONCEPT)
WITH DISTINCT c.name AS name
ORDER BY name ASC
RETURN collect(name) AS concept_names
```

## Case-Insensitive Unique List
If you want to ensure uniqueness regardless of case:
```cypher
MATCH (c:CONCEPT)
WITH DISTINCT toLower(c.name) AS name
ORDER BY name ASC
RETURN collect(name) AS concept_names
```

## Filter Out Null/Empty Names
Excludes null or empty concept names:
```cypher
MATCH (c:CONCEPT)
WHERE c.name IS NOT NULL AND c.name <> ''
WITH DISTINCT c.name AS name
ORDER BY name ASC
RETURN collect(name) AS concept_names
```

## Count Unique Concepts
Get both the list and the count:
```cypher
MATCH (c:CONCEPT)
WHERE c.name IS NOT NULL AND c.name <> ''
WITH DISTINCT c.name AS name
ORDER BY name ASC
WITH collect(name) AS concept_names, count(*) AS total_count
RETURN concept_names, total_count
```

## Using COLLECT with DISTINCT (Alternative)
Another way to get unique names as a list:
```cypher
MATCH (c:CONCEPT)
WHERE c.name IS NOT NULL AND c.name <> ''
RETURN collect(DISTINCT c.name) AS concept_names
ORDER BY concept_names
```

Note: The last query returns an unsorted list. For sorted results, use the WITH DISTINCT ... ORDER BY ... collect() pattern.

## Verify Merged Concepts
Check if specific concepts exist in the database (useful for verifying merges):
```cypher
// Check if a specific concept exists
MATCH (c:CONCEPT)
WHERE toLower(c.name) = toLower($concept_name)
RETURN c.name AS name, count(*) AS count
```

// Check multiple concepts at once
UNWIND $concept_names AS name
MATCH (c:CONCEPT)
WHERE toLower(c.name) = toLower(name)
RETURN collect(DISTINCT c.name) AS found_concepts

// Find concepts that might have been merged (check for similar names)
MATCH (c:CONCEPT)
WHERE toLower(c.name) CONTAINS toLower($search_term)
RETURN c.name AS name
ORDER BY c.name ASC
```

