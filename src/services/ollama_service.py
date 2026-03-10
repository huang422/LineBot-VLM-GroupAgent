"""
Ollama Service for local VLM integration.

Handles communication with the locally deployed Ollama API
for text and multimodal (vision) inference requests.

Supports streaming with <think> tag filtering for reasoning models
(e.g., qwen3.5) to strip internal reasoning and return only the
final response content.
"""

import asyncio
import json
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx

from opencc import OpenCC

from src.config import get_settings
from src.utils.logger import get_logger

# Simplified → Traditional Chinese converter (singleton)
_s2t = OpenCC('s2t')

logger = get_logger("services.ollama")

# Timeout settings
CONNECT_TIMEOUT = 10.0  # seconds
READ_TIMEOUT = 300.0    # seconds (reasoning models may think longer)

# Triggers for /think mode. Stored as single string — do NOT convert to a multi-line list,
# as linters will auto-expand it with unwanted keywords.
_COMPLEX_QUERY_TRIGGERS: frozenset = frozenset(
    "/think,分析,優缺點,比較,比較優缺點,設計方案,架構設計,詳細,詳細解釋,深入分析,說明,完整說明,深度分析,解釋,請問,摘要,什麼,怎麼辦,請,搜尋".split(",")
)


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
    using the configured Ollama model (set OLLAMA_MODEL in .env).

    Attributes:
        base_url: Ollama API base URL (e.g., http://localhost:11434)
        model: Model name (e.g., qwen3.5:35b-a3b for quality or qwen3.5:9b for speed)
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
    
    @staticmethod
    def _get_time_prefix() -> str:
        """Get current Taiwan time as a short prefix for system prompt."""
        tw = timezone(timedelta(hours=8))
        now = datetime.now(tw)
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        return f"現在時間：{now.strftime('%Y-%m-%d')} 星期{weekdays[now.weekday()]} {now.strftime('%H:%M')}\n"

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
                timeout=10.0
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
        extracted_content: Optional[str] = None,
    ) -> str:
        """
        Generate a response from the LLM using streaming with smart think routing.

        Automatically decides between /think and /no_think modes:
        - /no_think (default, ~80% of queries): Fast, 30-60s with 35b model
        - /think (complex queries only): Slower but deeper reasoning, 60-200s+

        The think content is always filtered from the output regardless of mode.

        Args:
            prompt: User question/prompt
            system_prompt: System prompt for behavior control
            image_base64: Optional base64-encoded image for vision tasks
            context_text: Optional text context (e.g., quoted message)
            conversation_history: Optional conversation history for context
            web_search_results: Optional web search results for augmented responses
            extracted_content: Optional extracted webpage content from URLs

        Returns:
            Generated response text (with thinking content stripped)

        Raises:
            OllamaConnectionError: If service is unreachable
            OllamaInferenceError: If inference fails
        """
        settings = get_settings()
        is_multimodal = image_base64 is not None
        time_prefix = self._get_time_prefix()

        logger.info(f"Generating response for: '{prompt[:50]}...' (multimodal={is_multimodal})")

        if is_multimodal:
            # Image requests: lightweight prompt, thinking disabled.
            image_prompt = prompt if prompt else "describe this image"
            if context_text:
                image_prompt += f"\n\nReferenced message:\n{context_text}"

            payload = {
                "model": self.model,
                "prompt": image_prompt,
                "stream": True,
                "think": False,  # Ollama API param — disables thinking for this request
                "system": f"{time_prefix}你是圖片分析助手。直接描述和回答，不需要思考過程。必須使用繁體中文回覆，禁止使用簡體中文。",
                "images": [image_base64],
                "options": {
                    "num_predict": settings.ollama_num_predict,
                    "temperature": 0.5,
                    "num_ctx": settings.ollama_num_ctx,
                }
            }
            logger.debug("Multimodal request with image (thinking disabled)")
        else:
            # Text-only: auto-select think mode via Ollama API "think" parameter.
            # Complex keywords → think=True (full budget, 200s timeout then retry).
            # Everything else → think=False (faster, but still 30-60s with 35b model).
            is_complex = any(kw in prompt for kw in _COMPLEX_QUERY_TRIGGERS)
            if is_complex:
                enable_think = True
                effective_num_predict = settings.ollama_num_predict
                logger.debug("Think mode: think=True triggered by keyword in prompt")
            else:
                enable_think = False
                effective_num_predict = 1024
                logger.debug("Think mode: think=False (fast path, num_predict=1024)")

            full_prompt = self._build_prompt(
                prompt, context_text, conversation_history,
                web_search_results, extracted_content
            )
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": True,
                "think": enable_think,  # Ollama API param — controls thinking mode
                "system": f"{time_prefix}{system_prompt}" if system_prompt else time_prefix,
                "options": {
                    "num_predict": effective_num_predict,
                    "temperature": settings.ollama_temperature,
                    "num_ctx": settings.ollama_num_ctx,
                }
            }

        try:
            start_time = time.monotonic()

            # Text requests: 300s think timeout, then retry with think=False (90s).
            # Full pipeline budget: classify(≤30s) + search(≤20s) + think(300s) + sleep(2s) + retry(90s) = 442s < 480s queue limit.
            # Image requests: rely on httpx-level timeout (300s), no retry needed.
            _THINKING_TIMEOUT = 300.0
            _RETRY_TIMEOUT = 90.0  # Max time for think=False retry (300+2+90=392, plus upstream steps ≤ 480s queue limit)
            timed_out = False

            if not is_multimodal:
                try:
                    response_text, think_text, stats = await asyncio.wait_for(
                        self._stream_ollama(payload),
                        timeout=_THINKING_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    elapsed_so_far = time.monotonic() - start_time
                    logger.warning(
                        f"Thinking timeout after {elapsed_so_far:.1f}s, retrying with /no_think"
                    )
                    timed_out = True
                    response_text, think_text, stats = "", "", {"done_reason": "timeout"}
            else:
                response_text, think_text, stats = await self._stream_ollama(payload)

            elapsed = time.monotonic() - start_time
            logger.info(
                f"Generation complete",
                extra={
                    "duration_seconds": round(elapsed, 2),
                    "response_length": len(response_text),
                    "think_length": len(think_text),
                    "total_tokens": stats.get("total_tokens", 0),
                    "done_reason": stats.get("done_reason", "unknown"),
                }
            )

            if response_text.strip():
                return _s2t.convert(response_text.strip())

            # Empty response: timeout OR token exhaustion (all tokens used on thinking).
            # Retry with /no_think for a fast direct answer.
            if not is_multimodal:
                reason = "timeout" if timed_out else f"token_exhaustion(done_reason={stats.get('done_reason')})"
                logger.warning(f"Empty response ({reason}), retrying with /no_think")

                # After a timeout, Ollama server may still be generating.
                # Brief pause to let it detect the dropped connection before starting a new request.
                if timed_out:
                    await asyncio.sleep(2.0)

                no_think_prompt = self._build_prompt(
                    prompt, context_text, conversation_history,
                    web_search_results, extracted_content,
                )
                retry_payload = {
                    "model": self.model,
                    "prompt": no_think_prompt,
                    "stream": True,
                    "think": False,  # Ollama API param — force no thinking on retry
                    "system": f"{time_prefix}{system_prompt}" if system_prompt else time_prefix,
                    "options": {
                        "num_predict": 4096,  # Retry: enough budget for a full answer, capped by _RETRY_TIMEOUT
                        "temperature": 0.7,
                        "num_ctx": settings.ollama_num_ctx,
                    }
                }
                try:
                    retry_text, _, _ = await asyncio.wait_for(
                        self._stream_ollama(retry_payload),
                        timeout=_RETRY_TIMEOUT,
                    )
                    if retry_text.strip():
                        logger.info("Retry with think=False succeeded")
                        return _s2t.convert(retry_text.strip())
                    logger.error("Retry with think=False returned empty response")
                except asyncio.TimeoutError:
                    logger.error(f"Retry with think=False timed out after {_RETRY_TIMEOUT}s")
                except Exception as retry_err:
                    logger.error(f"Retry with think=False also failed: {retry_err}")

            # Truly nothing produced
            raise OllamaInferenceError("Model produced empty response after all attempts")

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

    async def _stream_ollama(
        self,
        payload: dict,
    ) -> tuple[str, str, dict]:
        """
        Stream response from Ollama, reading both 'response' and 'thinking' fields.

        Ollama natively separates thinking content (in 'thinking' field) from
        the actual response (in 'response' field) for reasoning models like qwen3.5.
        No manual <think> tag parsing needed.

        Args:
            payload: Ollama API request payload (must have stream=True)

        Returns:
            Tuple of (response_text, think_text, stats_dict)
        """
        response_text = ""
        think_text = ""
        total_tokens = 0
        done_reason = ""

        async with self.client.stream(
            "POST",
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=httpx.Timeout(
                connect=CONNECT_TIMEOUT,
                read=READ_TIMEOUT,
                write=30.0,
                pool=10.0,
            ),
        ) as stream:
            if stream.status_code != 200:
                error_body = await stream.aread()
                raise OllamaInferenceError(
                    f"Ollama returned status {stream.status_code}: {error_body[:200]}"
                )

            async for line in stream.aiter_lines():
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Ollama separates thinking and response into two fields
                thinking_token = data.get("thinking", "")
                response_token = data.get("response", "")

                if thinking_token:
                    think_text += thinking_token
                    total_tokens += 1

                if response_token:
                    response_text += response_token
                    total_tokens += 1

                if data.get("done"):
                    done_reason = data.get("done_reason", "")
                    break

        # Final cleanup: remove any residual think tags (fallback for older Ollama)
        response_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL)
        response_text = re.sub(r"</?think>", "", response_text)

        stats = {"total_tokens": total_tokens, "done_reason": done_reason}

        if think_text:
            logger.debug(f"Think content: {len(think_text)} chars")

        return response_text, think_text, stats
    
    async def classify_needs_search(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> bool:
        """
        Determine if a question needs web search.

        Two-stage approach:
        1. Fast path: keyword matching for obvious time-sensitive queries
        2. Slow path: lightweight LLM classification with few-shot examples

        Args:
            prompt: User's question
            system_prompt: Optional system prompt (unused, kept for interface consistency)

        Returns:
            True if the question likely needs web search
        """
        # === Stage 1: Fast keyword matching (no LLM call needed) ===
        time_sensitive_keywords = [
            # 時間相關
            "今天", "明天", "昨天", "今晚", "今年", "這週", "本週", "下週",
            "最新", "最近", "現在", "目前", "即時",
            # 即時資訊類
            "新聞", "天氣", "氣溫", "股價", "匯率", "幣價", "油價",
            "比賽", "比分", "結果", "成績", "排名", "戰績",
            # 事件查詢
            "發生什麼", "怎麼了", "出了什麼事",
            # 年份（需要即時資訊的高機率指標）
            "2024", "2025", "2026",
            # English keywords
            "today", "tomorrow", "yesterday", "latest", "recent", "current",
            "news", "weather", "price", "score", "ranking",
        ]
        prompt_lower = prompt.lower()
        for kw in time_sensitive_keywords:
            if kw in prompt_lower:
                logger.info(f"Auto search triggered by keyword: '{kw}'")
                return True

        # === Stage 2: LLM classification with few-shot examples ===
        classify_system = (
            "你是一個搜尋判斷助手。你的唯一任務是判斷使用者的問題是否需要即時網路搜尋才能正確回答。\n"
            "只回答 YES 或 NO，不要輸出任何其他內容。"
        )

        classify_prompt = (
            "## 判斷規則\n"
            "需要搜尋（YES）的情況：\n"
            "- 問題涉及即時資訊（天氣、新聞、股價、比賽結果）\n"
            "- 問題涉及特定時間點的事實（今天、最近、最新）\n"
            "- 問題涉及你訓練資料可能過時的資訊（新產品、新政策、近期事件）\n"
            "- 問題需要查證具體事實（某個地址、營業時間、票價）\n\n"
            "不需要搜尋（NO）的情況：\n"
            "- 一般知識問答（程式語言語法、數學計算、歷史常識）\n"
            "- 主觀意見或建議（該買什麼、怎麼選擇）\n"
            "- 閒聊、打招呼、情緒表達\n"
            "- 圖片分析、翻譯、文字處理\n"
            "- 技術問題排查（Bug、錯誤訊息分析）\n\n"
            "## 範例\n"
            "問題：台北現在幾度？ → YES\n"
            "問題：Python怎麼寫迴圈？ → NO\n"
            "問題：iPhone 16 Pro 價格多少？ → YES\n"
            "問題：幫我解釋這段程式碼 → NO\n"
            "問題：台積電今天收盤價？ → YES\n"
            "問題：推薦一下好吃的餐廳 → YES\n"
            "問題：什麼是機器學習？ → NO\n"
            "問題：埃及金字塔有多高？ → NO\n\n"
            f"問題：{prompt}\n"
            "回答："
        )

        payload = {
            "model": self.model,
            "prompt": classify_prompt,
            "system": classify_system,
            "stream": False,
            "think": False,  # Ollama API param — no thinking needed for YES/NO classification
            "options": {
                "num_predict": 10,
                "temperature": 0,
            }
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=httpx.Timeout(connect=CONNECT_TIMEOUT, read=30.0, write=10.0, pool=5.0),
            )

            if response.status_code == 200:
                result = response.json()
                # Ollama may put answer in 'response' or 'thinking' field
                raw_response = result.get("response", "").strip()
                raw_thinking = result.get("thinking", "").strip()
                # Combine both fields to find YES/NO
                combined = f"{raw_response} {raw_thinking}".upper()
                needs_search = "YES" in combined
                logger.info(
                    f"Search classification: response='{raw_response[:30]}' "
                    f"thinking='{raw_thinking[:30]}' -> needs_search={needs_search}"
                )
                return needs_search

        except Exception as e:
            logger.warning(f"Search classification failed, defaulting to no search: {e}")

        return False
    
    def _build_prompt(
        self,
        prompt: str,
        context_text: Optional[str] = None,
        conversation_history: Optional[str] = None,
        web_search_results: Optional[str] = None,
        extracted_content: Optional[str] = None,
    ) -> str:
        """
        Build the full prompt including context, conversation history, web search, and extracted content.

        The prompt is structured as:
        1. User's current message (User message)
        2. Referenced message (if exists)
        3. Recent conversation history
        4. Extracted webpage content (if exists)
        5. Web search results (if exists)

        Args:
            prompt: User's question
            context_text: Optional context from quoted message
            conversation_history: Optional recent conversation history
            web_search_results: Optional web search results
            extracted_content: Optional extracted webpage content

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

        # 4. Add extracted webpage content (if available)
        if extracted_content:
            parts.append("")
            parts.append("Extracted webpage content:")
            parts.append("---")
            parts.append(extracted_content)
            parts.append("---")

        # 5. Add web search results (if available)
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
