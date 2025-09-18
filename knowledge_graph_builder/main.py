#!/usr/bin/env python3
"""
Knowledge Graph Builder - Production Main Pipeline

This is the production entry point for the complete knowledge graph building system.
It processes all documents in the unstructured_script/ directory using:

1. Topic-based folder organization
2. LangExtract integration with interactive visualizations  
3. Embedding generation for all concepts and theories
4. Neo4j database ingestion with vector search capabilities

The system uses IngestionService as the central coordinator for all operations.
"""

import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging


from services.ingestion import IngestionService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('knowledge_graph_builder.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class KnowledgeGraphBuilder:
    """Production knowledge graph builder with comprehensive processing and monitoring."""
    
    def __init__(self, input_dir: str = "unstructured_script", output_dir: str = "production_output"):
        """
        Initialize the knowledge graph builder.
        
        Args:
            input_dir: Directory containing DOCX files to process
            output_dir: Base directory for topic-based output
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.ingestion_service = IngestionService()
        
        # Processing statistics
        self.stats = {
            'total_documents': 0,
            'processed_successfully': 0,
            'processing_failed': 0,
            'topics_created': 0,
            'total_processing_time': 0,
            'neo4j_insertions_successful': 0,
            'neo4j_insertions_failed': 0,
            'total_nodes_created': 0,
            'total_relationships_created': 0,
            'processed_documents': [],
            'failed_documents': [],
            'topic_summary': {}
        }
    
    def discover_documents(self) -> List[Path]:
        """
        Discover all DOCX files in the input directory, sorted alphabetically.
        
        Returns:
            List of DOCX file paths sorted alphabetically
        """
        if not self.input_dir.exists():
            logger.error(f"Input directory not found: {self.input_dir}")
            return []
        
        docx_files = sorted(self.input_dir.glob("*.docx"))
        logger.info(f"Discovered {len(docx_files)} DOCX files in {self.input_dir}")
        
        for i, file_path in enumerate(docx_files, 1):
            logger.info(f"  {i:2d}. {file_path.name}")
        
        return docx_files
    
    def process_single_document(self, docx_path: Path) -> Dict[str, Any]:
        """
        Process a single document through the complete pipeline.
        
        Args:
            docx_path: Path to the DOCX file
            
        Returns:
            Processing result dictionary
        """
        start_time = time.time()
        
        logger.info(f"🔄 Processing: {docx_path.name}")
        
        try:
            # Process document with topic-based organization and immediate Neo4j insertion
            result = self.ingestion_service.process_document_with_langextract(
                str(docx_path),
                str(self.output_dir),
                insert_to_neo4j=True  # Enable streaming insertion
            )
            
            processing_time = time.time() - start_time
            
            if result['success']:
                topic_name = result.get('topic_name', 'Unknown Topic')
                sanitized_topic = result.get('sanitized_topic', 'Unknown_Topic')
                
                logger.info(f"✅ Successfully processed: {docx_path.name}")
                logger.info(f"   📋 Topic: {topic_name}")
                logger.info(f"   📁 Folder: {sanitized_topic}/")
                logger.info(f"   ⏱️  Processing time: {processing_time:.2f}s")
                
                # Log file details
                saved_files = result.get('saved_files', {})
                for file_type, file_path in saved_files.items():
                    file_size = Path(file_path).stat().st_size
                    logger.info(f"   📄 {file_type}: {Path(file_path).name} ({file_size:,} bytes)")

                # Log Neo4j insertion results
                neo4j_result = result.get('neo4j_insertion')
                if neo4j_result:
                    if neo4j_result.get('success'):
                        logger.info(f"   🗄️  Neo4j: {neo4j_result['nodes_created']} nodes, {neo4j_result['relationships_created']} relationships")
                    else:
                        logger.warning(f"   ⚠️  Neo4j insertion failed: {neo4j_result.get('error', 'Unknown error')}")

                # Update statistics
                self.stats['processed_successfully'] += 1
                self.stats['processed_documents'].append({
                    'file': docx_path.name,
                    'topic': topic_name,
                    'sanitized_topic': sanitized_topic,
                    'processing_time': processing_time,
                    'files_created': len(saved_files),
                    'neo4j_success': neo4j_result.get('success', False) if neo4j_result else False,
                    'nodes_created': neo4j_result.get('nodes_created', 0) if neo4j_result else 0,
                    'relationships_created': neo4j_result.get('relationships_created', 0) if neo4j_result else 0
                })
                
                # Track unique topics
                if sanitized_topic not in self.stats['topic_summary']:
                    self.stats['topic_summary'][sanitized_topic] = {
                        'topic_name': topic_name,
                        'documents': [],
                        'total_files': 0
                    }
                
                self.stats['topic_summary'][sanitized_topic]['documents'].append(docx_path.name)
                self.stats['topic_summary'][sanitized_topic]['total_files'] += len(saved_files)

                # Update Neo4j statistics
                if neo4j_result and neo4j_result.get('success'):
                    self.stats['neo4j_insertions_successful'] += 1
                    self.stats['total_nodes_created'] += neo4j_result.get('nodes_created', 0)
                    self.stats['total_relationships_created'] += neo4j_result.get('relationships_created', 0)
                elif neo4j_result:
                    self.stats['neo4j_insertions_failed'] += 1
                
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"❌ Failed to process: {docx_path.name} - {error_msg}")
                
                self.stats['processing_failed'] += 1
                self.stats['failed_documents'].append({
                    'file': docx_path.name,
                    'error': error_msg,
                    'processing_time': processing_time
                })
            
            self.stats['total_processing_time'] += processing_time
            return result
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"❌ Exception processing {docx_path.name}: {e}")
            
            self.stats['processing_failed'] += 1
            self.stats['total_processing_time'] += processing_time
            self.stats['failed_documents'].append({
                'file': docx_path.name,
                'error': str(e),
                'processing_time': processing_time
            })
            
            return {'success': False, 'error': str(e)}
    
    def process_all_documents(self) -> bool:
        """
        Process all documents in the input directory.
        
        Returns:
            True if at least one document was processed successfully
        """
        logger.info("🚀 Starting Knowledge Graph Builder - Production Pipeline")
        logger.info("=" * 80)
        
        # Discover documents
        docx_files = self.discover_documents()
        if not docx_files:
            logger.error("No DOCX files found to process")
            return False
        
        self.stats['total_documents'] = len(docx_files)
        
        logger.info(f"\n📋 Processing {len(docx_files)} documents...")
        logger.info("-" * 50)
        
        # Process each document
        for i, docx_path in enumerate(docx_files, 1):
            logger.info(f"\n[{i}/{len(docx_files)}] Processing document...")
            self.process_single_document(docx_path)
        
        # Update topics created count
        self.stats['topics_created'] = len(self.stats['topic_summary'])
        
        return self.stats['processed_successfully'] > 0

    def get_final_database_stats(self) -> Dict[str, Any]:
        """
        Get final database statistics after streaming insertions.

        Returns:
            Dictionary with database statistics
        """
        try:
            return self.ingestion_service.neo4j_service.get_database_stats()
        except Exception as e:
            logger.warning(f"Could not retrieve database stats: {e}")
            return {}

    def print_final_summary(self, final_db_stats: Optional[Dict[str, Any]] = None):
        """Print comprehensive final summary of the entire pipeline."""
        logger.info(f"\n🎉 Knowledge Graph Builder - Final Summary")
        logger.info("=" * 80)

        # Document processing summary
        logger.info(f"📄 Document Processing:")
        logger.info(f"   • Total documents: {self.stats['total_documents']}")
        logger.info(f"   • Successfully processed: {self.stats['processed_successfully']}")
        logger.info(f"   • Failed: {self.stats['processing_failed']}")
        logger.info(f"   • Success rate: {(self.stats['processed_successfully']/self.stats['total_documents']*100):.1f}%")
        logger.info(f"   • Total processing time: {self.stats['total_processing_time']:.2f}s")
        logger.info(f"   • Average time per document: {(self.stats['total_processing_time']/self.stats['total_documents']):.2f}s")

        # Topic organization summary
        logger.info(f"\n📋 Topic Organization:")
        logger.info(f"   • Unique topics created: {self.stats['topics_created']}")

        if self.stats['topic_summary']:
            logger.info(f"   • Topic breakdown:")
            for _, topic_info in self.stats['topic_summary'].items():
                doc_count = len(topic_info['documents'])
                file_count = topic_info['total_files']
                logger.info(f"     - {topic_info['topic_name']}: {doc_count} docs, {file_count} files")

        # Neo4j database summary (streaming approach)
        logger.info(f"\n🗄️  Neo4j Database (Streaming Insertion):")
        logger.info(f"   • Successful insertions: {self.stats['neo4j_insertions_successful']}")
        logger.info(f"   • Failed insertions: {self.stats['neo4j_insertions_failed']}")
        logger.info(f"   • Total nodes created: {self.stats['total_nodes_created']}")
        logger.info(f"   • Total relationships created: {self.stats['total_relationships_created']}")

        if final_db_stats:
            logger.info(f"   • Final database contents:")
            for stat_name, count in final_db_stats.items():
                if stat_name != 'error':
                    logger.info(f"     - {stat_name}: {count}")

        # Failed documents (if any)
        if self.stats['failed_documents']:
            logger.info(f"\n⚠️  Failed Documents:")
            for failed_doc in self.stats['failed_documents']:
                logger.info(f"   • {failed_doc['file']}: {failed_doc['error']}")

        # Output location
        logger.info(f"\n📁 Output Location: {self.output_dir}/")
        if self.stats['neo4j_insertions_successful'] > 0:
            logger.info(f"🌐 Neo4j Browser: http://localhost:7474")
            logger.info(f"   Username: neo4j, Password: password123")

        # Overall success criteria: documents processed and at least some Neo4j insertions successful
        overall_success = (self.stats['processed_successfully'] > 0 and
                          self.stats['neo4j_insertions_successful'] > 0)
        logger.info(f"\n🎯 Pipeline Status: {'✅ SUCCESS' if overall_success else '❌ FAILED'}")

    def run_complete_pipeline(self) -> bool:
        """
        Run the complete knowledge graph building pipeline.

        Returns:
            True if the pipeline completed successfully
        """
        start_time = time.time()

        try:
            # Step 1: Process all documents with streaming Neo4j insertion
            documents_processed = self.process_all_documents()

            if not documents_processed:
                logger.error("No documents were processed successfully")
                return False

            # Step 2: Get final database statistics
            logger.info(f"\n📊 Retrieving final database statistics...")
            final_db_stats = self.get_final_database_stats()

            # Step 3: Final summary
            total_time = time.time() - start_time
            logger.info(f"\n⏱️  Total pipeline execution time: {total_time:.2f}s")

            self.print_final_summary(final_db_stats)

            return documents_processed

        except Exception as e:
            logger.error(f"❌ Pipeline failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """Main entry point for the production knowledge graph builder."""

    # Initialize and run the knowledge graph builder
    builder = KnowledgeGraphBuilder()

    success = builder.run_complete_pipeline()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
