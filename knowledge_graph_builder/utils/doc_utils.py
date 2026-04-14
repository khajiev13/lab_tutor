import re
from langchain_community.document_loaders import Docx2txtLoader
from langchain_core.documents import Document
from pathlib import Path
from typing import Dict, Any, Optional, List
import json


def load_docx_documents(files_directory: str) -> list[Document]:
    """
    Load all DOCX files from the specified directory.

    Args:
        files_directory: Path to the directory containing DOCX files

    Returns:
        List of Document objects loaded from DOCX files with source metadata

    Raises:
        FileNotFoundError: If no DOCX files are found in the directory
    """
    dir_path = Path(files_directory)

    # Find all .docx files in the directory
    docx_files = list(dir_path.glob("*.docx"))

    if not docx_files:
        raise FileNotFoundError("No DOCX files found in the directory")

    documents = []

    # Load all DOCX files and add source metadata
    for docx_file in docx_files:
        loader = Docx2txtLoader(str(docx_file))
        docs = loader.load()

        # Add source file path to document metadata
        for doc in docs:
            if not doc.metadata:
                doc.metadata = {}
            doc.metadata['source_file'] = str(docx_file)
            doc.metadata['source_filename'] = docx_file.name

        documents.extend(docs)

    return documents


def load_single_docx_document(file_path: str) -> List[Document]:
    """
    Load a single DOCX file and return documents with source metadata.

    Args:
        file_path: Path to the DOCX file

    Returns:
        List of Document objects with source metadata

    Raises:
        FileNotFoundError: If the file doesn't exist
    """
    docx_path = Path(file_path)

    if not docx_path.exists():
        raise FileNotFoundError(f"DOCX file not found: {file_path}")

    loader = Docx2txtLoader(str(docx_path))
    docs = loader.load()

    # Add source file path to document metadata
    for doc in docs:
        if not doc.metadata:
            doc.metadata = {}
        doc.metadata['source_file'] = str(docx_path)
        doc.metadata['source_filename'] = docx_path.name

    return docs


def find_original_docx(json_filename: str, docx_directory: str) -> Optional[str]:
    """
    Find the corresponding DOCX file for a given JSON filename.
    
    Args:
        json_filename: Name of the JSON file (e.g., "BDA 4-1.json" or "BDA 4-1_with_embeddings.json")
        docx_directory: Directory containing DOCX files
        
    Returns:
        Path to the corresponding DOCX file, or None if not found
    """
    # Remove .json extension and _with_embeddings suffix if present
    base_name = json_filename.replace('.json', '').replace('_with_embeddings', '')
    docx_path = Path(docx_directory) / f"{base_name}.docx"
    
    if docx_path.exists():
        return str(docx_path)
    
    print(f"⚠️  Warning: No corresponding DOCX file found for {json_filename}")
    return None


def load_and_preprocess_docx(docx_path: str, extraction_service) -> str:
    """
    Load and preprocess DOCX content using the extraction service.
    
    Args:
        docx_path: Path to the DOCX file
        extraction_service: Service for text preprocessing
        
    Returns:
        Preprocessed text content
    """
    try:
        # Load DOCX content
        loader = Docx2txtLoader(docx_path)
        documents = loader.load()
        
        if not documents:
            return ""
        
        # Combine all document content
        raw_text = "\n".join([doc.page_content for doc in documents])
        
        # Preprocess using extraction service
        preprocessed_text = extraction_service.preprocess_text(raw_text)
        
        return preprocessed_text
        
    except Exception as e:
        print(f"❌ Error loading DOCX file {docx_path}: {e}")
        return ""


def load_json_file(json_path: str) -> Dict[str, Any]:
    """
    Load JSON file and return parsed data.
    
    Args:
        json_path: Path to the JSON file
        
    Returns:
        Parsed JSON data
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def ensure_embeddings_exist(data: Dict[str, Any], embedding_service) -> Dict[str, Any]:
    """
    Ensure that all nodes that need embeddings have them.
    
    For the corrected schema:
    - TOPIC nodes don't need embeddings (only have name)
    - THEORY nodes need embeddings (from topic summary)
    - CONCEPT nodes need embeddings (from definition)
    
    Args:
        data: JSON data structure
        embedding_service: Service for generating embeddings
        
    Returns:
        Updated data structure with embeddings
    """
    # Track which nodes need embeddings
    texts_to_embed = []
    node_indices = []
    
    for i, node in enumerate(data.get('nodes', [])):
        node_type = node.get('type')
        
        # Only Topic and Concept nodes in JSON need embeddings
        # Topic embeddings will be used for THEORY nodes
        if node_type == 'Topic' and 'embedding' not in node:
            if 'summary' in node:
                texts_to_embed.append(node['summary'])
                node_indices.append(i)
                
        elif node_type == 'Concept' and 'embedding' not in node:
            if 'definition' in node:
                texts_to_embed.append(node['definition'])
                node_indices.append(i)
    
    # Generate embeddings if needed
    if texts_to_embed:
        print(f"📡 Generating embeddings for {len(texts_to_embed)} nodes...")
        embeddings = embedding_service.embed_documents(texts_to_embed)
        
        # Add embeddings back to nodes
        for embedding, node_idx in zip(embeddings, node_indices):
            data['nodes'][node_idx]['embedding'] = embedding
            
        print(f"✅ Added embeddings to {len(texts_to_embed)} nodes")
    
    return data


def discover_json_files(json_directory: str) -> List[Path]:
    """
    Discover JSON files, preferring those with embeddings.
    
    Args:
        json_directory: Directory containing JSON files
        
    Returns:
        List of JSON file paths, preferring files with embeddings
    """
    # Find all JSON files, preferring those with embeddings
    all_json_files = list(Path(json_directory).glob("*.json"))
    
    # Create a mapping of base names to files
    file_mapping = {}
    for file in all_json_files:
        if file.name.endswith("_with_embeddings.json"):
            base_name = file.name.replace("_with_embeddings.json", "")
            file_mapping[base_name] = file
        else:
            base_name = file.name.replace(".json", "")
            if base_name not in file_mapping:  # Only add if no embedding version exists
                file_mapping[base_name] = file
    
    return list(file_mapping.values())

