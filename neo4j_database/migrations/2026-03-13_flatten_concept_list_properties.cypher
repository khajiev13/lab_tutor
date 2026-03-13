// Fix CONCEPT nodes where name/description became lists due to
// apoc.refactor.mergeNodes using `.*: "overwrite"` strategy.
// Root cause fixed in concept_normalization/repository.py (overwrite -> discard).
// Affected 30 nodes: 8 conflicting (head(name) already existed), 22 non-conflicting.

// Step 1: Merge conflicting broken nodes into their existing counterpart.
// When head(broken.name) matches an existing CONCEPT node, absorb the broken
// node's aliases, description, embedding, and relationships into the existing one.
MATCH (broken:CONCEPT)
WHERE apoc.meta.cypher.type(broken.name) = 'LIST OF STRING'
WITH broken, head(broken.name) AS target_name, tail(broken.name) AS extra_names
MATCH (existing:CONCEPT {name: target_name})
WHERE id(existing) <> id(broken)
SET existing.aliases = apoc.coll.toSet(
  coalesce(existing.aliases, []) + coalesce(broken.aliases, []) + extra_names
)
SET existing.description = CASE
  WHEN existing.description IS NOT NULL THEN existing.description
  WHEN broken.description IS NOT NULL AND apoc.meta.cypher.type(broken.description) = 'LIST OF STRING' THEN head(broken.description)
  ELSE broken.description
END
SET existing.embedding = CASE
  WHEN existing.embedding IS NOT NULL THEN existing.embedding
  ELSE broken.embedding
END
WITH existing, broken
CALL apoc.refactor.mergeNodes(
  [existing, broken],
  { properties: "discard", mergeRels: true }
)
YIELD node
RETURN count(node);

// Step 2: Flatten the remaining non-conflicting nodes (no duplicate name exists).
MATCH (c:CONCEPT)
WHERE apoc.meta.cypher.type(c.name) = 'LIST OF STRING'
SET c.aliases = apoc.coll.toSet(coalesce(c.aliases, []) + tail(c.name)),
    c.name = head(c.name);

// Step 3: Flatten any list-typed descriptions.
MATCH (c:CONCEPT)
WHERE c.description IS NOT NULL
  AND apoc.meta.cypher.type(c.description) = 'LIST OF STRING'
SET c.description = head(c.description);
