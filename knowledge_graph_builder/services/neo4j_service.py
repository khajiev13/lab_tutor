"""
Modern Neo4j Service for Topic-Based Knowledge Graph Operations

This service is designed to work with our topic-based folder structure and embedded vector data.
It handles:
1. Topic-based JSON file processing
2. Vector similarity search setup
3. Modern LangChain Neo4j integration
4. Constraint and index management
5. Graph construction from our construction plan format
"""

from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import json
import os
from dotenv import load_dotenv

from langchain_neo4j import Neo4jGraph
from langchain_neo4j.graphs.graph_document import GraphDocument
from langchain_neo4j.graphs.graph_document import Node as GraphNode
from langchain_neo4j.graphs.graph_document import Relationship as GraphRelationship
from langchain_core.documents import Document

load_dotenv()


class Neo4jService:
    """Modern Neo4j service for topic-based knowledge graph operations with vector search."""
    
    def __init__(
        self,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: str = "neo4j"
    ):
        """
        Initialize Neo4j service with connection parameters.
        
        Args:
            url: Neo4j database URL (defaults to NEO4J_URI env var or bolt://localhost:7687)
            username: Database username (defaults to NEO4J_USERNAME env var or neo4j)
            password: Database password (defaults to NEO4J_PASSWORD env var or password)
            database: Database name
        """
        # Use environment variables or defaults
        self.url = url or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.username = username or os.getenv("NEO4J_USERNAME", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self.database = database
        
        # Initialize Neo4j connection
        try:
            self.graph = Neo4jGraph(
                url=self.url,
                username=self.username,
                password=self.password,
                database=self.database
            )
            print(f"✅ Connected to Neo4j at {self.url}")
        except Exception as e:
            print(f"❌ Failed to connect to Neo4j: {e}")
            raise
    
    def clear_database(self):
        """Clear all data from the Neo4j database for fresh start."""
        try:
            self.graph.query("MATCH (n) DETACH DELETE n")
            print("🗑️  Database cleared - fresh start ready")
        except Exception as e:
            print(f"⚠️  Error clearing database: {e}")
    
    def create_constraints_and_indexes(self):
        """Create constraints and indexes optimized for our knowledge graph schema."""
        print("🔧 Setting up database constraints and indexes...")
        
        # Node constraints for uniqueness
        constraints = [
            "CREATE CONSTRAINT topic_name_unique IF NOT EXISTS FOR (t:TOPIC) REQUIRE t.name IS UNIQUE",
            "CREATE CONSTRAINT theory_id_unique IF NOT EXISTS FOR (th:THEORY) REQUIRE th.id IS UNIQUE",
            # Note: CONCEPT nodes should be shared across documents, so we use MERGE instead of unique constraint
            # "CREATE CONSTRAINT concept_name_unique IF NOT EXISTS FOR (c:CONCEPT) REQUIRE c.name IS UNIQUE"
        ]
        
        # Regular indexes for performance
        indexes = [
            "CREATE INDEX topic_name_idx IF NOT EXISTS FOR (t:TOPIC) ON (t.name)",
            "CREATE INDEX theory_source_idx IF NOT EXISTS FOR (th:THEORY) ON (th.source)",
            "CREATE INDEX concept_definition_idx IF NOT EXISTS FOR (c:CONCEPT) ON (c.definition)"
        ]
        
        # Vector indexes for similarity search (Neo4j 5.0+)
        vector_indexes = [
            """CREATE VECTOR INDEX theory_embedding_idx IF NOT EXISTS
               FOR (th:THEORY) ON (th.embedding)
               OPTIONS {indexConfig: {
                 `vector.dimensions`: 1536,
                 `vector.similarity_function`: 'cosine'
               }}""",
            """CREATE VECTOR INDEX concept_embedding_idx IF NOT EXISTS
               FOR (c:CONCEPT) ON (c.embedding)
               OPTIONS {indexConfig: {
                 `vector.dimensions`: 1536,
                 `vector.similarity_function`: 'cosine'
               }}"""
        ]
        
        # Execute constraints
        for constraint in constraints:
            try:
                self.graph.query(constraint)
                constraint_name = constraint.split("FOR")[1].split("REQUIRE")[0].strip()
                print(f"  ✅ Constraint: {constraint_name}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"  ℹ️  Constraint already exists: {constraint.split()[2]}")
                else:
                    print(f"  ⚠️  Constraint error: {e}")
        
        # Execute regular indexes
        for index in indexes:
            try:
                self.graph.query(index)
                index_name = index.split()[2]
                print(f"  ✅ Index: {index_name}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"  ℹ️  Index already exists: {index.split()[2]}")
                else:
                    print(f"  ⚠️  Index error: {e}")
        
        # Execute vector indexes
        for vector_index in vector_indexes:
            try:
                self.graph.query(vector_index)
                index_name = vector_index.split()[3]
                print(f"  ✅ Vector index: {index_name}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"  ℹ️  Vector index already exists: {vector_index.split()[3]}")
                else:
                    print(f"  ⚠️  Vector index error (may require Neo4j 5.0+): {e}")
        
        print("🎯 Database setup complete!")
    
    def process_topic_json_file(self, json_file_path: Union[str, Path]) -> bool:
        """
        Process a single Neo4j-ready JSON file from a topic folder.
        Handles concept deduplication and constraint conflicts gracefully.

        Args:
            json_file_path: Path to the Neo4j-ready JSON file

        Returns:
            True if successful, False otherwise
        """
        try:
            json_path = Path(json_file_path)
            print(f"📄 Processing: {json_path.name}")

            # Load JSON data
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Validate data structure
            if 'nodes' not in data or 'relationships' not in data:
                print(f"❌ Invalid JSON structure in {json_path.name}")
                return False

            # Try to process with concept deduplication
            try:
                # Create graph document from our construction plan format
                graph_doc = self._create_graph_document_from_construction_plan(data)

                # Insert into Neo4j
                self.graph.add_graph_documents([graph_doc])

                print(f"✅ Successfully processed: {json_path.name}")
                print(f"   • Nodes: {len(data['nodes'])}")
                print(f"   • Relationships: {len(data['relationships'])}")

                return True

            except Exception as insert_error:
                # If we still get constraint errors, try manual insertion with MERGE
                if "IndexEntryConflictException" in str(insert_error) or "already exists" in str(insert_error):
                    print(f"⚠️  Constraint conflict detected, trying manual MERGE approach...")
                    return self._manual_merge_insertion(data, json_path.name)
                else:
                    raise insert_error

        except Exception as e:
            print(f"❌ Error processing {json_file_path}: {e}")
            return False

    def _create_graph_document_from_construction_plan(self, data: Dict[str, Any]) -> GraphDocument:
        """
        Create a GraphDocument from our construction plan format.
        Handles concept deduplication by using concept names as IDs for CONCEPT nodes.

        Args:
            data: Dictionary with 'nodes' and 'relationships' keys

        Returns:
            GraphDocument ready for insertion
        """
        # Create nodes
        nodes = []
        node_map = {}  # Map node IDs to Node objects
        concept_name_to_node = {}  # Track concepts by name to handle duplicates

        for node_data in data['nodes']:
            # Extract node properties (handle both 'type' and 'label' formats)
            node_id = node_data.get('id', '')
            node_type = node_data.get('type', '') or node_data.get('label', '')
            properties = node_data.get('properties', {})

            # Special handling for CONCEPT nodes with relationship-centric approach
            if node_type == 'CONCEPT':
                concept_name = properties.get('name', '')
                if concept_name in concept_name_to_node:
                    # Concept already exists, just map this node_id to the existing node
                    # Contextual definitions will be stored in MENTIONS relationships
                    existing_node = concept_name_to_node[concept_name]
                    node_map[node_id] = existing_node
                    continue
                else:
                    # New concept, use concept name as the ID for consistency
                    # Remove any manual 'id' from properties to avoid redundancy
                    clean_properties = {k: v for k, v in properties.items() if k != 'id'}

                    node = GraphNode(
                        id=concept_name,  # Use name as ID for concepts
                        type=node_type,
                        properties=clean_properties
                    )
                    nodes.append(node)
                    # Map both the original node_id AND the concept name to this node
                    node_map[node_id] = node
                    node_map[concept_name] = node  # Also map concept name for relationships
                    concept_name_to_node[concept_name] = node
            else:
                # Regular node (TOPIC, THEORY)
                node = GraphNode(
                    id=node_id,
                    type=node_type,
                    properties=properties
                )
                nodes.append(node)
                node_map[node_id] = node

        # Create relationships
        relationships = []
        for rel_data in data['relationships']:
            # Handle both formats: 'source_id'/'target_id' and 'from_node_id'/'to_node_id'
            source_id = rel_data.get('source_id', '') or rel_data.get('from_node_id', '')
            target_id = rel_data.get('target_id', '') or rel_data.get('to_node_id', '')
            rel_type = rel_data.get('type', '') or rel_data.get('relationship_type', '')
            rel_properties = rel_data.get('properties', {})

            # Find source and target nodes
            source_node = node_map.get(source_id)
            target_node = node_map.get(target_id)

            if source_node and target_node:
                relationship = GraphRelationship(
                    source=source_node,
                    target=target_node,
                    type=rel_type,
                    properties=rel_properties
                )
                relationships.append(relationship)
            else:
                print(f"⚠️  Skipping relationship: source={source_id}, target={target_id} (nodes not found)")

        # Create source document
        source_doc = Document(
            page_content="Knowledge graph from topic-based processing",
            metadata={"source": "topic_based_pipeline"}
        )

        return GraphDocument(
            nodes=nodes,
            relationships=relationships,
            source=source_doc
        )

    def _manual_merge_insertion(self, data: Dict[str, Any], filename: str) -> bool:
        """
        Manually insert nodes and relationships using MERGE to handle duplicates.

        Args:
            data: Dictionary with 'nodes' and 'relationships' keys
            filename: Name of the file being processed (for logging)

        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"   🔄 Using manual MERGE insertion for {filename}")

            # Insert nodes using MERGE
            nodes_created = 0
            for node_data in data['nodes']:
                node_type = node_data.get('type', '') or node_data.get('label', '')
                properties = node_data.get('properties', {})

                if node_type == 'CONCEPT':
                    # For canonical concepts, only store name (no definition or embedding)
                    concept_name = properties.get('name', '')

                    cypher = """
                    MERGE (c:CONCEPT {name: $name})
                    ON CREATE SET
                        c.created_at = datetime(),
                        c.total_mentions = 1
                    ON MATCH SET
                        c.total_mentions = c.total_mentions + 1,
                        c.last_updated = datetime()
                    RETURN c
                    """

                    result = self.graph.query(cypher, {
                        'name': concept_name
                    })

                elif node_type == 'TOPIC':
                    # For topics, merge by name
                    topic_name = properties.get('name', '')

                    cypher = """
                    MERGE (t:TOPIC {name: $name})
                    RETURN t
                    """

                    result = self.graph.query(cypher, {'name': topic_name})

                elif node_type == 'THEORY':
                    # For theories, merge by id
                    theory_id = properties.get('id', '')
                    original_text = properties.get('original_text', '')
                    compressed_text = properties.get('compressed_text', '')
                    source = properties.get('source', '')
                    keywords = properties.get('keywords', [])
                    embedding = properties.get('embedding', [])

                    cypher = """
                    MERGE (th:THEORY {id: $id})
                    ON CREATE SET
                        th.original_text = $original_text,
                        th.compressed_text = $compressed_text,
                        th.source = $source,
                        th.keywords = $keywords,
                        th.embedding = $embedding
                    RETURN th
                    """

                    result = self.graph.query(cypher, {
                        'id': theory_id,
                        'original_text': original_text,
                        'compressed_text': compressed_text,
                        'source': source,
                        'keywords': keywords,
                        'embedding': embedding
                    })

                if result:
                    nodes_created += 1

            # Insert relationships using MERGE
            relationships_created = 0
            for rel_data in data['relationships']:
                source_id = rel_data.get('source_id', '') or rel_data.get('from_node_id', '')
                target_id = rel_data.get('target_id', '') or rel_data.get('to_node_id', '')
                rel_type = rel_data.get('type', '') or rel_data.get('relationship_type', '')

                # Determine node types for matching
                source_label = rel_data.get('from_node_label', 'TOPIC')  # Default assumption
                target_label = rel_data.get('to_node_label', 'CONCEPT')  # Default assumption

                if rel_type == 'HAS':
                    # TOPIC -[HAS]-> THEORY
                    cypher = """
                    MATCH (t:TOPIC {name: $source_name})
                    MATCH (th:THEORY {id: $target_id})
                    MERGE (t)-[r:HAS]->(th)
                    RETURN r
                    """
                    result = self.graph.query(cypher, {
                        'source_name': source_id.replace('topic_', ''),
                        'target_id': target_id
                    })

                elif rel_type == 'MENTIONS':
                    # THEORY -[MENTIONS]-> CONCEPT with simplified relationship properties
                    rel_properties = rel_data.get('properties', {})

                    cypher = """
                    MATCH (th:THEORY {id: $source_id})
                    MATCH (c:CONCEPT {name: $target_name})
                    MERGE (th)-[r:MENTIONS]->(c)
                    SET r.local_definition = $local_definition,
                        r.source_file = $source_file
                    RETURN r
                    """
                    # Extract concept name from target_id if it starts with 'concept_'
                    target_name = target_id
                    if target_id.startswith('concept_'):
                        # Try to find the actual concept name from the nodes data
                        for node in data['nodes']:
                            if node.get('id') == target_id and node.get('type') == 'CONCEPT':
                                target_name = node.get('properties', {}).get('name', target_id)
                                break

                    result = self.graph.query(cypher, {
                        'source_id': source_id,
                        'target_name': target_name,
                        'local_definition': rel_properties.get('local_definition', ''),
                        'source_file': rel_properties.get('source_file', '')
                    })

                if result:
                    relationships_created += 1

            print(f"   ✅ Manual insertion completed: {nodes_created} nodes, {relationships_created} relationships")
            return True

        except Exception as e:
            print(f"   ❌ Manual insertion failed: {e}")
            return False

    def process_topic_folder(self, topic_folder_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Process all Neo4j-ready JSON files in a topic folder.

        Args:
            topic_folder_path: Path to the topic folder

        Returns:
            Processing results summary
        """
        topic_path = Path(topic_folder_path)
        neo4j_ready_dir = topic_path / "neo4j_ready"

        results = {
            'topic_folder': str(topic_path.name),
            'processed_files': [],
            'failed_files': [],
            'total_nodes': 0,
            'total_relationships': 0
        }

        if not neo4j_ready_dir.exists():
            print(f"❌ Neo4j ready directory not found: {neo4j_ready_dir}")
            return results

        # Find all JSON files in neo4j_ready directory
        json_files = list(neo4j_ready_dir.glob("*.json"))

        if not json_files:
            print(f"⚠️  No JSON files found in {neo4j_ready_dir}")
            return results

        print(f"📁 Processing topic folder: {topic_path.name}")
        print(f"   Found {len(json_files)} JSON files")

        # Process each JSON file
        for json_file in json_files:
            if self.process_topic_json_file(json_file):
                results['processed_files'].append(str(json_file.name))

                # Count nodes and relationships
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    results['total_nodes'] += len(data.get('nodes', []))
                    results['total_relationships'] += len(data.get('relationships', []))
                except Exception as e:
                    print(f"⚠️  Error counting data in {json_file.name}: {e}")
            else:
                results['failed_files'].append(str(json_file.name))

        return results

    def ingest_all_topics(self, base_output_dir: Union[str, Path]) -> Dict[str, Any]:
        """
        Ingest all topic folders from the base output directory.

        Args:
            base_output_dir: Base directory containing topic folders

        Returns:
            Complete ingestion results
        """
        base_path = Path(base_output_dir)

        if not base_path.exists():
            print(f"❌ Base output directory not found: {base_path}")
            return {'error': 'Base directory not found'}

        # Find all topic folders (directories that contain neo4j_ready subdirectories)
        topic_folders = []
        for item in base_path.iterdir():
            if item.is_dir() and (item / "neo4j_ready").exists():
                topic_folders.append(item)

        if not topic_folders:
            print(f"⚠️  No topic folders found in {base_path}")
            return {'error': 'No topic folders found'}

        print(f"🚀 Starting Neo4j ingestion for {len(topic_folders)} topics...")

        # Clear database and set up constraints
        self.clear_database()
        self.create_constraints_and_indexes()

        # Process each topic folder
        ingestion_results = {
            'base_directory': str(base_path),
            'topics_processed': [],
            'topics_failed': [],
            'total_files_processed': 0,
            'total_files_failed': 0,
            'total_nodes': 0,
            'total_relationships': 0
        }

        for topic_folder in topic_folders:
            print(f"\n📋 Processing topic: {topic_folder.name}")

            topic_result = self.process_topic_folder(topic_folder)

            if topic_result['processed_files']:
                ingestion_results['topics_processed'].append(topic_result)
                ingestion_results['total_files_processed'] += len(topic_result['processed_files'])
                ingestion_results['total_nodes'] += topic_result['total_nodes']
                ingestion_results['total_relationships'] += topic_result['total_relationships']

            if topic_result['failed_files']:
                ingestion_results['topics_failed'].append(topic_result)
                ingestion_results['total_files_failed'] += len(topic_result['failed_files'])

        # Get final database statistics
        db_stats = self.get_database_stats()
        ingestion_results['database_stats'] = db_stats

        return ingestion_results

    def get_database_stats(self) -> Dict[str, int]:
        """
        Get comprehensive statistics about the Neo4j database.

        Returns:
            Dictionary with counts of different node types and relationships
        """
        stats = {}

        try:
            # Count nodes by type
            node_types = ["TOPIC", "THEORY", "CONCEPT"]
            for node_type in node_types:
                result = self.graph.query(f"MATCH (n:{node_type}) RETURN count(n) as count")
                stats[f"{node_type} nodes"] = result[0]['count'] if result else 0

            # Count relationships by type
            rel_types = ["HAS", "MENTIONS"]
            for rel_type in rel_types:
                result = self.graph.query(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as count")
                stats[f"{rel_type} relationships"] = result[0]['count'] if result else 0

            # Total counts
            total_nodes_result = self.graph.query("MATCH (n) RETURN count(n) as count")
            stats["Total nodes"] = total_nodes_result[0]['count'] if total_nodes_result else 0

            total_rels_result = self.graph.query("MATCH ()-[r]->() RETURN count(r) as count")
            stats["Total relationships"] = total_rels_result[0]['count'] if total_rels_result else 0

        except Exception as e:
            print(f"⚠️  Error getting database stats: {e}")
            stats["error"] = str(e)

        return stats

    def vector_similarity_search(
        self,
        query_text: str,
        node_type: str = "CONCEPT",
        limit: int = 5,
        similarity_threshold: float = 0.8
    ) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search on embedded nodes.

        Args:
            query_text: Text to search for similar content
            node_type: Type of nodes to search (CONCEPT or THEORY)
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score

        Returns:
            List of similar nodes with similarity scores
        """
        # This would require embedding the query_text first
        # For now, return a placeholder implementation
        print(f"🔍 Vector similarity search for '{query_text}' in {node_type} nodes")
        print(f"   (Vector search requires embedding service integration)")

        # Fallback to text-based search for now
        if node_type == "CONCEPT":
            cypher = """
            MATCH (c:CONCEPT)
            WHERE toLower(c.definition) CONTAINS toLower($query_text)
               OR toLower(c.name) CONTAINS toLower($query_text)
            RETURN c.name as name, c.definition as definition
            LIMIT $limit
            """
        else:  # THEORY
            cypher = """
            MATCH (t:THEORY)
            WHERE toLower(t.compressed_text) CONTAINS toLower($query_text)
               OR toLower(t.original_text) CONTAINS toLower($query_text)
            RETURN t.source as source, t.compressed_text as summary
            LIMIT $limit
            """

        try:
            results = self.graph.query(cypher, {"query_text": query_text, "limit": limit})
            return results
        except Exception as e:
            print(f"❌ Error in similarity search: {e}")
            return []

    def query(self, cypher_query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a custom Cypher query.

        Args:
            cypher_query: Cypher query string
            params: Query parameters

        Returns:
            Query results
        """
        try:
            return self.graph.query(cypher_query, params or {})
        except Exception as e:
            print(f"❌ Query error: {e}")
            return []

    def close(self):
        """Close the database connection."""
        print("🔌 Neo4j connection closed")
        # LangChain Neo4jGraph manages connections internally
