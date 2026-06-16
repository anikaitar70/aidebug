"""Embedding service for creating vector embeddings"""

import logging
from typing import List
import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generate embeddings for code chunks"""
    
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        """
        Initialize embedding service
        
        Args:
            model_name: HuggingFace model name for embeddings
        """
        self.model_name = model_name
        self._model = None
        self._initialize_model()
    
    def _initialize_model(self):
        """Lazy load embedding model"""
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
        except ImportError:
            logger.warning("sentence-transformers not available, using mock embeddings")
            self._model = None
    
    async def embed_text(self, text: str) -> List[float]:
        """
        Create embedding for text
        
        Args:
            text: Input text
            
        Returns:
            Embedding vector as list of floats
        """
        if self._model is None:
            return self._mock_embedding(text)
        
        try:
            embedding = self._model.encode(text, convert_to_tensor=False)
            return embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return self._mock_embedding(text)
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Create embeddings for multiple texts
        
        Args:
            texts: List of input texts
            
        Returns:
            List of embedding vectors
        """
        if self._model is None:
            return [self._mock_embedding(text) for text in texts]
        
        try:
            embeddings = self._model.encode(texts, convert_to_tensor=False)
            return [emb.tolist() if hasattr(emb, 'tolist') else list(emb) for emb in embeddings]
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            return [self._mock_embedding(text) for text in texts]
    
    @staticmethod
    def _mock_embedding(text: str) -> List[float]:
        """Generate mock embedding for testing"""
        # Simple hash-based mock embedding
        hash_value = hash(text) % 10000
        np.random.seed(hash_value)
        return np.random.randn(384).tolist()
    
    async def compute_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float]
    ) -> float:
        """
        Compute cosine similarity between two embeddings
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Similarity score between 0 and 1
        """
        arr1 = np.array(embedding1)
        arr2 = np.array(embedding2)
        
        # Normalize vectors
        arr1_norm = arr1 / (np.linalg.norm(arr1) + 1e-8)
        arr2_norm = arr2 / (np.linalg.norm(arr2) + 1e-8)
        
        # Compute cosine similarity
        similarity = np.dot(arr1_norm, arr2_norm)
        return float((similarity + 1) / 2)  # Convert from [-1, 1] to [0, 1]


# Global service instance
_embedding_service: EmbeddingService | None = None


async def get_embedding_service() -> EmbeddingService:
    """Get embedding service instance"""
    global _embedding_service
    if _embedding_service is None:
        from app.utils.config import get_settings
        settings = get_settings()
        _embedding_service = EmbeddingService(settings.EMBEDDING_MODEL)
    return _embedding_service
