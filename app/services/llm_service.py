
"""LLM service for generating responses using Google Gemini (per-request API key)."""

import logging
from typing import List, Dict, Any, Optional

import google.generativeai as genai

logger = logging.getLogger(__name__)


class LLMService:
    """Interface with Gemini using a user-supplied API key per request."""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.7,
    ):
        self.model = model
        self.temperature = temperature

    async def generate_response(
        self,
        query: str,
        context_chunks: List[str],
        api_key: str,
        system_prompt: str | None = None,
    ) -> Dict[str, Any]:
        """Generate response from Gemini using the caller's API key."""
        if not api_key or not api_key.strip():
            raise ValueError("Gemini API key is required")

        try:
            context = "\n\n".join(
                [f"```\n{chunk}\n```" for chunk in context_chunks]
            )

            if system_prompt is None:
                system_prompt = """
You are an expert code analysis assistant.

Analyze the provided code context carefully.
Answer accurately and concisely.
If the answer is not present in the context, clearly say so.
"""

            full_prompt = f"""
{system_prompt}

CODE CONTEXT:
{context}

USER QUESTION:
{query}
"""

            estimated_tokens = max(1, len(full_prompt) // 4)
            logger.info(
                "FINAL_CONTEXT_SENT_TO_LLM estimated_tokens=%d chunks=%d",
                estimated_tokens,
                len(context_chunks),
            )
            for i, chunk in enumerate(context_chunks):
                preview = chunk[:200].replace("\n", " ")
                logger.info("  LLM_CONTEXT_CHUNK[%d] preview=%s...", i, preview)

            genai.configure(api_key=api_key.strip())
            client = genai.GenerativeModel(self.model)

            response = client.generate_content(
                full_prompt,
                generation_config={
                    "temperature": self.temperature,
                    "max_output_tokens": 1000,
                },
            )

            answer = response.text if response.text else "No response generated."

            usage = getattr(response, "usage_metadata", None)
            tokens_used = 0
            if usage is not None:
                tokens_used = int(
                    getattr(usage, "total_token_count", 0)
                    or (
                        getattr(usage, "prompt_token_count", 0)
                        + getattr(usage, "candidates_token_count", 0)
                    )
                )

            logger.info("Gemini response generated successfully")

            return {
                "answer": answer,
                "model": self.model,
                "tokens_used": tokens_used,
                "provider": "google",
                "prompt_context_chars": len(context),
                "estimated_prompt_tokens": estimated_tokens,
            }

        except Exception as e:
            logger.error("Gemini generation failed: %s", e)
            return {
                "answer": f"LLM generation failed: {str(e)}",
                "model": self.model,
                "tokens_used": 0,
                "provider": "google",
            }


_llm_service: Optional[LLMService] = None


async def get_llm_service() -> LLMService:
    """Get LLM service instance (model settings only; API key is per-request)."""
    global _llm_service

    if _llm_service is None:
        from app.utils.config import get_settings

        settings = get_settings()
        _llm_service = LLMService(
            model=settings.LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE,
        )

    return _llm_service
