"""Google Generative AI embedding service."""

import asyncio
import logging
import os
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_GOOGLE_EMBEDDING_MODEL = "textembedding-gecko@001"
DEFAULT_BATCH_SIZE = 16
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
INITIAL_RETRY_DELAY = 1.0


class GoogleEmbeddingService:
    """Generate embeddings using Google Generative AI."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = DEFAULT_GOOGLE_EMBEDDING_MODEL,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self.model_name = model_name
        self.batch_size = batch_size
        self._client = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Configure the Google Generative AI client."""
        if not self.api_key:
            logger.warning("Google API key is not configured. Embeddings requests will fail.")
            return

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai
            logger.info("Google Generative AI client configured for embeddings")
        except ImportError:
            logger.error("google.generativeai package is not installed")
            self._client = None
        except Exception as exc:
            logger.error("Failed to initialize Google Generative AI client: %s", exc)
            self._client = None

    async def embed_text(self, text: str) -> List[float]:
        """Generate a single embedding vector."""
        embeddings = await self.embed_batch([text])
        return embeddings[0] if embeddings else []

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of text chunks."""
        if not texts:
            return []

        if self._client is None:
            logger.warning("GoogleEmbeddingService is not available, returning empty embeddings")
            return [[] for _ in texts]

        results: List[List[float]] = []
        tasks = []

        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            tasks.append(self._embed_batch_with_retries(batch))

        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for batch_result in batch_results:
            if isinstance(batch_result, Exception):
                logger.error("Embedding batch failed: %s", batch_result)
                results.extend([[] for _ in range(self.batch_size)])
            else:
                results.extend(batch_result)

        return results[: len(texts)]

    async def _embed_batch_with_retries(self, texts: List[str]) -> List[List[float]]:
        """Retry a single embedding batch on transient failures."""
        attempt = 0
        delay = INITIAL_RETRY_DELAY

        while attempt < MAX_RETRIES:
            try:
                return await asyncio.to_thread(self._request_embeddings, texts)
            except Exception as exc:
                attempt += 1
                logger.warning(
                    "Embedding request failed (attempt %d/%d): %s",
                    attempt,
                    MAX_RETRIES,
                    exc,
                )
                if attempt >= MAX_RETRIES:
                    logger.error("Max retries reached for embedding request")
                    raise
                await asyncio.sleep(delay)
                delay *= RETRY_BACKOFF

        return [[] for _ in texts]

    def _request_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Synchronous request to the Google embedding API."""
        if self._client is None:
            raise RuntimeError("Google Generative AI client is not initialized")

        response = self._client.embeddings.create(
            model=self.model_name,
            input=texts,
        )

        return self._parse_response(response, len(texts))

    @staticmethod
    def _parse_response(response, expected_count: int) -> List[List[float]]:
        """Parse embeddings from the API response."""
        if response is None:
            raise ValueError("Empty response from embedding API")

        try:
            embeddings_data = getattr(response, 'data', None) or response
            if isinstance(embeddings_data, dict):
                embeddings_data = embeddings_data.get('data', [])

            results = []
            for item in embeddings_data:
                vector = item.get('embedding') if isinstance(item, dict) else getattr(item, 'embedding', None)
                if vector is None:
                    raise ValueError("Embedding vector missing from response item")
                results.append(list(vector))

            if len(results) != expected_count:
                logger.warning(
                    "Expected %d embeddings but received %d; padding with empty vectors",
                    expected_count,
                    len(results),
                )
                while len(results) < expected_count:
                    results.append([])

            return results
        except Exception as exc:
            raise ValueError(f"Failed to parse embedding response: {exc}")


# Module-level instance helper
_embedding_service: Optional[GoogleEmbeddingService] = None


def get_google_embedding_service(
    api_key: Optional[str] = None,
    model_name: str = DEFAULT_GOOGLE_EMBEDDING_MODEL,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> GoogleEmbeddingService:
    """Get or create the Google embedding service."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = GoogleEmbeddingService(
            api_key=api_key,
            model_name=model_name,
            batch_size=batch_size,
        )
    return _embedding_service
