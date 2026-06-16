"""Retrieval-Augmented Generation (RAG) pipeline service."""

import asyncio
import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.embedding_service import get_embedding_service
from app.services.retrieval_service import get_retrieval_service
from app.utils.config import get_settings

logger = logging.getLogger(__name__)


class RAGService:
    """Pipeline that combines embeddings, retrieval, and LLM generation."""

    def __init__(
        self,
        google_api_key: Optional[str] = None,
        google_model: Optional[str] = None,
        default_top_k: int = 5,
    ):
        settings = get_settings()
        self.google_api_key = google_api_key or settings.GOOGLE_API_KEY or os.environ.get("GOOGLE_API_KEY")
        self.google_model = google_model or settings.GOOGLE_LLM_MODEL
        self.default_top_k = default_top_k
        self.log_path = Path(settings.RAG_LOG_PATH)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize Google Generative AI client."""
        if not self.google_api_key:
            logger.warning("Google API key not configured for RAGService")
            return

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.google_api_key)
            self._client = genai
            logger.info("Google Generative AI client configured for RAGService")
        except ImportError:
            logger.error("google.generativeai package is not installed")
            self._client = None
        except Exception as exc:
            logger.error("Failed to initialize Google Generative AI client: %s", exc)
            self._client = None

    async def answer_query(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the RAG pipeline for a user query."""
        query = query.strip()
        if not query:
            raise ValueError("Query cannot be empty")
        if not session_id or not session_id.strip():
            raise ValueError("session_id is required")

        embedding_service = await get_embedding_service()
        retrieval_service = await get_retrieval_service()

        query_embedding = await embedding_service.embed_text(query)
        results = await retrieval_service.retrieve_similar(
            session_id=session_id.strip(),
            query_embedding=query_embedding,
            top_k=top_k or self.default_top_k,
            filters=filters,
            query_text=query,
            enhanced=True,
        )

        if not results:
            return {
                "answer": "No relevant code chunks found for your query.",
                "context": [],
                "model": "none",
                "tokens_used": 0,
            }

        context_chunks = [result["content"] for result in results]
        prompt = self._build_prompt(query, context_chunks)
        llm_result = await self._generate_with_google(prompt)

        answer_text = llm_result["answer"]
        retrieved_context = [
            {
                "chunk_id": result["chunk_id"],
                "content": result["content"],
                "metadata": result["metadata"],
                "distance": result.get("distance", 0.0),
            }
            for result in results
        ]

        log_entry = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "query": query,
            "retrieved_chunks": [
                {
                    "chunk_id": item["chunk_id"],
                    "metadata": item.get("metadata", {}),
                    "content": item["content"],
                }
                for item in retrieved_context
            ],
            "response": answer_text,
            "evaluation": {
                "response_length": len(answer_text),
                "retrieved_chunk_count": len(retrieved_context),
            },
        }
        self._write_log_entry(log_entry)

        return {
            "answer": answer_text,
            "context": retrieved_context,
            "model": llm_result["model"],
            "tokens_used": llm_result.get("tokens_used", 0),
        }

    def _build_prompt(self, query: str, context_chunks: List[str]) -> str:
        """Construct a concise, context-focused prompt."""
        header = (
            "You are a precise code assistant. Answer using only the provided code context. "
            "Do not guess or add information that is not present in the context."
        )

        context_parts = []
        for index, chunk in enumerate(context_chunks, start=1):
            context_parts.append(f"--- Context chunk {index} ---\n{chunk}")

        context_text = "\n\n".join(context_parts)

        return (
            f"{header}\n\n"
            f"{context_text}\n\n"
            f"Question: {query}\n\n"
            "Answer concisely based on the code above."
        )

    async def _generate_with_google(self, prompt: str) -> Dict[str, Any]:
        """Generate a response using Google Generative AI."""
        if self._client is None:
            logger.warning("Google client unavailable, falling back to mock response")
            return self._generate_mock_response(prompt)

        try:
            response = await asyncio.to_thread(self._request_google_completion, prompt)
            answer = self._parse_google_response(response)
            return {
                "answer": answer,
                "model": self.google_model,
                "tokens_used": self._extract_token_count(response),
            }
        except Exception as exc:
            logger.error("Google LLM request failed: %s", exc)
            return self._generate_mock_response(prompt)

    def _request_google_completion(self, prompt: str) -> Any:
        """Synchronous call to Google Chat Completion."""
        if self._client is None:
            raise RuntimeError("Google client is not initialized")

        return self._client.chat.completions.create(
            model=self.google_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful and precise code assistant. Answer only from the context provided. "
                        "Avoid speculation."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_output_tokens=512,
        )

    @staticmethod
    def _parse_google_response(response: Any) -> str:
        """Extract the generated answer from the Google AI response."""
        if response is None:
            return ""

        if hasattr(response, "candidates") and response.candidates:
            return response.candidates[0].content

        if hasattr(response, "output"):
            if isinstance(response.output, dict):
                return response.output.get("content", "")
            if isinstance(response.output, list) and response.output:
                return response.output[0].get("content", "")

        return str(response)

    @staticmethod
    def _extract_token_count(response: Any) -> int:
        """Try to extract a token count from the API response."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return 0
        return int(getattr(usage, "total_tokens", 0) or 0)

    def _write_log_entry(self, entry: Dict[str, Any]) -> None:
        """Persist one query log entry to JSONL."""
        try:
            with self.log_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.error("Failed to write RAG query log: %s", exc)

    @staticmethod
    def _generate_mock_response(prompt: str) -> Dict[str, Any]:
        """Fallback mock response when LLM is unavailable."""
        return {
            "answer": (
                "Based on the provided code context, the requested information is likely present in the retrieved chunks. "
                "In a production environment with Google LLM access, this would return a concise answer referencing the code above."
            ),
            "model": "mock-google-llm",
            "tokens_used": 0,
        }


_rag_service: Optional[RAGService] = None


async def get_rag_service(
    google_api_key: Optional[str] = None,
    google_model: Optional[str] = None,
    default_top_k: int = 5,
) -> RAGService:
    """Get or create the RAG pipeline service."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService(
            google_api_key=google_api_key,
            google_model=google_model,
            default_top_k=default_top_k,
        )
    return _rag_service
