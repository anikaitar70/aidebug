
"""LLM service for generating responses using Google Gemini"""

import logging
from typing import List, Dict, Any

import google.generativeai as genai

logger = logging.getLogger(__name__)


class LLMService:
    """Interface with Gemini for generating responses"""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.7
    ):
        self.model = model
        self.temperature = temperature
        self._client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize Gemini client"""
        try:
            from app.utils.config import get_settings

            settings = get_settings()

            if not settings.GOOGLE_API_KEY:
                raise ValueError("GOOGLE_API_KEY is missing")

            genai.configure(api_key=settings.GOOGLE_API_KEY)

            self._client = genai.GenerativeModel(self.model)

            logger.info(f"Initialized Gemini client: {self.model}")

        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            self._client = None

    async def generate_response(
        self,
        query: str,
        context_chunks: List[str],
        system_prompt: str | None = None
    ) -> Dict[str, Any]:
        """
        Generate response from Gemini
        """

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
            logger.info("FINAL_CONTEXT_SENT_TO_LLM estimated_tokens=%d chunks=%d", estimated_tokens, len(context_chunks))
            for i, chunk in enumerate(context_chunks):
                preview = chunk[:200].replace("\n", " ")
                logger.info("  LLM_CONTEXT_CHUNK[%d] preview=%s...", i, preview)

            if self._client is None:
                raise ValueError("Gemini client not initialized")

            response = self._client.generate_content(
                full_prompt,
                generation_config={
                    "temperature": self.temperature,
                    "max_output_tokens": 1000,
                }
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
            logger.error(f"Gemini generation failed: {e}")

            return {
                "answer": f"LLM generation failed: {str(e)}",
                "model": self.model,
                "tokens_used": 0,
                "provider": "google"
            }


# Global service instance
_llm_service: LLMService | None = None


async def get_llm_service() -> LLMService:
    """Get LLM service instance"""

    global _llm_service

    if _llm_service is None:
        from app.utils.config import get_settings

        settings = get_settings()

        _llm_service = LLMService(
            model=settings.LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE
        )

    return _llm_service

