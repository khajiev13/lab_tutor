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
import re
from dotenv import load_dotenv

from langchain_neo4j import Neo4jGraph
from langchain_neo4j.graphs.graph_document import GraphDocument
from langchain_neo4j.graphs.graph_document import Node as GraphNode
from langchain_neo4j.graphs.graph_document import Relationship as GraphRelationship
from langchain_core.documents import Document

from models.neo4j_models import (
    Neo4jGraphData, Neo4jNode, Neo4jRelationship,
    TopicNodeProperties, TheoryNodeProperties, ConceptNodeProperties,
    HasTheoryRelationshipProperties, MentionsRelationshipProperties,
    Neo4jInsertionResult
)
from services.embedding import EmbeddingService

load_dotenv()


class Neo4jService:
    """Modern Neo4j service for topic-based knowledge graph operations with vector search."""
    
    def __init__(
        self,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: str = "neo4j",
        embedding_service: Optional[EmbeddingService] = None
    ):
        """
        Initialize Neo4j service with connection parameters.

        Args:
            url: Neo4j database URL (defaults to NEO4J_URI env var or bolt://localhost:7687)
            username: Database username (defaults to NEO4J_USERNAME env var or neo4j)
            password: Database password (defaults to NEO4J_PASSWORD env var or password)
            database: Database name
            embedding_service: Optional embedding service instance
        """
        # Use environment variables or defaults
        self.url = url or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.username = username or os.getenv("NEO4J_USERNAME", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self.database = database

        # Initialize embedding service
        self.embedding_service = embedding_service or EmbeddingService()

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
                # Use LangChain's native error handling
                print(f"⚠️  Insertion error: {insert_error}")
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
            # Handle multiple formats: prioritize Pydantic model format, then legacy formats
            source_id = (rel_data.get('start_node_id', '') or
                        rel_data.get('source_id', '') or
                        rel_data.get('from_node_id', ''))
            target_id = (rel_data.get('end_node_id', '') or
                        rel_data.get('target_id', '') or
                        rel_data.get('to_node_id', ''))
            rel_type = rel_data.get('relationship_type', '') or rel_data.get('type', '')
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

    def create_graph_data_from_extraction(self, extraction_result, source_file: str) -> Neo4jGraphData:
        """
        Create Pydantic-based Neo4j graph data from LangChain extraction result.

        This method handles the complete transformation from extraction results to Neo4j-ready data,
        including embedding generation and concept normalization.

        Args:
            extraction_result: CompleteExtractionResult from LangChain extraction
            source_file: Path to source DOCX file

        Returns:
            Neo4jGraphData with type-safe Pydantic models
        """
        # Extract data from LangChain result
        extraction = extraction_result.extraction
        topic_name = extraction.topic
        summary_text = extraction.summary
        keywords_data = extraction.keywords
        concepts_data = extraction.concepts

        # Get original text from extraction result
        original_text = getattr(extraction, 'original_text', '')

        # Generate unique IDs
        source_filename = Path(source_file).name
        topic_id = f"topic_{Path(source_file).stem}"
        theory_id = f"theory_{Path(source_file).stem}"

        # Generate embedding for the theory (compressed text/summary)
        theory_embedding = []
        if summary_text:
            try:
                theory_embedding = self.embedding_service.embed_text(summary_text)
            except Exception as e:
                print(f"⚠️  Failed to generate theory embedding: {e}")
                theory_embedding = []

        # Create lists for Pydantic models
        nodes = []
        relationships = []

        # 1. TOPIC Node
        if topic_name:
            topic_node = Neo4jNode(
                id=topic_id,
                label="TOPIC",
                properties=TopicNodeProperties(name=topic_name)
            )
            nodes.append(topic_node)

        # 2. THEORY Node
        theory_node = Neo4jNode(
            id=theory_id,
            label="THEORY",
            properties=TheoryNodeProperties(
                name=topic_name,
                original_text=original_text,
                compressed_text=summary_text,
                embedding=theory_embedding,
                keywords=keywords_data,
                source=source_filename
            )
        )
        nodes.append(theory_node)

        # 3. TOPIC -> THEORY relationship
        if topic_name:
            topic_theory_rel = Neo4jRelationship(
                id=f"rel_{topic_id}_to_{theory_id}",
                relationship_type="HAS_THEORY",
                start_node_id=topic_id,
                end_node_id=theory_id,
                properties=HasTheoryRelationshipProperties()
            )
            relationships.append(topic_theory_rel)

        # 4. CONCEPT Nodes (canonical approach - no duplicates)
        canonical_concepts = {}  # Track canonical concepts to avoid duplicates

        for concept in concepts_data:
            # Normalize concept name to canonical form
            canonical_name = self._normalize_concept_name(concept.name)

            # Skip if we've already processed this canonical concept
            if canonical_name in canonical_concepts:
                continue

            # Create canonical concept node
            concept_id = f"concept_{canonical_name.replace(' ', '_').replace('-', '_')}"
            concept_node = Neo4jNode(
                id=concept_id,
                label="CONCEPT",
                properties=ConceptNodeProperties(name=canonical_name)
            )
            nodes.append(concept_node)
            canonical_concepts[canonical_name] = concept_id

            # 5. THEORY -> CONCEPT relationship (MENTIONS)
            mentions_relationship = Neo4jRelationship(
                id=f"mentions_{theory_id}_to_{concept_id}",
                relationship_type="MENTIONS",
                start_node_id=theory_id,
                end_node_id=concept_id,
                properties=MentionsRelationshipProperties(
                    original_name=concept.name,
                    definition=concept.definition,
                    text_evidence=concept.text_evidence,
                    source_document=source_filename
                )
            )
            relationships.append(mentions_relationship)

        return Neo4jGraphData(nodes=nodes, relationships=relationships)

    def _normalize_concept_name(self, concept_name: str) -> str:
        """
        Normalize concept names to canonical forms for the relationship-centric approach.

        Args:
            concept_name: Raw concept name from extraction

        Returns:
            Normalized canonical concept name
        """
        if not concept_name:
            return concept_name

        # Remove common redundant suffixes and patterns
        redundant_patterns = [
            r'\s+(Strategy|Strategies)$',
            r'\s+(Model|Models)$',
            r'\s+(Framework|Frameworks)$',
            r'\s+(System|Systems)$',
            r'\s+(Architecture|Architectures)$',
            r'\s+(Algorithm|Algorithms)$',
            r'\s+(Method|Methods)$',
            r'\s+(Technique|Techniques)$',
            r'\s+(Approach|Approaches)$',
            r'\s+(Implementation|Implementations)$',
            r'\s+(Programming|Processing)$',
            r'\s+(Computing|Computation)$',
            r'\s+Crawling\s+Strategy$',  # Specific to web crawler examples
            r'\s+Analysis\s+(Framework|Model)$'
        ]

        normalized = concept_name.strip()

        for pattern in redundant_patterns:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

        # Clean up extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        # Return original if normalization resulted in empty string
        return normalized if normalized else concept_name

    def insert_graph_data(self, graph_data: Neo4jGraphData, source_file: str) -> Neo4jInsertionResult:
        """
        Insert Pydantic-based Neo4j graph data directly into the database using LangChain.

        Args:
            graph_data: Neo4jGraphData with type-safe Pydantic models
            source_file: Path to source file for error reporting

        Returns:
            Neo4jInsertionResult with insertion status and statistics
        """
        try:
            # Convert Pydantic models to dictionary format for existing method
            neo4j_dict = graph_data.to_dict()

            # Create GraphDocument using existing method
            if neo4j_dict.get('nodes'):
                graph_doc = self._create_graph_document_from_construction_plan(neo4j_dict)

                # Insert into Neo4j using LangChain
                self.graph.add_graph_documents([graph_doc])

                # Count nodes and relationships
                nodes_created = len(graph_data.nodes)
                relationships_created = len(graph_data.relationships)

                return Neo4jInsertionResult(
                    success=True,
                    nodes_created=nodes_created,
                    relationships_created=relationships_created,
                    source_file=source_file
                )
            else:
                return Neo4jInsertionResult(
                    success=False,
                    nodes_created=0,
                    relationships_created=0,
                    source_file=source_file,
                    error='No nodes to insert'
                )

        except Exception as e:
            return Neo4jInsertionResult(
                success=False,
                nodes_created=0,
                relationships_created=0,
                source_file=source_file,
                error=str(e)
            )

    def close(self):
        """Close the database connection."""
        print("🔌 Neo4j connection closed")
        # LangChain Neo4jGraph manages connections internally
