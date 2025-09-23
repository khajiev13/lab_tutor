"""
Native LangChain-based Canonical Concept Extraction Service

Replaces LangExtract with pure LangChain implementation using structured output
for the canonical relationship-centric approach.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import ValidationError

from models.extraction_models import (
    CanonicalExtractionResult,
    CanonicalExtractionWithText,
    CompleteExtractionResult,
    ExtractionMetadata,
    ConceptExtraction
)


class LangChainCanonicalExtractionService:
    """
    LangChain-based canonical concept extraction service.
    
    Uses LangChain's structured output capabilities with Pydantic models
    for reliable concept extraction in the canonical relationship-centric approach.
    """
    
    def __init__(self, model_id: str = "gemini-2.0-flash", verbose: bool = True) -> None:
        """
        Initialize the LangChain extraction service.

        Args:
            model_id: Google Gemini model ID to use for extraction
            verbose: Enable verbose logging for debugging
        """
        self.model_id = model_id
        self.api_key = os.environ.get('GOOGLE_API_KEY')
        self.verbose = verbose

        # Instance variables for saving lambda
        self.current_output_path = None
        self.current_filename = None
        self.current_original_text = None

        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")

        # Initialize LangChain LLM with structured output and native verbose mode
        self.llm = ChatGoogleGenerativeAI(
            model=model_id,
            google_api_key=self.api_key,
            temperature=0,
            verbose=self.verbose  # Use LangChain's native verbose mode
        )
        
        # Create structured output chain with json_mode for better Gemini compatibility
        self.extraction_chain = self.llm.with_structured_output(
            CanonicalExtractionResult,
            method="json_mode"
        )

        # Create the extraction prompt template using LangChain message classes
        self.prompt_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=self._get_system_prompt()),
            HumanMessage(content=self._get_user_prompt())
        ])

        # Create saving lambda for automatic JSON saving
        self.saving_lambda = RunnableLambda(self._save_extraction_result)

        # Complete 3-component extraction and saving chain
        self.chain = self.prompt_template | self.extraction_chain | self.saving_lambda

    def _get_system_prompt(self) -> str:
        """Get the optimized system prompt for canonical concept extraction."""
        return """Extract structured knowledge from technical documents with strict text grounding.

**RULES:**
- Only extract concepts explicitly mentioned in source text
- Provide exact text evidence for each concept
- Use clear, descriptive concept names as they appear in the text
- Ensure all extracted information is directly supported by the source text

**EXTRACT:**
1. **Topic**: Concise document title
2. **Summary**: Clear overview (30-50% of original)
3. **Keywords**: 5-10 central terms from text
4. **Concepts**: Important concepts with definitions and exact quotes as evidence"""

    def _get_user_prompt(self) -> str:
        """Get the optimized user prompt template."""
        return """Analyze the text and extract structured information. Only extract concepts explicitly mentioned in the source text.

**Text:**
{text}

Extract the following:
- **Topic**: A concise title that captures the main subject
- **Summary**: A clear overview of the content
- **Keywords**: 5-10 important terms directly from the text
- **Concepts**: Key concepts with their definitions and exact text evidence (quotes) from the source"""

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



    def _save_extraction_result(self, extraction_result: CanonicalExtractionResult) -> CanonicalExtractionResult:
        """
        Saving lambda function for the chain - saves extraction result to JSON and returns it unchanged.

        Args:
            extraction_result: The structured extraction result from with_structured_output()

        Returns:
            The same extraction result (for chain continuation)
        """
        if self.current_output_path and self.current_filename:
            try:
                # Create output directory
                output_path = Path(self.current_output_path)
                output_path.mkdir(parents=True, exist_ok=True)

                # Create extended result with original_text if available using Pydantic
                if hasattr(self, 'current_original_text') and self.current_original_text:
                    # Create a new model instance with original_text added
                    result_data = extraction_result.model_dump()
                    result_data['original_text'] = self.current_original_text

                    # Save using Pydantic's native JSON serialization
                    json_path = output_path / f"{self.current_filename}_extraction.json"

                    with open(json_path, 'w', encoding='utf-8') as f:
                        import json
                        json.dump(result_data, f, indent=2, ensure_ascii=False)
                else:
                    # Save using Pydantic's native JSON serialization
                    json_path = output_path / f"{self.current_filename}_extraction.json"

                    with open(json_path, 'w', encoding='utf-8') as f:
                        f.write(extraction_result.model_dump_json(indent=2))

                if self.verbose:
                    print(f"✅ Extraction JSON saved: {json_path}")

            except Exception as e:
                if self.verbose:
                    print(f"⚠️  Failed to save extraction JSON: {e}")

        return extraction_result



    def compress_and_extract_concepts(self, documents: List[Document], source_file_path: Optional[str] = None) -> CompleteExtractionResult:
        """
        Extract canonical concepts using LangChain structured output.

        Args:
            documents: List of Document objects to process
            source_file_path: Path to the source file being processed

        Returns:
            CompleteExtractionResult with canonical concept extractions
        """
        if not documents:
            raise ValueError("No documents provided for extraction")

        # Get the raw document content (outside try block for error handling)
        raw_text = documents[0].page_content

        # Preprocess to remove numbers and titles
        cleaned_text = self.preprocess_text(raw_text)

        try:

            # Note: Saving parameters should be set by the calling service
            # If not set, use defaults
            if not self.current_output_path:
                if source_file_path:
                    base_filename = Path(source_file_path).stem
                    self.current_output_path = f"extraction_output/{base_filename}"
                    self.current_filename = base_filename
                else:
                    self.current_output_path = "extraction_output"
                    self.current_filename = "extraction_result"

            # Set the original text for saving
            self.current_original_text = cleaned_text

            # Invoke the 3-component chain (prompt | extraction | saving)
            # LangChain's verbose mode is controlled by the LLM initialization
            extraction_result = self.chain.invoke({"text": cleaned_text}, verbose=self.verbose)

            # Create extraction result with original text (trust LLM's concept naming)
            extraction_result_with_text = CanonicalExtractionWithText(
                topic=extraction_result.topic,
                summary=extraction_result.summary,
                keywords=extraction_result.keywords,
                concepts=extraction_result.concepts,  # Use LLM output directly
                original_text=cleaned_text  # Include the cleaned text that was processed
            )
            
            # Create metadata
            metadata = ExtractionMetadata(
                source_file=source_file_path,
                original_text_length=len(raw_text),
                processed_text_length=len(cleaned_text),
                model_used=self.model_id
            )
            
            # Create complete result with original text
            complete_result = CompleteExtractionResult(
                extraction=extraction_result_with_text,
                metadata=metadata,
                success=True
            )

            if self.verbose:
                print(f"✅ Successfully extracted {len(extraction_result_with_text.concepts)} canonical concepts using LangChain")
            
            return complete_result
            
        except ValidationError as e:
            error_msg = f"Pydantic validation error: {e}"
            if self.verbose:
                print(f"❌ {error_msg}")
            # Get raw_text length safely
            raw_text_length = len(documents[0].page_content) if documents else 0
            # Create error result with original text
            error_extraction = CanonicalExtractionWithText(
                topic="Extraction Failed",
                summary="Failed to extract content due to validation error. Please check the input text and model response format.",
                keywords=["extraction", "failed", "validation", "error", "processing"],  # Meet minimum 5 keywords
                concepts=[ConceptExtraction(name="Error", definition="An error occurred during the extraction process", text_evidence="N/A - Error case")],  # Meet minimum 1 concept
                original_text=cleaned_text
            )

            return CompleteExtractionResult(
                extraction=error_extraction,
                metadata=ExtractionMetadata(
                    source_file=source_file_path,
                    original_text_length=raw_text_length,
                    processed_text_length=0,
                    model_used=self.model_id
                ),
                success=False,
                error_message=error_msg
            )

        except Exception as e:
            error_msg = f"Extraction error: {str(e)}"
            if self.verbose:
                print(f"❌ {error_msg}")
            # Get raw_text length safely
            raw_text_length = len(documents[0].page_content) if documents else 0
            # Create error result with original text
            error_extraction = CanonicalExtractionWithText(
                topic="Extraction Failed",
                summary="Failed to extract content due to processing error. Please check the input text and API configuration.",
                keywords=["extraction", "failed", "processing", "error", "system"],  # Meet minimum 5 keywords
                concepts=[ConceptExtraction(name="Error", definition="A system error occurred during the extraction process", text_evidence="N/A - Error case")],  # Meet minimum 1 concept
                original_text=cleaned_text
            )

            return CompleteExtractionResult(
                extraction=error_extraction,
                metadata=ExtractionMetadata(
                    source_file=source_file_path,
                    original_text_length=raw_text_length,
                    processed_text_length=0,
                    model_used=self.model_id
                ),
                success=False,
                error_message=error_msg
            )

    def extract_and_save_results(self, documents: List[Document], output_dir: str,
                               source_file_path: Optional[str] = None, generate_viz: bool = False) -> Dict[str, Any]:
        """
        Extract canonical concepts and save results (without LangExtract visualizations).

        Args:
            documents: List of Document objects to process
            output_dir: Directory to save results
            source_file_path: Path to the source file being processed
            generate_viz: Ignored (no visualizations in LangChain implementation)

        Returns:
            Dictionary with processing results and file paths
        """
        # Unused parameter kept for API compatibility
        _ = generate_viz
        try:
            # Perform extraction
            extraction_result = self.compress_and_extract_concepts(documents, source_file_path)

            # Determine base filename
            if source_file_path:
                base_filename = Path(source_file_path).stem
            else:
                base_filename = "extraction_result"

            # Save results
            saved_files = self.save_extraction_results(extraction_result, output_dir, base_filename)

            return {
                'success': extraction_result.success,
                'source_file': source_file_path,
                'saved_files': saved_files,
                'extraction_result': extraction_result,
                'error': extraction_result.error_message if not extraction_result.success else None
            }

        except Exception as e:
            if self.verbose:
                print(f"❌ Error during extraction: {e}")
            return {
                'success': False,
                'source_file': source_file_path,
                'error': str(e),
                'saved_files': {}
            }

    def save_extraction_results(self, extraction_result: CompleteExtractionResult,
                              output_dir: str, base_filename: str) -> Dict[str, str]:
        """Save extraction results in JSON format using Pydantic's native serialization."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        saved_files = {}

        # Save as JSON using Pydantic's native serialization
        try:
            json_path = output_path / f"{base_filename}_langchain.json"

            # Use Pydantic's native JSON serialization
            with open(json_path, 'w', encoding='utf-8') as f:
                f.write(extraction_result.model_dump_json(indent=2))

            saved_files['langchain_json'] = str(json_path)
            if self.verbose:
                print(f"✅ LangChain JSON saved: {json_path}")

        except Exception as json_error:
            if self.verbose:
                print(f"⚠️  Failed to save JSON: {json_error}")

        return saved_files



    @staticmethod
    def load_from_json(json_path: str) -> CompleteExtractionResult:
        """
        Load extraction results from JSON file back into Pydantic models using native deserialization.

        Args:
            json_path: Path to the JSON file saved by save_extraction_results

        Returns:
            CompleteExtractionResult loaded from JSON

        Raises:
            FileNotFoundError: If the JSON file doesn't exist
            ValidationError: If the JSON doesn't match the expected schema
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            json_content = f.read()

        # Use Pydantic's native JSON deserialization
        return CompleteExtractionResult.model_validate_json(json_content)


