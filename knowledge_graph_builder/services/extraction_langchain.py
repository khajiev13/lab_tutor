"""
Native LangChain-based Canonical Concept Extraction Service

Replaces LangExtract with pure LangChain implementation using structured output
for the canonical relationship-centric approach.
"""

import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableConfig
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from pydantic import ValidationError

from models.extraction_models import (
    CanonicalExtractionResult,
    CanonicalExtractionWithText,
    CompleteExtractionResult,
    ExtractionMetadata,
    ConceptExtraction
)
from prompts.extraction_prompts import (
    COMPLETE_EXTRACTION_PROMPT,
    EXTRACTION_PROMPT_WITH_EXAMPLES
)

logger = logging.getLogger(__name__)


class LangChainCanonicalExtractionService:
    """
    LangChain-based canonical concept extraction service.
    
    Uses LangChain's structured output capabilities with Pydantic models
    for reliable concept extraction in the canonical relationship-centric approach.
    """
    
    def __init__(
        self,
        model_id: str | None = None,
        verbose: bool = True,
        enhanced_debug: bool = False,
        use_examples: bool = True,
    ) -> None:
        """
        Initialize the LangChain extraction service.

        Args:
            model_id: Google Gemini model ID to use for extraction
            verbose: Enable verbose logging for debugging
            enhanced_debug: Enable enhanced debugging with detailed step-by-step output
            use_examples: Use few-shot examples in prompts for better performance
        """
        load_dotenv()

        # XiaoCase (OpenAI-compatible) is the only supported LLM backend.
        xiaocase_api_key = os.getenv("XIAO_CASE_API_KEY") or os.getenv("XIAOCASE_API_KEY")
        xiaocase_api_base = (
            os.getenv("XIAO_CASE_API_BASE")
            or os.getenv("XIAOCASE_API_BASE")
            or "https://api.xiaocaseai.com/v1"
        )

        # If caller didn't specify a model, choose via env or sensible default.
        if model_id is None:
            model_id = (
                os.getenv("XIAO_CASE_MODEL")
                or os.getenv("XIAOCASE_MODEL")
                or "deepseek-v3.2"
            )

        self.model_id = model_id
        self.verbose = verbose
        self.enhanced_debug = enhanced_debug or verbose  # Enhanced debug if explicitly enabled or verbose is True
        self.use_examples = use_examples

        # Instance variables for saving lambda
        self.current_output_path = None
        self.current_filename = None
        self.current_original_text = None

        if not xiaocase_api_key:
            raise ValueError(
                "XiaoCase is required. Set XIAO_CASE_API_KEY (or XIAOCASE_API_KEY) in your environment."
            )

        # XiaoCase uses OpenAI-compatible Chat Completions: /v1/chat/completions
        # Model can be DeepSeek variants, e.g. "deepseek-v3.2".
        base_llm = ChatOpenAI(
            model=model_id,
            base_url=xiaocase_api_base,
            api_key=SecretStr(xiaocase_api_key),
            temperature=0,
            timeout=600,
            max_completion_tokens=4096,
        )

        # For GPT-4o via proxy, json_mode tends to be more reliable.
        # For DeepSeek and others, function_calling usually works better.
        method = "json_mode" if "gpt-4o" in model_id else "function_calling"
        self.extraction_chain = base_llm.with_structured_output(CanonicalExtractionResult, method=method)
        self.llm = base_llm

        # Create simple prompt template using separated prompt content
        prompt_content = EXTRACTION_PROMPT_WITH_EXAMPLES if self.use_examples else COMPLETE_EXTRACTION_PROMPT
        self.prompt_template = PromptTemplate.from_template(prompt_content)

        # Create saving lambda for automatic JSON saving
        self.saving_lambda = RunnableLambda(self._save_extraction_result)

        # Complete 3-component extraction and saving chain
        self.chain = self.prompt_template | self.extraction_chain | self.saving_lambda

    def set_debug_mode(self, verbose: bool = True, enhanced_debug: bool = False, use_examples: Optional[bool] = None) -> None:
        """
        Set debugging mode and prompt configuration at runtime.

        Args:
            verbose: Enable basic verbose logging
            enhanced_debug: Enable enhanced debugging with detailed step-by-step output
            use_examples: Use few-shot examples in prompts (None = keep current setting)
        """
        self.verbose = verbose
        self.enhanced_debug = enhanced_debug or verbose

        # Update examples setting if provided
        if use_examples is not None:
            self.use_examples = use_examples
            # Recreate prompt template with new setting
            prompt_content = EXTRACTION_PROMPT_WITH_EXAMPLES if self.use_examples else COMPLETE_EXTRACTION_PROMPT
            self.prompt_template = PromptTemplate.from_template(prompt_content)
            # Recreate the chain with updated prompt
            self.chain = self.prompt_template | self.extraction_chain | self.saving_lambda

        # Update LLM verbose mode
        self.llm.verbose = verbose

        if enhanced_debug:
            logger.info("Enhanced debugging mode ENABLED")
        elif verbose:
            logger.info("Verbose mode ENABLED")
        else:
            logger.info("Debug mode DISABLED")



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

                if self.enhanced_debug:
                    logger.debug(f"Extraction JSON saved: {json_path} - Size: {json_path.stat().st_size} bytes, Concepts: {len(extraction_result.concepts)}")
                elif self.verbose:
                    logger.info(f"Extraction JSON saved: {json_path}")

            except Exception as e:
                if self.enhanced_debug or self.verbose:
                    logger.error(f"Failed to save extraction JSON: {e}")

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

        # Debug document loading to verify content
        if self.enhanced_debug:
            print(f"\n📄 DOCUMENT LOADING VERIFICATION")
            print("=" * 60)
            print(f"📁 Source file: {source_file_path}")
            print(f"📄 Raw text length: {len(raw_text)} characters")
            print(f"📄 Raw text preview: {raw_text[:200]}...")
            print(f"📄 Contains NoSQL: {'NoSQL' in raw_text or 'nosql' in raw_text.lower()}")
            print(f"📄 Contains C++: {'C++' in raw_text or 'cpp' in raw_text.lower()}")
            print("=" * 60)

        # Preprocess to remove numbers and titles
        cleaned_text = self.preprocess_text(raw_text)

        # Debug preprocessing to verify text cleaning
        if self.enhanced_debug:
            print(f"\n🧹 TEXT PREPROCESSING VERIFICATION")
            print("=" * 60)
            print(f"📄 Cleaned text length: {len(cleaned_text)} characters")
            print(f"📄 Cleaned text preview: {cleaned_text[:200]}...")
            print(f"📄 Preprocessing removed {len(raw_text) - len(cleaned_text)} characters")
            print(f"📄 Still contains NoSQL: {'NoSQL' in cleaned_text or 'nosql' in cleaned_text.lower()}")
            print(f"📄 Still contains C++: {'C++' in cleaned_text or 'cpp' in cleaned_text.lower()}")
            print("=" * 60)

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
            # Enhanced verbose debugging with comprehensive configuration
            if self.enhanced_debug:
                print("🔍 ENHANCED VERBOSE DEBUGGING ENABLED")
                print("=" * 60)
                print(f"📄 Processing text length: {len(cleaned_text)} characters")
                print(f"📄 Original text length: {len(raw_text)} characters")
                print(f"🤖 Model: {self.model_id}")
                print(f"💾 Output path: {self.current_output_path}")
                print(f"📝 Filename: {self.current_filename}")
                print(f"\n📖 TEXT PREVIEW (first 200 chars):")
                print(f"   {cleaned_text[:200]}...")
                print("=" * 60)

                # Debug simple prompt template rendering with ACTUAL substituted text
                print("\n🎯 PROMPT TEMPLATE DEBUGGING")
                print("=" * 60)
                try:
                    formatted_prompt = self.prompt_template.invoke({"text": cleaned_text})
                    # PromptTemplate returns a PromptValue, convert to string
                    prompt_string = formatted_prompt.to_string()

                    print(f"📝 Formatted Prompt Preview (first 300 chars):")
                    print(f"   {prompt_string[:300]}...")
                    print(f"📊 Total prompt length: {len(prompt_string)} characters")

                    # Verify the text was properly substituted
                    if "{text}" in prompt_string:
                        print("❌ WARNING: Text substitution FAILED - {text} placeholder still present!")
                        print(f"   Contains input text: False")
                        print(f"   Text substitution successful: False")
                    else:
                        # Check if actual content was substituted
                        contains_input = any(phrase in prompt_string for phrase in ["NoSQL", "Key Value", "Document-Oriented"])
                        print(f"   Contains input text: {contains_input}")
                        print(f"   Text substitution successful: True")
                        print("✅ Text substitution successful")

                except Exception as e:
                    print(f"❌ Prompt formatting error: {e}")
                print("=" * 60)

            # Configure enhanced debugging with RunnableConfig
            config = RunnableConfig(
                metadata={
                    "source_file": source_file_path,
                    "text_length": len(cleaned_text),
                    "model": self.model_id,
                    "debug_mode": "enhanced_verbose"
                }
            )

            # Debug the actual input being sent to the chain
            if self.enhanced_debug:
                print(f"\n🔍 CHAIN INPUT VERIFICATION")
                print("=" * 60)
                chain_input = {"text": cleaned_text}
                print(f"📥 Input key: 'text'")
                print(f"📥 Input value length: {len(chain_input['text'])} characters")
                print(f"📥 Input preview: {chain_input['text'][:200]}...")
                print(f"📥 Contains NoSQL content: {'NoSQL' in chain_input['text']}")
                print(f"📥 Contains C++ content: {'C++' in chain_input['text']}")
                print("=" * 60)

            extraction_result = self.chain.invoke({"text": cleaned_text}, config=config)

            # Enhanced verbose debugging - show extraction results with content verification
            if self.enhanced_debug:
                print("\n🎯 EXTRACTION RESULTS SUMMARY")
                print("=" * 60)
                print(f"📋 Topic: {extraction_result.topic}")
                print(f"📝 Summary length: {len(extraction_result.summary)} characters")
                print(f"🔑 Keywords count: {len(extraction_result.keywords)}")
                print(f"🧠 Concepts extracted: {len(extraction_result.concepts)}")

                # Content consistency verification
                print(f"\n🔍 CONTENT CONSISTENCY CHECK:")
                input_has_nosql = 'NoSQL' in cleaned_text or 'nosql' in cleaned_text.lower()
                input_has_cpp = 'C++' in cleaned_text or 'cpp' in cleaned_text.lower()
                topic_has_nosql = 'NoSQL' in extraction_result.topic or 'nosql' in extraction_result.topic.lower()
                topic_has_cpp = 'C++' in extraction_result.topic or 'cpp' in extraction_result.topic.lower()

                print(f"   Input contains NoSQL: {input_has_nosql}")
                print(f"   Input contains C++: {input_has_cpp}")
                print(f"   Topic contains NoSQL: {topic_has_nosql}")
                print(f"   Topic contains C++: {topic_has_cpp}")

                if input_has_nosql and topic_has_cpp:
                    print("   ❌ CONTENT MISMATCH: Input is NoSQL but topic is C++!")
                elif input_has_cpp and topic_has_nosql:
                    print("   ❌ CONTENT MISMATCH: Input is C++ but topic is NoSQL!")
                else:
                    print("   ✅ Content appears consistent")

                print(f"\n🔑 KEYWORDS: {', '.join(extraction_result.keywords)}")
                print("\n🔍 CONCEPT DETAILS:")
                for i, concept in enumerate(extraction_result.concepts, 1):
                    print(f"   {i}. {concept.name}")
                    print(f"      Definition: {concept.definition[:100]}...")
                    print(f"      Evidence: {concept.text_evidence[:80]}...")
                print("=" * 60)

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
                logger.info(f"Successfully extracted {len(extraction_result_with_text.concepts)} canonical concepts using LangChain")
            
            return complete_result
            
        except ValidationError as e:
            error_msg = f"Pydantic validation error: {e}"
            if self.verbose:
                logger.error(error_msg)
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
                logger.error(error_msg)
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
                logger.error(f"Error during extraction: {e}")
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
                logger.info(f"LangChain JSON saved: {json_path}")

        except Exception as json_error:
            if self.verbose:
                logger.warning(f"Failed to save JSON: {json_error}")

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


