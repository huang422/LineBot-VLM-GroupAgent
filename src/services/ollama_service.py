"""
Ollama Service for local VLM integration.

Handles communication with the locally deployed Ollama API
for text and multimodal (vision) inference requests.
"""

import asyncio
from typing import Optional, AsyncGenerator
import httpx

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger("services.ollama")

# Timeout settings
CONNECT_TIMEOUT = 10.0  # seconds
READ_TIMEOUT = 120.0    # seconds (LLM inference can be slow)


class OllamaError(Exception):
    """Base exception for Ollama service errors."""
    pass


class OllamaConnectionError(OllamaError):
    """Raised when Ollama service is unreachable."""
    pass


class OllamaInferenceError(OllamaError):
    """Raised when inference fails."""
    pass


class OllamaService:
    """
    Service for interacting with Ollama API.
    
    Supports both text-only and multimodal (image + text) requests
    using the gemma3:4b VLM model.
    
    Attributes:
        base_url: Ollama API base URL (e.g., http://localhost:11434)
        model: Model name (e.g., gemma3:4b)
        client: Async HTTP client for API calls
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize Ollama service.
        
        Args:
            base_url: Override config base URL
            model: Override config model name
        """
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=CONNECT_TIMEOUT,
                read=READ_TIMEOUT,
                write=30.0,
                pool=10.0,
            )
        )
        
        logger.info(
            f"OllamaService initialized: {self.base_url}, model={self.model}"
        )
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
    
    async def health_check(self) -> bool:
        """
        Check if Ollama service is available.
        
        Returns:
            True if service is responding, False otherwise
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/api/tags",
                timeout=5.0
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        image_base64: Optional[str] = None,
        context_text: Optional[str] = None,
        conversation_history: Optional[str] = None,
        web_search_results: Optional[str] = None,
    ) -> str:
        """
        Generate a response from the LLM.

        Args:
            prompt: User question/prompt
            system_prompt: System prompt for behavior control
            image_base64: Optional base64-encoded image for vision tasks
            context_text: Optional text context (e.g., quoted message)
            conversation_history: Optional conversation history for context
            web_search_results: Optional web search results for augmented responses

        Returns:
            Generated response text

        Raises:
            OllamaConnectionError: If service is unreachable
            OllamaInferenceError: If inference fails
        """
        # Build the full prompt with context
        full_prompt = self._build_prompt(prompt, context_text, conversation_history, web_search_results)
        
        # Build request payload
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,  # Get complete response
            "options": {
                "num_predict": 1024,  # Max tokens to generate
                "temperature": 0.7,
            }
        }
        
        # Add system prompt if provided
        if system_prompt:
            payload["system"] = system_prompt
        
        # Add image for multimodal request
        if image_base64:
            payload["images"] = [image_base64]
            logger.debug("Multimodal request with image")
        
        try:
            logger.debug(
                f"Sending request to Ollama",
                extra={"prompt_length": len(full_prompt), "has_image": bool(image_base64)}
            )
            
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            
            if response.status_code != 200:
                error_text = response.text[:200]
                logger.error(f"Ollama API error: {response.status_code} - {error_text}")
                raise OllamaInferenceError(
                    f"Ollama returned status {response.status_code}"
                )
            
            result = response.json()
            generated_text = result.get("response", "").strip()
            
            # Log generation stats
            eval_count = result.get("eval_count", 0)
            total_duration = result.get("total_duration", 0) / 1e9  # nanoseconds to seconds
            
            logger.info(
                f"Generation complete",
                extra={
                    "tokens": eval_count,
                    "duration_seconds": round(total_duration, 2),
                    "response_length": len(generated_text),
                }
            )
            
            return generated_text
            
        except httpx.ConnectError as e:
            logger.error(f"Failed to connect to Ollama: {e}")
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. Is the service running?"
            )
        except httpx.TimeoutException as e:
            logger.error(f"Ollama request timed out: {e}")
            raise OllamaInferenceError(
                "Request timed out. The model may be overloaded or the prompt too complex."
            )
        except Exception as e:
            if isinstance(e, OllamaError):
                raise
            logger.error(f"Unexpected Ollama error: {e}", exc_info=True)
            raise OllamaInferenceError(f"Inference failed: {str(e)}")
    
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        image_base64: Optional[str] = None,
        context_text: Optional[str] = None,
        conversation_history: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response from the LLM.

        Yields tokens as they are generated for real-time output.

        Args:
            prompt: User question/prompt
            system_prompt: System prompt for behavior control
            image_base64: Optional base64-encoded image
            context_text: Optional text context
            conversation_history: Optional conversation history for context

        Yields:
            Generated text chunks
        """
        full_prompt = self._build_prompt(prompt, context_text, conversation_history)
        
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": True,
            "options": {
                "num_predict": 1024,
                "temperature": 0.7,
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt
        
        if image_base64:
            payload["images"] = [image_base64]
        
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=payload,
            ) as response:
                if response.status_code != 200:
                    raise OllamaInferenceError(f"Ollama returned {response.status_code}")
                
                async for line in response.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        if token := data.get("response"):
                            yield token
                        if data.get("done"):
                            break
                            
        except httpx.ConnectError:
            raise OllamaConnectionError(f"Cannot connect to Ollama at {self.base_url}")
        except Exception as e:
            if isinstance(e, OllamaError):
                raise
            raise OllamaInferenceError(f"Stream failed: {str(e)}")
    
    def _build_prompt(
        self,
        prompt: str,
        context_text: Optional[str] = None,
        conversation_history: Optional[str] = None,
        web_search_results: Optional[str] = None,
    ) -> str:
        """
        Build the full prompt including context, conversation history, and web search.

        The prompt is structured as:
        1. User's current message (User message)
        2. Referenced message (if exists)
        3. Recent conversation history
        4. Web search results (if exists)

        Args:
            prompt: User's question
            context_text: Optional context from quoted message
            conversation_history: Optional recent conversation history
            web_search_results: Optional web search results

        Returns:
            Combined prompt string
        """
        parts = []

        # 1. User's current message
        parts.append(f"User's question: {prompt}")

        # 2. Add quoted message context (if available)
        if context_text:
            parts.append("")
            parts.append("Referenced message:")
            parts.append("---")
            parts.append(context_text)
            parts.append("---")

        # 3. Add conversation history (if available)
        if conversation_history:
            parts.append("")
            parts.append("Recent conversation:")
            parts.append("---")
            parts.append(conversation_history)
            parts.append("---")

        # 4. Add web search results (if available)
        if web_search_results:
            parts.append("")
            parts.append("web search:")
            parts.append(web_search_results)

        return "\n".join(parts)


# Global singleton instance
_ollama_service: Optional[OllamaService] = None


def get_ollama_service() -> OllamaService:
    """Get or create the global OllamaService instance."""
    global _ollama_service
    if _ollama_service is None:
        _ollama_service = OllamaService()
    return _ollama_service


async def close_ollama_service() -> None:
    """Close the global OllamaService instance."""
    global _ollama_service
    if _ollama_service:
        await _ollama_service.close()
        _ollama_service = None
