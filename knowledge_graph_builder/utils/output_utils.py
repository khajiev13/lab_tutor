"""
Output Organization Utilities

Utilities for organizing extraction output files into topic-based folder structures.
Handles topic name extraction, sanitization, folder creation, file moving, and cleanup.
"""

from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from models.extraction_models import CompleteExtractionResult


def organize_extraction_output(
    extraction_result: CompleteExtractionResult,
    document_path: str,
    output_dir: str,
    temp_output_path: Path,
    base_filename: str
) -> Tuple[Dict[str, str], Path]:
    """
    Organize extraction output into topic-based folder structure.
    
    This function handles the complete file organization workflow:
    1. Extracts topic name from extraction result or falls back to document filename
    2. Sanitizes topic name for filesystem use
    3. Creates topic-based folder structure
    4. Moves extraction files from temp location to final topic folder
    5. Cleans up temporary directories
    
    Args:
        extraction_result: CompleteExtractionResult from LangChain extraction
        document_path: Path to the source document being processed
        output_dir: Base output directory for organized files
        temp_output_path: Temporary directory containing extraction files
        base_filename: Base filename for the extraction files
        
    Returns:
        Tuple containing:
        - saved_files: Dictionary mapping file types to their final paths
        - topic_folder: Path to the final topic folder
        
    Raises:
        OSError: If file operations fail (creation, moving, etc.)
    """
    # Extract topic name from LangChain result
    if extraction_result.success:
        topic_name = extraction_result.extraction.topic
    else:
        # Fallback to document filename if extraction failed
        topic_name = Path(document_path).stem

    # Create final topic-based folder structure
    base_output_path = Path(output_dir)
    
    # Sanitize topic name for filesystem use
    sanitized_topic = _sanitize_topic_name(topic_name)
    topic_folder = base_output_path / sanitized_topic
    topic_folder.mkdir(parents=True, exist_ok=True)

    # Move the extraction file to the correct topic folder
    temp_json_path = temp_output_path / f"{base_filename}_extraction.json"
    final_json_path = topic_folder / f"{base_filename}_extraction.json"

    saved_files = {}
    if temp_json_path.exists():
        # Move the file to the final location
        temp_json_path.rename(final_json_path)
        saved_files['extraction_json'] = str(final_json_path)

        # Clean up temp directory
        _cleanup_temp_directory(temp_output_path)

    return saved_files, topic_folder


def _sanitize_topic_name(topic_name: str, max_length: int = 50) -> str:
    """
    Sanitize topic name for use as a folder name.
    
    Args:
        topic_name: Raw topic name from extraction
        max_length: Maximum length for folder name
        
    Returns:
        Sanitized folder name safe for filesystem use
    """
    if not topic_name:
        return "Unknown_Topic"

    # Replace problematic characters with underscores
    sanitized = topic_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
    
    # Remove other potentially problematic characters
    problematic_chars = '<>:"|?*'
    for char in problematic_chars:
        sanitized = sanitized.replace(char, '_')
    
    # Remove multiple consecutive underscores
    while '__' in sanitized:
        sanitized = sanitized.replace('__', '_')
    
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    
    # Truncate if too long
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip('_')
    
    # Ensure we have something
    if not sanitized:
        return "Unknown_Topic"

    return sanitized


def _cleanup_temp_directory(temp_path: Path) -> None:
    """
    Clean up temporary directory after file operations.
    
    Args:
        temp_path: Path to temporary directory to clean up
    """
    try:
        # Only remove if directory is empty
        temp_path.rmdir()
    except OSError:
        # Directory not empty, doesn't exist, or permission issues
        # This is expected behavior - we don't force cleanup
        pass


def create_topic_folder(output_dir: str, topic_name: str) -> Path:
    """
    Create a topic-based folder structure.
    
    Args:
        output_dir: Base output directory
        topic_name: Topic name to use for folder creation
        
    Returns:
        Path to the created topic folder
    """
    base_output_path = Path(output_dir)
    sanitized_topic = _sanitize_topic_name(topic_name)
    topic_folder = base_output_path / sanitized_topic
    topic_folder.mkdir(parents=True, exist_ok=True)
    return topic_folder


def move_file_to_topic_folder(
    source_file: Path,
    topic_folder: Path,
    new_filename: Optional[str] = None
) -> str:
    """
    Move a file to a topic folder with optional renaming.
    
    Args:
        source_file: Path to the source file to move
        topic_folder: Destination topic folder
        new_filename: Optional new filename (uses original if not provided)
        
    Returns:
        String path to the moved file
        
    Raises:
        FileNotFoundError: If source file doesn't exist
        OSError: If file move operation fails
    """
    if not source_file.exists():
        raise FileNotFoundError(f"Source file not found: {source_file}")
    
    filename = new_filename or source_file.name
    destination = topic_folder / filename
    
    source_file.rename(destination)
    return str(destination)
