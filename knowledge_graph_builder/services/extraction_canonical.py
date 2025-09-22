from langchain_core.documents import Document
import langextract as lx
import textwrap
from typing import List, Dict, Any, Optional
import os
import re
from pathlib import Path
import json

class CanonicalExtractionService:
    """
    LLM-based Text Compression and Canonical Concept Extraction Service
    
    Uses LLM to compress text and extract canonical concepts for relationship-centric approach.
    Focuses on canonical concept names and stores contextual definitions in relationships.
    """
    def __init__(self, model_id: str = "gemini-2.5-pro") -> None:
        self.base_url = "https://api.xiaocaseai.com/v1"
        self.model_id = model_id
        self.api_key = os.environ.get('LANGEXTRACT_API_KEY')

        if not self.api_key:
            raise ValueError("XIAO_CASE_API_KEY environment variable is required")
        
        # Enhanced prompt for canonical concept extraction
        self.extraction_prompt = textwrap.dedent("""\
        You are an expert at analyzing technical and educational lecture transcripts to extract structured knowledge.

        **Task**: Extract the following four categories of information from the text:
        1. **Topic Title (TOPIC)**: A single concise title summarizing the session's overall subject.
        2. **Compressed Summary (SUMMARY)**: A clear and coherent summary of the session, reduced to 30–50% of the original length, covering all major sections and arguments.
        3. **Keywords (KEYWORDS)**: A comma-separated list of 5–10 high-value terms, phrases, or entities most central to the lecture.
        4. **Canonical Concepts (CONCEPT)**: All important theories, models, technologies, frameworks, or technical terms. Use CANONICAL names that represent the core concept, not specific variations or implementations.

        **Critical Concept Naming Rules**:
        - Use the most general, canonical form of concept names (e.g., "Web Crawler" not "Web Crawler Crawling Strategy")
        - Avoid redundant or overly specific variations (e.g., "MapReduce" not "MapReduce Programming Model")
        - Use standard terminology from the field (e.g., "Machine Learning" not "ML Algorithms and Techniques")
        - For each concept, provide a `definition` attribute using the text's exact meaning for THIS specific context
        - The definition should capture how this concept is used in THIS document, not a general definition

        **Extraction Rules**:
        - **Topic**: Extract exactly one TOPIC.
        - **Summary**: Extract exactly one SUMMARY that maintains logical flow.
        - **Keywords**: Extract exactly one KEYWORDS entity with 5–10 items.
        - **Concepts**: Extract multiple CONCEPT entities with canonical names and context-specific definitions.
        - Preserve technical accuracy but use canonical concept names (e.g., "HDFS," "NoSQL," "Big Data").
        """)

        # Example showing canonical concept extraction
        self.extraction_examples = [
            lx.data.ExampleData(
                text="The Big Data lifecycle has four stages: Collect, Store, Analyze, and Governance. Collecting involves gathering structured and unstructured data. Storage relies on platforms like HDFS and databases. Analysis applies tools like MapReduce, Spark, and MySQL. Governance ensures compliance, accuracy, and security. The DIKW pyramid explains the transformation from data to information, knowledge, and wisdom.",
                extractions=[
                    lx.data.Extraction(
                        extraction_class="TOPIC",
                        extraction_text="Big Data Lifecycle and Analysis Frameworks"
                    ),
                    lx.data.Extraction(
                        extraction_class="SUMMARY",
                        extraction_text="The Big Data lifecycle consists of four stages: collection, storage, analysis, and governance. Collection gathers structured and unstructured data from various sources. Storage uses distributed systems like HDFS and traditional databases. Analysis employs processing frameworks like MapReduce and Spark alongside databases like MySQL. Governance maintains data quality, compliance, and security. The DIKW pyramid illustrates the progression from raw data to actionable wisdom through information and knowledge transformation."
                    ),
                    lx.data.Extraction(
                        extraction_class="KEYWORDS",
                        extraction_text="big data lifecycle, collect, store, analyze, governance, DIKW pyramid, Hadoop, Spark, HDFS, real-time analytics"
                    ),
                    lx.data.Extraction(
                        extraction_class="CONCEPT",
                        extraction_text="DIKW Pyramid",
                        attributes={
                            "definition": "A model showing the progression from data (facts) to information (organized data), to knowledge (meaningful information), and wisdom (actionable insights)."
                        }
                    ),
                    lx.data.Extraction(
                        extraction_class="CONCEPT",
                        extraction_text="OLTP",
                        attributes={
                            "definition": "Online Transaction Processing, a method of handling routine transactions using databases in early stages of data analysis."
                        }
                    ),
                    lx.data.Extraction(
                        extraction_class="CONCEPT",
                        extraction_text="OLAP",
                        attributes={
                            "definition": "Online Analytical Processing, which allows analysis of integrated organizational data for improved business decisions."
                        }
                    ),
                    lx.data.Extraction(
                        extraction_class="CONCEPT",
                        extraction_text="HDFS",
                        attributes={
                            "definition": "Hadoop Distributed File System, the main storage platform for big data, supporting distributed processing and integration with tools like Hive."
                        }
                    )
                ]
            )
        ]

    def preprocess_text(self, text: str) -> str:
        """
        Preprocess text to remove numbers, nonsensical titles, and improve extraction quality.
        
        Args:
            text: Raw text to preprocess
            
        Returns:
            Cleaned text ready for LLM processing
        """
        # Remove standalone numbers and number-heavy lines
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
                
            # Skip lines that are mostly numbers (like page numbers, timestamps)
            if re.match(r'^[\d\s\-:.,]+$', line):
                continue
                
            # Skip very short lines that are likely artifacts
            if len(line) < 10:
                continue
                
            # Skip lines with excessive punctuation or special characters
            if len(re.findall(r'[^\w\s]', line)) > len(line) * 0.3:
                continue
                
            cleaned_lines.append(line)
        
        # Join lines back together
        cleaned_text = '\n'.join(cleaned_lines)
        
        # Additional cleanup
        # Remove excessive whitespace
        cleaned_text = re.sub(r'\n\s*\n', '\n\n', cleaned_text)
        cleaned_text = re.sub(r' +', ' ', cleaned_text)
        
        return cleaned_text.strip()

    def compress_and_extract_concepts(self, documents: List[Document], source_file_path: Optional[str] = None) -> Any:
        """
        Single method that uses preprocessing + LLM to compress text and extract canonical concepts.

        Process:
        1. Preprocess text to remove numbers and nonsensical titles
        2. LLM handles compression, keyword extraction, and canonical concept extraction in one operation
        3. Add source file path to the results

        Args:
            documents: List of Document objects to process
            source_file_path: Path to the source file being processed

        Returns:
            LangExtract AnnotatedDocument with canonical concept extractions
        """
        if not documents:
            raise ValueError("No documents provided for extraction")

        # Get the raw document content
        raw_text = documents[0].page_content
        
        # Preprocess to remove numbers and titles
        cleaned_text = self.preprocess_text(raw_text)
        
        # Show preprocessing results
        print(f"Original text length: {len(raw_text)}")
        print(f"After preprocessing length: {len(cleaned_text)}")
        print(f"Preprocessing removed: {len(raw_text) - len(cleaned_text)} characters")
        print(f"\nFirst 200 chars of cleaned text:")
        print(f"{cleaned_text[:200]}...")
        
        # Use LLM for compression and canonical extraction on cleaned text
        print(f"🔄 Using custom OpenAI endpoint: {self.base_url}")
        print(f"📋 Model: {self.model_id}")
        
        result = lx.extract(
            text_or_documents=cleaned_text,
            prompt_description=self.extraction_prompt,
            examples=self.extraction_examples,
            model_id=self.model_id,
            api_key=self.api_key,
            model_url=self.base_url,
            max_char_buffer=16000,
        )

        print(f"✅ Successfully extracted canonical concepts with preprocessing + LLM compression")
        
        return result

    def normalize_concept_name(self, concept_name: str) -> str:
        """
        Normalize concept names to canonical forms.
        
        Args:
            concept_name: Raw concept name from extraction
            
        Returns:
            Normalized canonical concept name
        """
        if not concept_name:
            return concept_name
            
        # Remove common redundant suffixes
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
            r'\s+(Implementation|Implementations)$'
        ]
        
        normalized = concept_name.strip()
        
        for pattern in redundant_patterns:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
        
        # Clean up extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized if normalized else concept_name

    def extract_and_save_results(self, documents: List[Document], output_dir: str, 
                               source_file_path: Optional[str] = None, generate_viz: bool = True) -> Dict[str, Any]:
        """
        Extract canonical concepts and save results in multiple formats.

        Args:
            documents: List of Document objects to process
            output_dir: Directory to save results
            source_file_path: Path to the source file being processed
            generate_viz: Whether to generate HTML visualization

        Returns:
            Dictionary with processing results and file paths
        """
        try:
            # Perform extraction
            extraction_result = self.compress_and_extract_concepts(documents, source_file_path)

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
                'saved_files': saved_files,
                'extraction_result': extraction_result
            }

        except Exception as e:
            print(f"❌ Error during extraction: {e}")
            return {
                'success': False,
                'source_file': source_file_path,
                'error': str(e)
            }

    def save_extraction_results(self, extraction_result: Any, output_dir: str, base_filename: str) -> Dict[str, str]:
        """Save extraction results in multiple formats."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        saved_files = {}
        
        # Save as JSONL for LangExtract
        try:
            jsonl_path = output_path / f"{base_filename}_langextract.jsonl"
            
            # Handle both single AnnotatedDocument and list cases
            documents_to_save = []
            if isinstance(extraction_result, list):
                documents_to_save = extraction_result
            elif hasattr(extraction_result, 'text'):  # Single AnnotatedDocument
                documents_to_save = [extraction_result]
            
            if documents_to_save:
                lx.io.save_annotated_documents(
                    documents_to_save,
                    output_dir=str(output_path),
                    output_name=f"{base_filename}_langextract.jsonl",
                    show_progress=False
                )
                saved_files['langextract_jsonl'] = str(jsonl_path)
                print(f"✅ LangExtract JSONL saved: {jsonl_path}")
            else:
                print(f"⚠️  No documents to save as JSONL")
                
        except Exception as jsonl_error:
            print(f"⚠️  Failed to save JSONL: {jsonl_error}")
        
        return saved_files

    def generate_visualization(self, jsonl_path: str, output_dir: str, base_filename: str) -> Optional[str]:
        """Generate HTML visualization from JSONL file."""
        try:
            output_path = Path(output_dir)
            html_path = output_path / f"{base_filename}_visualization.html"
            
            # Generate visualization using LangExtract
            html_content = lx.visualize(
                jsonl_path,
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
            
            print(f"✅ Visualization saved: {html_path}")
            return str(html_path)
            
        except Exception as viz_error:
            print(f"⚠️  Failed to generate visualization: {viz_error}")
            return None
