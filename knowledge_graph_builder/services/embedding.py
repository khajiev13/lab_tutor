from langchain_openai import OpenAIEmbeddings
from typing import List, Optional, Dict, Any
import os
import json
from pydantic import SecretStr
from dotenv import load_dotenv
load_dotenv()
class EmbeddingService:
    """Service for generating text embeddings using OpenAI-compatible API."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.xiaocaseai.com/v1",
        model: str = "text-embedding-3-small"
    ):
        """
        Initialize the embedding service.
        
        Args:
            api_key: API key for authentication (if None, reads from XIAO_CASE_API_KEY env var)
            base_url: Custom base URL for the API
            model: Model name to use for embeddings
        """
        if api_key is None:
            api_key = os.getenv("XIAO_CASE_API_KEY")
            if api_key is None:
                raise ValueError("API key must be provided either as parameter or XIAO_CASE_API_KEY environment variable")
        
        self.embeddings = OpenAIEmbeddings(
            api_key=SecretStr(api_key),
            base_url=base_url,
            model=model
        )
    
    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Input text to embed
            
        Returns:
            List of float values representing the embedding
        """
        return self.embeddings.embed_query(text)
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of input texts to embed
            
        Returns:
            List of embeddings, each as a list of float values
        """
        return self.embeddings.embed_documents(texts)
    
    async def aembed_text(self, text: str) -> List[float]:
        """
        Asynchronously generate embedding for a single text.
        
        Args:
            text: Input text to embed
            
        Returns:
            List of float values representing the embedding
        """
        return await self.embeddings.aembed_query(text)
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Asynchronously generate embeddings for multiple texts.
        
        Args:
            texts: List of input texts to embed
            
        Returns:
            List of embeddings, each as a list of float values
        """
        return await self.embeddings.aembed_documents(texts)
    
    def embed_structured_document(self, json_file_path: str, output_file_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load a structured JSON document, generate embeddings for Topic summaries and Concept definitions,
        and return the updated document with embeddings added.
        
        Args:
            json_file_path: Path to the input JSON file containing the structured document
            output_file_path: Optional path to save the updated JSON file with embeddings
            
        Returns:
            Dictionary containing the updated document structure with embeddings
        """
        # Load the JSON file
        with open(json_file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        
        # Extract texts to embed and track their corresponding nodes
        texts_to_embed = []
        node_indices = []
        
        for i, node in enumerate(data.get('nodes', [])):
            if node.get('type') == 'Topic' and 'summary' in node:
                texts_to_embed.append(node['summary'])
                node_indices.append(i)
            elif node.get('type') == 'Concept' and 'definition' in node:
                texts_to_embed.append(node['definition'])
                node_indices.append(i)
        
        # Generate embeddings for all texts at once (more efficient)
        if texts_to_embed:
            embeddings = self.embed_documents(texts_to_embed)
            
            # Add embeddings back to the corresponding nodes
            for embedding, node_idx in zip(embeddings, node_indices):
                data['nodes'][node_idx]['embedding'] = embedding
        
        # Save to output file if specified
        if output_file_path:
            with open(output_file_path, 'w', encoding='utf-8') as file:
                json.dump(data, file, indent=2, ensure_ascii=False)
        
        return data