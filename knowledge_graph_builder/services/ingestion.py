from pathlib import Path
from typing import List, Dict, Any, Optional
import json

from utils.doc_utils import (
    load_json_file,
    find_original_docx,
    load_and_preprocess_docx,
    ensure_embeddings_exist,
    discover_json_files,
    load_single_docx_document
)
import langextract as lx
import re


class IngestionService:
    """
    Handles the complete knowledge graph ingestion pipeline.
    """
    
    def __init__(self, neo4j_service=None, embedding_service=None, extraction_service=None):
        """
        Initialize with optional services. Services will be created as needed.

        Args:
            neo4j_service: Optional Neo4j service instance
            embedding_service: Optional embedding service instance
            extraction_service: Optional extraction service instance
        """
        self.neo4j_service = neo4j_service
        self.embedding_service = embedding_service
        self.extraction_service = extraction_service
    
    def create_topic_node_data(self, topic_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create TOPIC node data dictionary."""
        return {
            'id': f"topic_{topic_data['name']}",
            'type': "TOPIC",
            'properties': {"name": topic_data["name"]}
        }
    
    def create_theory_node_data(self, topic_data: Dict[str, Any], original_text: str = "") -> Dict[str, Any]:
        """Create THEORY node data dictionary with enhanced fields."""
        theory_id = f"theory_{topic_data['name']}"

        # Use topic summary as compressed text
        compressed_text = topic_data.get('summary', '')

        # Get embedding from topic data (generated from summary)
        embedding = topic_data.get('embedding', [])

        # Extract keywords (new field)
        keywords = topic_data.get('keywords', [])

        # Extract source file path (new field)
        source = topic_data.get('source', '')

        return {
            'id': theory_id,
            'type': "THEORY",
            'properties': {
                "original_text": original_text,
                "compressed_text": compressed_text,
                "embedding": embedding,
                "keywords": keywords,
                "source": source
            }
        }
    
    def create_concept_node_data(self, concept_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create CONCEPT node data dictionary."""
        return {
            'id': f"concept_{concept_data['name']}",
            'type': "CONCEPT",
            'properties': {
                "name": concept_data["name"],
                "definition": concept_data.get("definition", ""),
                "embedding": concept_data.get("embedding", [])
            }
        }
    
    def build_knowledge_graph_from_json(self, data: Dict[str, Any], original_text: str = "") -> Dict[str, Any]:
        """
        Build knowledge graph data from JSON data.
        
        Args:
            data: JSON data with nodes and relationships
            original_text: Original DOCX content for THEORY nodes
            
        Returns:
            Dictionary with 'nodes' and 'relationships' lists ready for Neo4j service
        """
        nodes_data = []
        relationships_data = []
        
        # Create node mappings for relationship building
        node_by_id = {}
        
        # First pass: Create all nodes
        for node_data in data.get('nodes', []):
            node_type = node_data.get('type')
            node_name = node_data.get('name')
            
            if node_type == 'Topic':
                # Create TOPIC and THEORY nodes
                topic_node_data = self.create_topic_node_data(node_data)
                theory_node_data = self.create_theory_node_data(node_data, original_text)
                
                nodes_data.extend([topic_node_data, theory_node_data])
                
                # Map for relationship creation
                node_by_id[node_data.get('id')] = theory_node_data['id']  # Relationships point to THEORY
                
                # Create HAS relationship: TOPIC -> THEORY
                has_rel_data = {
                    'source_id': topic_node_data['id'],
                    'target_id': theory_node_data['id'],
                    'type': "HAS"
                }
                relationships_data.append(has_rel_data)
                
            elif node_type == 'Concept':
                concept_node_data = self.create_concept_node_data(node_data)
                nodes_data.append(concept_node_data)
                
                # Map for relationship creation
                node_by_id[node_data.get('id')] = concept_node_data['id']
        
        # Second pass: Create relationships from JSON data
        for relationship_data in data.get('relationships', []):
            source_id = relationship_data.get('source')
            target_id = relationship_data.get('target')
            rel_type = relationship_data.get('type', 'RELATED_TO')
            
            source_node_id = node_by_id.get(source_id)
            target_node_id = node_by_id.get(target_id)
            
            if source_node_id and target_node_id:
                # Map relationship types appropriately
                if rel_type in ['contains', 'includes', 'has']:
                    rel_type = 'MENTIONS'  # THEORY mentions CONCEPT
                
                rel_data = {
                    'source_id': source_node_id,
                    'target_id': target_node_id,
                    'type': rel_type
                }
                relationships_data.append(rel_data)
        
        return {
            'nodes': nodes_data,
            'relationships': relationships_data
        }
    
    def process_single_json_file(self, json_path: str, docx_directory: str) -> bool:
        """
        Process a single JSON file and insert into knowledge graph.
        
        Args:
            json_path: Path to JSON file with extracted data
            docx_directory: Directory containing original DOCX files
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Load and process JSON data
            data = load_json_file(json_path)
            data = ensure_embeddings_exist(data, self.embedding_service)
            
            # Get original text - first try from metadata, then from DOCX file
            original_text = ""
            json_filename = Path(json_path).name

            # Check if original text is already in the JSON metadata
            if 'metadata' in data and 'original_text' in data['metadata']:
                original_text = data['metadata']['original_text']
                print(f"📄 Using original text from JSON metadata")
            else:
                # Fallback: Find and load original DOCX content
                docx_path = find_original_docx(json_filename, docx_directory)
                if docx_path:
                    original_text = load_and_preprocess_docx(docx_path, self.extraction_service)
                    print(f"📄 Loaded original text from DOCX: {docx_path}")
                else:
                    print(f"⚠️  No original text found for: {json_filename}")
            
            # Build knowledge graph data
            graph_data = self.build_knowledge_graph_from_json(data, original_text)
            
            # Create GraphDocument using Neo4j service
            if graph_data['nodes']:
                graph_doc = self.neo4j_service._create_graph_document_from_construction_plan(graph_data)

                # Insert into Neo4j
                self.neo4j_service.graph.add_graph_documents([graph_doc])
                print(f"✅ Successfully ingested: {json_filename}")
                return True
            else:
                print(f"⚠️  No graph data created for: {json_filename}")
                return False
                
        except Exception as e:
            print(f"❌ Error processing {json_path}: {e}")
            return False
    
    def ingest_all_json_files(self, json_directory: str, docx_directory: str) -> Dict[str, int]:
        """
        Ingest all JSON files from the specified directory.
        
        Args:
            json_directory: Directory containing JSON files
            docx_directory: Directory containing original DOCX files
            
        Returns:
            Dictionary with ingestion statistics
        """
        print("🚀 Starting knowledge graph ingestion process...")
        
        # Create constraints first
        self.neo4j_service.create_constraints_and_indexes()

        # Discover JSON files
        json_files = discover_json_files(json_directory)

        if not json_files:
            print("❌ No JSON files found!")
            return {"processed": 0, "successful": 0, "failed": 0}

        print(f"📚 Found {len(json_files)} JSON files to process")

        # Process each file
        successful = 0
        failed = 0

        for json_file in json_files:
            if self.process_single_json_file(str(json_file), docx_directory):
                successful += 1
            else:
                failed += 1

        # Print statistics
        stats = {
            "processed": len(json_files),
            "successful": successful,
            "failed": failed
        }

        print(f"\n📊 Ingestion completed:")
        print(f"   • Files processed: {stats['processed']}")
        print(f"   • Successful: {stats['successful']}")
        print(f"   • Failed: {stats['failed']}")

        # Get database statistics
        db_stats = self.neo4j_service.get_database_stats()
        print(f"\n📈 Database statistics:")
        for stat_name, count in db_stats.items():
            print(f"   • {stat_name}: {count}")

        return stats

    def ingest_topics_to_neo4j(self, base_output_dir: str = "output") -> Dict[str, Any]:
        """
        Ingest all topic folders into Neo4j database using the new topic-based structure.

        Args:
            base_output_dir: Base directory containing topic folders

        Returns:
            Complete ingestion results and statistics
        """
        # Initialize Neo4j service if not already done
        if not self.neo4j_service:
            from services.neo4j_service import Neo4jService
            self.neo4j_service = Neo4jService()

        print("🚀 Starting topic-based Neo4j ingestion...")

        # Use the new Neo4j service to ingest all topics
        results = self.neo4j_service.ingest_all_topics(base_output_dir)

        # Print comprehensive summary
        if 'error' not in results:
            print(f"\n🎉 Neo4j Ingestion Complete!")
            print(f"📊 Summary:")
            print(f"   • Topics processed: {len(results['topics_processed'])}")
            print(f"   • Topics failed: {len(results['topics_failed'])}")
            print(f"   • Files processed: {results['total_files_processed']}")
            print(f"   • Files failed: {results['total_files_failed']}")
            print(f"   • Total nodes: {results['total_nodes']}")
            print(f"   • Total relationships: {results['total_relationships']}")

            # Display database statistics
            if 'database_stats' in results:
                print(f"\n📈 Database Statistics:")
                for stat_name, count in results['database_stats'].items():
                    if stat_name != 'error':
                        print(f"   • {stat_name}: {count}")

            # List processed topics
            if results['topics_processed']:
                print(f"\n✅ Successfully processed topics:")
                for topic_result in results['topics_processed']:
                    topic_name = topic_result['topic_folder']
                    file_count = len(topic_result['processed_files'])
                    node_count = topic_result['total_nodes']
                    rel_count = topic_result['total_relationships']
                    print(f"   • {topic_name}: {file_count} files, {node_count} nodes, {rel_count} relationships")
        else:
            print(f"❌ Ingestion failed: {results['error']}")

        return results

    def _sanitize_topic_name(self, topic_name: str, max_length: int = 100) -> str:
        """
        Sanitize topic name for use as a folder name.

        Args:
            topic_name: Raw topic name from LangExtract
            max_length: Maximum length for folder name

        Returns:
            Sanitized folder name safe for filesystem use
        """
        if not topic_name or not topic_name.strip():
            return "Unknown_Topic"

        # Remove or replace problematic characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', topic_name.strip())

        # Replace multiple spaces/underscores with single underscore
        sanitized = re.sub(r'[\s_]+', '_', sanitized)

        # Remove leading/trailing underscores and dots
        sanitized = sanitized.strip('_.')

        # Limit length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length].rstrip('_.')

        # Ensure it's not empty after sanitization
        if not sanitized:
            return "Unknown_Topic"

        return sanitized

    def _extract_topic_from_langextract_result(self, langextract_result) -> str:
        """
        Extract topic name from LangExtract result.

        Args:
            langextract_result: LangExtract AnnotatedDocument result

        Returns:
            Topic name string, or empty string if not found
        """
        extractions = []
        if hasattr(langextract_result, 'extractions'):
            extractions = langextract_result.extractions
        elif isinstance(langextract_result, list) and len(langextract_result) > 0:
            extractions = langextract_result[0].extractions if hasattr(langextract_result[0], 'extractions') else []

        # Find TOPIC extraction
        for extraction in extractions:
            extraction_class = getattr(extraction, 'extraction_class', '')
            if extraction_class == 'TOPIC':
                return getattr(extraction, 'extraction_text', '')

        return ""

    def process_document_with_langextract(self, docx_path: str, output_dir: str = "output") -> Dict[str, Any]:
        """
        Process a single DOCX document with structured three-folder output for Neo4j ingestion.

        Creates organized outputs in three folders:
        1. langextract_outputs/ - JSONL files from LangExtract
        2. visualizations/ - HTML visualization files
        3. neo4j_ready/ - JSON files formatted for Neo4j database ingestion

        Args:
            docx_path: Path to the DOCX file
            output_dir: Base directory to create structured folders

        Returns:
            Dictionary with processing results and file paths
        """
        try:
            print(f"📄 Loading document: {docx_path}")

            # Load document
            documents = load_single_docx_document(docx_path)
            if not documents:
                return {
                    'success': False,
                    'error': 'No content found in document',
                    'source_file': docx_path
                }

            # Initialize extraction service if not provided
            if not self.extraction_service:
                from services.extraction import ExtractionService
                self.extraction_service = ExtractionService(documents=documents)
            else:
                # Update documents in existing service
                self.extraction_service.documents = documents

            # Perform LangExtract extraction
            print(f"🔄 Extracting with LangExtract...")
            langextract_result = self.extraction_service.compress_and_extract_concepts(
                source_file_path=docx_path
            )

            # Extract topic name from LangExtract result
            topic_name = self._extract_topic_from_langextract_result(langextract_result)
            if not topic_name:
                # Fallback to document filename if no topic found
                topic_name = Path(docx_path).stem
                print(f"⚠️  No TOPIC found in extraction, using filename: {topic_name}")
            else:
                print(f"📋 Extracted topic: {topic_name}")

            # Sanitize topic name for folder creation
            sanitized_topic = self._sanitize_topic_name(topic_name)
            print(f"📁 Using folder name: {sanitized_topic}")

            # Create topic-based folder structure
            base_output_path = Path(output_dir)
            topic_folder = base_output_path / sanitized_topic
            langextract_dir = topic_folder / "langextract_outputs"
            visualizations_dir = topic_folder / "visualizations"
            neo4j_dir = topic_folder / "neo4j_ready"

            # Create all directories
            for dir_path in [langextract_dir, visualizations_dir, neo4j_dir]:
                dir_path.mkdir(parents=True, exist_ok=True)

            base_filename = Path(docx_path).stem
            saved_files = {}

            # 1. Save as JSONL for LangExtract in langextract_outputs/
            try:
                jsonl_path = langextract_dir / f"{base_filename}_langextract.jsonl"

                # Handle both single AnnotatedDocument and list cases
                documents_to_save = []
                if isinstance(langextract_result, list):
                    documents_to_save = langextract_result
                elif hasattr(langextract_result, 'text'):  # Single AnnotatedDocument
                    documents_to_save = [langextract_result]

                if documents_to_save:
                    lx.io.save_annotated_documents(
                        documents_to_save,
                        output_dir=str(langextract_dir),
                        output_name=f"{base_filename}_langextract.jsonl",
                        show_progress=False
                    )
                    saved_files['langextract_jsonl'] = str(jsonl_path)
                    print(f"✅ LangExtract JSONL saved: {jsonl_path}")
                else:
                    print(f"⚠️  No documents to save as JSONL")

            except Exception as jsonl_error:
                print(f"⚠️  Failed to save JSONL: {jsonl_error}")

            # 2. Generate HTML visualization in visualizations/
            if 'langextract_jsonl' in saved_files:
                try:
                    html_path = visualizations_dir / f"{base_filename}_visualization.html"

                    # Generate visualization using LangExtract
                    html_content = lx.visualize(
                        saved_files['langextract_jsonl'],
                        animation_speed=1.0,
                        show_legend=True
                    )

                    # Save HTML content
                    with open(html_path, 'w', encoding='utf-8') as f:
                        if hasattr(html_content, 'data'):
                            f.write(html_content.data)  # For Jupyter/Colab environments
                        elif isinstance(html_content, str):
                            f.write(html_content)
                        else:
                            f.write(str(html_content))

                    saved_files['visualization_html'] = str(html_path)
                    print(f"✅ Visualization saved: {html_path}")

                except Exception as viz_error:
                    print(f"⚠️  Failed to generate visualization: {viz_error}")

            # 3. Transform to Neo4j-ready JSON format in neo4j_ready/
            try:
                neo4j_json = self._transform_langextract_to_neo4j_format(
                    langextract_result=langextract_result,
                    source_file=docx_path,
                    original_text=documents[0].page_content if documents else ""
                )

                neo4j_path = neo4j_dir / f"{base_filename}_neo4j.json"
                with open(neo4j_path, 'w', encoding='utf-8') as f:
                    json.dump(neo4j_json, f, indent=2, ensure_ascii=False)

                saved_files['neo4j_json'] = str(neo4j_path)
                print(f"✅ Neo4j-ready JSON saved: {neo4j_path}")

            except Exception as neo4j_error:
                print(f"⚠️  Failed to create Neo4j JSON: {neo4j_error}")

            return {
                'success': True,
                'source_file': docx_path,
                'base_filename': base_filename,
                'topic_name': topic_name,
                'sanitized_topic': sanitized_topic,
                'topic_folder': str(topic_folder),
                'saved_files': saved_files,
                'langextract_result': langextract_result
            }

        except Exception as e:
            print(f"❌ Error processing document: {e}")
            return {
                'success': False,
                'source_file': docx_path,
                'error': str(e)
            }

    def _transform_langextract_to_neo4j_format(self, langextract_result, source_file: str, original_text: str) -> Dict[str, Any]:
        """
        Transform LangExtract output into Neo4j-compatible JSON format.

        Args:
            langextract_result: LangExtract AnnotatedDocument result
            source_file: Path to source DOCX file
            original_text: Original preprocessed text from document

        Returns:
            Dictionary in Neo4j construction plan format
        """
        # Extract data from LangExtract result
        extractions = []
        if hasattr(langextract_result, 'extractions'):
            extractions = langextract_result.extractions
        elif isinstance(langextract_result, list) and len(langextract_result) > 0:
            extractions = langextract_result[0].extractions if hasattr(langextract_result[0], 'extractions') else []

        # Initialize extraction data containers
        topic_data = None
        summary_data = None
        keywords_data = []
        concepts_data = []

        # Parse extractions by type
        for extraction in extractions:
            extraction_class = getattr(extraction, 'extraction_class', '')
            extraction_text = getattr(extraction, 'extraction_text', '')

            if extraction_class == 'TOPIC':
                topic_data = extraction_text
            elif extraction_class == 'SUMMARY':
                summary_data = extraction_text
            elif extraction_class == 'KEYWORDS':
                # Split keywords by comma and clean
                keywords_data = [kw.strip() for kw in extraction_text.split(',') if kw.strip()]
            elif extraction_class == 'CONCEPT':
                concept_name = extraction_text
                concept_definition = ""

                # Extract definition from attributes if available
                if hasattr(extraction, 'attributes') and extraction.attributes:
                    concept_definition = extraction.attributes.get('definition', '')

                concepts_data.append({
                    'name': concept_name,
                    'definition': concept_definition
                })

        # Generate unique IDs
        source_filename = Path(source_file).name
        topic_id = f"topic_{Path(source_file).stem}"
        theory_id = f"theory_{Path(source_file).stem}"

        # Initialize embedding service if needed
        if not self.embedding_service:
            from services.embedding import EmbeddingService
            self.embedding_service = EmbeddingService()
            print(f"🔧 Initialized embedding service")

        # Generate embedding for the theory (compressed text/summary)
        theory_embedding = []
        if summary_data:
            try:
                print(f"🔄 Generating theory embedding for summary ({len(summary_data)} chars)...")
                theory_embedding = self.embedding_service.embed_text(summary_data)
                print(f"✅ Theory embedding generated: {len(theory_embedding)} dimensions")
            except Exception as e:
                print(f"⚠️  Failed to generate theory embedding: {e}")
                theory_embedding = []

        # Build Neo4j construction plan format
        neo4j_format = {
            "nodes": [],
            "relationships": []
        }

        # 1. TOPIC Node
        if topic_data:
            topic_node = {
                "id": topic_id,
                "construction_type": "node",
                "label": "TOPIC",
                "unique_column_name": "name",
                "properties": {
                    "name": topic_data
                }
            }
            neo4j_format["nodes"].append(topic_node)

        # 2. THEORY Node
        theory_node = {
            "id": theory_id,
            "construction_type": "node",
            "label": "THEORY",
            "unique_column_name": "id",
            "properties": {
                "id": theory_id,
                "original_text": original_text,
                "compressed_text": summary_data or "",
                "embedding": theory_embedding,
                "source": source_filename,
                "keywords": keywords_data
            }
        }
        neo4j_format["nodes"].append(theory_node)

        # 3. CONCEPT Nodes with embeddings
        print(f"🔄 Generating embeddings for {len(concepts_data)} concepts...")
        for i, concept in enumerate(concepts_data):
            concept_id = f"concept_{Path(source_file).stem}_{i}"

            # Generate embedding for concept definition
            concept_embedding = []
            if concept['definition']:
                try:
                    concept_embedding = self.embedding_service.embed_text(concept['definition'])
                    print(f"✅ Concept {i+1} embedding generated: {len(concept_embedding)} dimensions")
                except Exception as e:
                    print(f"⚠️  Failed to generate embedding for concept {i+1}: {e}")
                    concept_embedding = []

            concept_node = {
                "id": concept_id,
                "construction_type": "node",
                "label": "CONCEPT",
                "unique_column_name": "name",
                "properties": {
                    "name": concept['name'],
                    "definition": concept['definition'],
                    "embedding": concept_embedding
                }
            }
            neo4j_format["nodes"].append(concept_node)

        # 4. Relationships
        # TOPIC -[HAS]-> THEORY relationship
        if topic_data:
            has_relationship = {
                "construction_type": "relationship",
                "relationship_type": "HAS",
                "from_node_id": topic_id,
                "from_node_label": "TOPIC",
                "to_node_id": theory_id,
                "to_node_label": "THEORY",
                "properties": {}
            }
            neo4j_format["relationships"].append(has_relationship)

        # THEORY -[MENTIONS]-> CONCEPT relationships
        for i, concept in enumerate(concepts_data):
            concept_id = f"concept_{Path(source_file).stem}_{i}"
            mentions_relationship = {
                "construction_type": "relationship",
                "relationship_type": "MENTIONS",
                "from_node_id": theory_id,
                "from_node_label": "THEORY",
                "to_node_id": concept_id,
                "to_node_label": "CONCEPT",
                "properties": {}
            }
            neo4j_format["relationships"].append(mentions_relationship)

        return neo4j_format