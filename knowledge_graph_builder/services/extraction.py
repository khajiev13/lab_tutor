from langchain_core.documents import Document
import langextract as lx
import textwrap
from typing import List, Dict, Any, Optional
import os
import re
from pathlib import Path
import json

class ExtractionService:
    """
    LLM-based Text Compression and Concept Extraction Service
    
    Uses LLM to compress text and extract concepts in a single operation.
    Includes preprocessing to remove numbers and nonsensical titles.
    """
    def __init__(self, documents: List[Document], model_id: str = "gemini-2.5-pro") -> None:
        self.documents: List[Document] = documents
        self.base_url = "https://api.xiaocaseai.com/v1"
        self.model_id = model_id
        self.api_key = os.environ.get('LANGEXTRACT_API_KEY')

        if not self.api_key:
            raise ValueError("XIAO_CASE_API_KEY environment variable is required")
        
        # Enhanced prompt for LLM-based extraction of topic, summary, concepts, and keywords
        self.extraction_prompt = textwrap.dedent("""\
            You are an expert at analyzing educational text to extract key information.

            **Task**: Your goal is to extract four types of information from the text:
            1.  **Topic Title**: A single, concise title for the entire document.
            2.  **Compressed Summary**: A detailed summary of the entire text, reduced to 30-50% of its original length while preserving all critical information.
            3.  **Keywords**: A list of 5-10 most important keywords and key phrases that represent the main topics and concepts in the text.
            4.  **Concepts**: A list of core technical terms, theories, and technologies mentioned.

            **Extraction Rules**:
            -   **Topic**: Extract exactly one `TOPIC`. The text should be a short, descriptive title.
            -   **Summary**: Extract exactly one `SUMMARY`. The text should be the compressed version of the document.
            -   **Keywords**: Extract exactly one `KEYWORDS` entity. The text should be a comma-separated list of 5-10 key terms that best represent the document's content.
            -   **Concepts**: Extract all relevant `CONCEPT`s. For each concept, provide a `definition` attribute.
            """)
        
        # Example showing LLM-based extraction of topic, summary, keywords, and concepts
        self.extraction_examples = [
            lx.data.ExampleData(
            text="In-memory computation is a technique for running large-scale, complex calculations entirely in a computer cluster's collective RAM. This eliminates slower data access from disks to improve performance. A computer cluster is a group of computers that work together, pooling their RAM.",
            extractions=[
                lx.data.Extraction(
                extraction_class="TOPIC",
                extraction_text="In-Memory Computation and Computer Clusters"
                ),
                lx.data.Extraction(
                extraction_class="SUMMARY",
                extraction_text="In-memory computation uses cluster RAM for calculations, avoiding disk access for better performance."
                ),
                lx.data.Extraction(
                extraction_class="KEYWORDS",
                extraction_text="in-memory computation, computer cluster, RAM, distributed computing, performance optimization, large-scale calculations"
                ),
                lx.data.Extraction(
                extraction_class="CONCEPT",
                extraction_text="In-memory computation",
                attributes={
                    "definition": "A technique for running large-scale, complex calculations entirely in a computer cluster's collective RAM."
                }
                ),
                lx.data.Extraction(
                extraction_class="CONCEPT",
                extraction_text="Computer Cluster",
                attributes={
                    "definition": "A group of computers that work together, pooling their RAM to perform large-scale calculations."
                }
                )
            ]
            )
        ]
        
    def preprocess_text(self, text: str) -> str:
        """
        Simple preprocessing to remove numbers and nonsensical titles.
        """
        # Remove nonsensical titles at the beginning (like "transcript BD 1-1 Concepts", "BDA 5-1")
        text = re.sub(r'^(transcript\s+)?(BD|BDA|Big\s+data)\s*\d*[-\d]*\s*[^\n]*\n?', '', text, flags=re.MULTILINE | re.IGNORECASE)
        
        # Remove standalone numbers on their own lines (like "1", "2", "3")
        text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
        
        # Remove numbers at the beginning of lines (numbered lists)
        text = re.sub(r'^\d+\.?\s*', '', text, flags=re.MULTILINE)
        
        # Clean up excessive whitespace
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Multiple newlines to double
        text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)  # Leading spaces
        text = text.strip()
        
        return text

    def compress_and_extract_concepts(self, source_file_path: Optional[str] = None) -> Any:
        """
        Single method that uses preprocessing + LLM to compress text and extract concepts.

        Process:
        1. Preprocess text to remove numbers and nonsensical titles
        2. LLM handles compression, keyword extraction, and concept extraction in one operation
        3. Add source file path to the results

        Args:
            source_file_path: Path to the source file being processed

        Returns:
            Dictionary containing extraction results with compressed concepts, keywords, and source info
        """
        # Get the raw document content
        raw_text = self.documents[0].page_content
        
        # Preprocess to remove numbers and titles
        cleaned_text = self.preprocess_text(raw_text)
        
        # Show preprocessing results
        print(f"Original text length: {len(raw_text)}")
        print(f"After preprocessing length: {len(cleaned_text)}")
        print(f"Preprocessing removed: {len(raw_text) - len(cleaned_text)} characters")
        print(f"\nFirst 200 chars of cleaned text:")
        print(f"{cleaned_text[:200]}...")
        
        
        # Use LLM for compression and extraction on cleaned text with custom OpenAI endpoint
        print(f"🔄 Using custom OpenAI endpoint: {self.base_url}")
        print(f"📋 Model: {self.model_id}")
        
        result = lx.extract(
            text_or_documents=cleaned_text,
            prompt_description=self.extraction_prompt,
            examples=self.extraction_examples,
            model_id=self.model_id,
            api_key=self.api_key,
            model_url=self.base_url,
            max_char_buffer=12000,
        )

        # The result from lx.extract is already a list of AnnotatedDocument objects
        # We need to return both the LangExtract result and our structured data
        structured_data = self._enhance_extraction_result(result, cleaned_text, source_file_path)

        print(f"✅ Successfully extracted concepts with preprocessing + LLM compression")

        # Return the original LangExtract result for visualization,
        # but add our structured data as metadata
        if isinstance(result, list) and len(result) > 0:
            # Add our structured data to the first document's metadata
            result[0].metadata = result[0].metadata or {}
            result[0].metadata['structured_data'] = structured_data
            result[0].metadata['source_file'] = source_file_path
            result[0].metadata['original_text'] = cleaned_text
        elif hasattr(result, 'metadata'):
            # Single AnnotatedDocument case
            result.metadata = result.metadata or {}
            result.metadata['structured_data'] = structured_data
            result.metadata['source_file'] = source_file_path
            result.metadata['original_text'] = cleaned_text

        return result

    def _enhance_extraction_result(self, result: Any, original_text: str, source_file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Enhance the extraction result with additional metadata and structure it for ingestion.

        Args:
            result: Raw extraction result from LangExtract
            original_text: The cleaned/preprocessed text that was extracted from
            source_file_path: Path to the source file

        Returns:
            Enhanced result with proper structure for ingestion
        """
        try:
            # Initialize the enhanced structure
            enhanced_result = {
                "nodes": [],
                "relationships": [],
                "metadata": {
                    "source_file": source_file_path,
                    "original_text": original_text,
                    "extraction_timestamp": None  # Could add timestamp if needed
                }
            }

            # Process extractions from LangExtract result
            topic_data = {}
            concepts = []

            # Handle different result formats from LangExtract
            extractions = []
            try:
                # Try to access extractions from the result
                if hasattr(result, 'extractions'):
                    # Result is a single AnnotatedDocument
                    extractions = result.extractions
                elif isinstance(result, list) and len(result) > 0:
                    # Result is a list - try to get first item
                    first_item = result[0]
                    if hasattr(first_item, 'extractions'):
                        extractions = first_item.extractions
                else:
                    print(f"⚠️  Unexpected result format: {type(result)}")
                    print(f"Result content: {result}")
            except (IndexError, AttributeError, TypeError) as e:
                print(f"⚠️  Error processing result format: {e}")
                print(f"Result type: {type(result)}")
                # Try to print result safely
                try:
                    print(f"Result content: {str(result)[:200]}...")
                except:
                    print("Could not display result content")

            # Process all extractions
            for extraction in extractions:
                        extraction_class = extraction.extraction_class.upper()
                        extraction_text = extraction.extraction_text

                        if extraction_class == "TOPIC":
                            topic_data["name"] = extraction_text
                            topic_data["type"] = "Topic"
                            topic_data["id"] = f"topic_{extraction_text.lower().replace(' ', '_')}"

                        elif extraction_class == "SUMMARY":
                            topic_data["summary"] = extraction_text

                        elif extraction_class == "KEYWORDS":
                            # Parse comma-separated keywords
                            keywords = [kw.strip() for kw in extraction_text.split(",")]
                            topic_data["keywords"] = keywords

                        elif extraction_class == "CONCEPT":
                            concept_data = {
                                "id": f"concept_{extraction_text.lower().replace(' ', '_')}",
                                "type": "Concept",
                                "name": extraction_text,
                                "definition": extraction.attributes.get("definition", "") if extraction.attributes else ""
                            }
                            concepts.append(concept_data)

            # Add source file path to topic data
            if source_file_path:
                topic_data["source"] = source_file_path

            # Ensure keywords field exists (empty if not extracted)
            if topic_data and "keywords" not in topic_data:
                topic_data["keywords"] = []

            # Add topic node if we have one
            if topic_data:
                enhanced_result["nodes"].append(topic_data)

            # Add concept nodes
            enhanced_result["nodes"].extend(concepts)

            # Create relationships between topic and concepts
            if topic_data and concepts:
                for concept in concepts:
                    relationship = {
                        "source": topic_data["id"],
                        "target": concept["id"],
                        "type": "mentions"
                    }
                    enhanced_result["relationships"].append(relationship)

            return enhanced_result

        except Exception as e:
            print(f"❌ Error enhancing extraction result: {e}")
            # Return the original result with error info
            return {
                "error": f"Enhancement failed: {str(e)}",
                "original_result": result,
                "nodes": [],
                "relationships": []
            }

    def set_documents(self, documents: List[Document]) -> None:
        """
        Set the documents to be processed.

        Args:
            documents: List of Document objects to process
        """
        self.documents = documents

    def get_documents(self) -> List[Document]:
        """
        Get the currently loaded documents.

        Returns:
            List of Document objects
        """
        return self.documents

    def save_extraction_results(self, result: Any, output_dir: str, base_filename: str) -> Dict[str, str]:
        """
        Save extraction results in multiple formats for different use cases.

        Args:
            result: The extraction result from compress_and_extract_concepts
            output_dir: Directory to save files
            base_filename: Base name for output files (without extension)

        Returns:
            Dictionary with paths to saved files
        """
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        saved_files = {}

        try:
            # Handle both single AnnotatedDocument and list cases
            documents_to_save = []
            metadata_source = None

            if isinstance(result, list) and len(result) > 0:
                documents_to_save = result
                metadata_source = result[0]
            elif hasattr(result, 'metadata'):
                # Single AnnotatedDocument
                documents_to_save = [result]
                metadata_source = result

            # 1. Save as JSONL for LangExtract visualization
            if documents_to_save:
                try:
                    jsonl_path = output_path / f"{base_filename}_langextract.jsonl"
                    lx.io.save_annotated_documents(
                        documents_to_save,
                        output_dir=str(output_path),
                        output_name=f"{base_filename}_langextract.jsonl",
                        show_progress=False
                    )
                    saved_files['langextract_jsonl'] = str(jsonl_path)
                    print(f"✅ LangExtract JSONL saved: {jsonl_path}")
                except Exception as jsonl_error:
                    print(f"⚠️  Failed to save JSONL: {jsonl_error}")
                    # Continue to try saving JSON even if JSONL fails

                # 2. Extract and save structured JSON for ingestion pipeline
                if metadata_source and hasattr(metadata_source, 'metadata') and metadata_source.metadata:
                    if 'structured_data' in metadata_source.metadata:
                        structured_data = metadata_source.metadata['structured_data']
                        json_path = output_path / f"{base_filename}.json"
                        with open(json_path, 'w', encoding='utf-8') as f:
                            json.dump(structured_data, f, indent=2, ensure_ascii=False)
                        saved_files['structured_json'] = str(json_path)
                        print(f"✅ Structured JSON saved: {json_path}")
                    else:
                        print(f"⚠️  No structured_data found in metadata")
                else:
                    print(f"⚠️  No metadata found in result")

            # Fallback: if result is already structured data
            elif hasattr(result, 'nodes') or isinstance(result, dict):
                json_path = output_path / f"{base_filename}.json"
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                saved_files['structured_json'] = str(json_path)
                print(f"✅ Structured JSON saved: {json_path}")

        except Exception as e:
            print(f"⚠️  Error saving extraction results: {e}")

        return saved_files

    def generate_visualization(self, jsonl_path: str, output_dir: str, base_filename: str) -> Optional[str]:
        """
        Generate HTML visualization from JSONL file using LangExtract.

        Args:
            jsonl_path: Path to the JSONL file
            output_dir: Directory to save visualization
            base_filename: Base name for the HTML file

        Returns:
            Path to generated HTML file, or None if failed
        """
        try:
            output_path = Path(output_dir)
            html_path = output_path / f"{base_filename}_visualization.html"

            # Generate visualization using LangExtract
            html_content = lx.visualize(
                jsonl_path,
                animation_speed=1.0,
                show_legend=True,
                gif_optimized=True
            )

            # Save HTML content
            with open(html_path, 'w', encoding='utf-8') as f:
                if hasattr(html_content, 'data'):
                    f.write(html_content.data)  # For Jupyter/Colab environments
                elif isinstance(html_content, str):
                    f.write(html_content)
                else:
                    f.write(str(html_content))

            print(f"✅ Visualization saved: {html_path}")
            return str(html_path)

        except Exception as e:
            print(f"⚠️  Failed to generate visualization: {e}")
            return None

    def process_document_with_visualization(self, source_file_path: Optional[str] = None,
                                          output_dir: str = "output",
                                          generate_viz: bool = True) -> Dict[str, Any]:
        """
        Complete processing pipeline: extract, save, and visualize.

        Args:
            source_file_path: Path to the source file being processed
            output_dir: Directory for output files
            generate_viz: Whether to generate HTML visualization

        Returns:
            Dictionary with processing results and file paths
        """
        try:
            # Perform extraction
            extraction_result = self.compress_and_extract_concepts(source_file_path)

            # Determine base filename
            if source_file_path:
                base_filename = Path(source_file_path).stem
            else:
                base_filename = "extraction_result"

            # Save results in multiple formats
            saved_files = self.save_extraction_results(extraction_result, output_dir, base_filename)

            # Generate visualization if requested and JSONL was saved
            html_path = None
            if generate_viz and 'langextract_jsonl' in saved_files:
                html_path = self.generate_visualization(
                    saved_files['langextract_jsonl'],
                    output_dir,
                    base_filename
                )
                if html_path:
                    saved_files['visualization_html'] = html_path

            return {
                'success': True,
                'source_file': source_file_path,
                'extraction_result': extraction_result,
                'saved_files': saved_files,
                'base_filename': base_filename
            }

        except Exception as e:
            print(f"❌ Error in processing pipeline: {e}")
            return {
                'success': False,
                'source_file': source_file_path,
                'error': str(e)
            }
