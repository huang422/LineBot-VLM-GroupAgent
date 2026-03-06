"""
Web Search Service using Tavily AI Search API.

Provides web search functionality to augment LLM responses with
real-time search results from the internet.

Tavily is optimized for LLMs and RAG applications.
API Documentation: https://docs.tavily.com/
"""

import asyncio
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime, timezone

from src.config import get_settings
from src.utils.logger import get_logger

logger = get_logger("services.web_search")

# Default settings
DEFAULT_MAX_RESULTS = 3


class WebSearchError(Exception):
    """Base exception for web search errors."""
    pass


class WebSearchConnectionError(WebSearchError):
    """Raised when search API is unreachable."""
    pass


class WebSearchAPIError(WebSearchError):
    """Raised when search API returns an error."""
    pass


@dataclass
class SearchResult:
    """A single search result."""
    title: str
    url: str
    content: str
    score: float = 0.0

    def to_text(self, index: int) -> str:
        """Format as concise text for LLM context."""
        content = self.content[:2000] if len(self.content) > 2000 else self.content
        return f"[{index}] {self.title}\nURL: {self.url}\n{content}"


@dataclass
class ExtractResult:
    """Result from URL content extraction."""
    url: str
    content: str

    def to_text(self) -> str:
        """Format extracted content for LLM context."""
        content = self.content[:10000] if len(self.content) > 10000 else self.content
        return f"URL: {self.url}\n{content}"


@dataclass
class ExtractResponse:
    """Response from URL content extraction."""
    results: List[ExtractResult]
    failed_urls: List[str]

    @property
    def has_results(self) -> bool:
        return len(self.results) > 0

    def to_context_text(self) -> str:
        """Format extracted content as context text for LLM."""
        if not self.results:
            return ""
        parts = []
        for result in self.results:
            parts.append(result.to_text())
        return "\n\n---\n\n".join(parts)


@dataclass
class WebSearchResponse:
    """Response from web search."""
    query: str
    results: List[SearchResult]
    answer: Optional[str] = None  # Tavily AI-generated answer

    @property
    def has_results(self) -> bool:
        """Check if there are any results."""
        return len(self.results) > 0

    def to_context_text(self) -> str:
        """
        Format search results as concise context text for LLM.

        Returns:
            Formatted string with all search results
        """
        if not self.results:
            return ""

        parts = []

        # Include Tavily AI answer at the top if available
        if self.answer:
            parts.append(f"AI Summary: {self.answer}")

        for i, result in enumerate(self.results, 1):
            parts.append(result.to_text(i))

        return "\n\n".join(parts)


class WebSearchService:
    """
    Service for web search using Tavily AI.

    Provides search functionality optimized for LLM and RAG applications.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        max_results: int = DEFAULT_MAX_RESULTS,
    ):
        """
        Initialize web search service.

        Args:
            api_key: Tavily API key (defaults to settings)
            max_results: Default number of results (1-10)
        """
        settings = get_settings()
        self.api_key = api_key or settings.tavily_api_key
        self.max_results = max(1, min(10, max_results))
        self._client = None

        # Monthly quota tracking (resets each month automatically)
        self._monthly_quota = settings.web_search_monthly_quota
        self._month_search_count = 0
        self._current_month = datetime.now(timezone.utc).strftime("%Y-%m")

        if self.api_key:
            logger.info(
                f"WebSearchService initialized with Tavily API, "
                f"max_results={self.max_results}, "
                f"monthly_quota={self._monthly_quota}"
            )
        else:
            logger.warning(
                "WebSearchService: TAVILY_API_KEY not configured, "
                "web search will be disabled"
            )

    @property
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    def _check_and_reset_month(self) -> None:
        """Reset monthly counter if we've entered a new month."""
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        if current_month != self._current_month:
            logger.info(
                f"Monthly quota reset: {self._current_month} -> {current_month}, "
                f"last month used {self._month_search_count}/{self._monthly_quota}"
            )
            self._current_month = current_month
            self._month_search_count = 0

    @property
    def quota_remaining(self) -> int:
        """Get remaining search quota for this month."""
        self._check_and_reset_month()
        return max(0, self._monthly_quota - self._month_search_count)

    @property
    def is_quota_available(self) -> bool:
        """Check if there's remaining search quota."""
        return self.quota_remaining > 0

    def get_quota_stats(self) -> dict:
        """Get quota statistics for monitoring."""
        self._check_and_reset_month()
        return {
            "month": self._current_month,
            "used": self._month_search_count,
            "quota": self._monthly_quota,
            "remaining": self.quota_remaining,
        }

    def _get_client(self):
        """Get or create Tavily client (lazy initialization)."""
        if self._client is None and self.api_key:
            try:
                from tavily import TavilyClient
                self._client = TavilyClient(api_key=self.api_key)
            except ImportError:
                logger.error("tavily-python package not installed")
                raise WebSearchError(
                    "tavily-python package not installed. "
                    "Run: pip install tavily-python"
                )
        return self._client

    async def close(self) -> None:
        """Close the client."""
        self._client = None

    async def search(
        self,
        query: str,
        max_results: Optional[int] = None,
        include_answer: bool = True,
        search_depth: str = "basic",
    ) -> WebSearchResponse:
        """
        Perform a web search using Tavily API.

        Args:
            query: Search query string
            max_results: Override default max results (1-10)
            include_answer: Whether to include AI-generated answer
            search_depth: "basic" (1 credit) or "advanced" (2 credits, more precise)

        Returns:
            WebSearchResponse with search results

        Raises:
            WebSearchError: If search fails
        """
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty")

        if not self.is_configured:
            raise WebSearchError("Tavily API key not configured")

        # Use provided values or defaults
        num_results = max_results or self.max_results
        num_results = max(1, min(10, num_results))

        try:
            logger.debug(
                f"Tavily search: '{query[:50]}...', max_results={num_results}, "
                f"depth={search_depth}, include_answer={include_answer}"
            )

            client = self._get_client()

            # Run search synchronously (Tavily client is sync)
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.search(
                    query=query.strip(),
                    max_results=num_results,
                    include_answer=include_answer,
                    search_depth=search_depth,
                )
            )

            # Parse results
            results = []
            for item in response.get("results", []):
                result = SearchResult(
                    title=item.get("title", "No title"),
                    url=item.get("url", ""),
                    content=item.get("content", ""),
                    score=item.get("score", 0.0),
                )
                results.append(result)

            search_response = WebSearchResponse(
                query=query,
                results=results,
                answer=response.get("answer") if include_answer else None,
            )

            # Increment monthly counter after successful search
            self._month_search_count += 1

            logger.info(
                f"Tavily search complete: query='{query[:30]}...', results={len(results)}, "
                f"depth={search_depth}, quota={self.quota_remaining}/{self._monthly_quota} remaining"
            )

            return search_response

        except WebSearchError:
            raise
        except Exception as e:
            error_str = str(e)
            # Tavily returns specific errors for quota exceeded
            if "429" in error_str or "432" in error_str or "limit" in error_str.lower():
                logger.warning(f"Tavily API quota exceeded: {e}")
                raise WebSearchError(f"搜尋 API 額度已用完: {error_str}")
            logger.error(f"Tavily search error: {e}", exc_info=True)
            raise WebSearchAPIError(f"Search failed: {error_str}")

    async def extract(
        self,
        urls: List[str],
    ) -> ExtractResponse:
        """
        Extract content from URLs using Tavily Extract API.

        Args:
            urls: List of URLs to extract content from (max 20)

        Returns:
            ExtractResponse with extracted content

        Raises:
            WebSearchError: If extraction fails
        """
        if not urls:
            raise ValueError("URL list cannot be empty")

        if not self.is_configured:
            raise WebSearchError("Tavily API key not configured")

        # Limit to 5 URLs to conserve credits
        urls = urls[:5]

        try:
            logger.info(f"Tavily extract: {len(urls)} URLs")

            client = self._get_client()

            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.extract(urls=urls)
            )

            results = []
            for item in response.get("results", []):
                raw_content = item.get("raw_content", "")
                if raw_content:
                    results.append(ExtractResult(
                        url=item.get("url", ""),
                        content=raw_content,
                    ))

            failed_urls = []
            for item in response.get("failed_results", []):
                failed_url = item.get("url", "")
                failed_error = item.get("error", "unknown")
                failed_urls.append(failed_url)
                logger.warning(f"Tavily extract failed for URL: {failed_url}, error: {failed_error}")

            # Increment monthly counter
            self._month_search_count += 1

            logger.info(
                f"Tavily extract complete: {len(results)} success, {len(failed_urls)} failed, "
                f"quota={self.quota_remaining}/{self._monthly_quota} remaining"
            )

            return ExtractResponse(results=results, failed_urls=failed_urls)

        except WebSearchError:
            raise
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "432" in error_str or "limit" in error_str.lower():
                logger.warning(f"Tavily API quota exceeded: {e}")
                raise WebSearchError(f"搜尋 API 額度已用完: {error_str}")
            logger.error(f"Tavily extract error: {e}", exc_info=True)
            raise WebSearchAPIError(f"Extract failed: {error_str}")


# Global singleton instance
_web_search_service: Optional[WebSearchService] = None


def get_web_search_service() -> WebSearchService:
    """Get or create the global WebSearchService instance."""
    global _web_search_service
    if _web_search_service is None:
        _web_search_service = WebSearchService()
    return _web_search_service


async def close_web_search_service() -> None:
    """Close the global WebSearchService instance."""
    global _web_search_service
    if _web_search_service:
        await _web_search_service.close()
        _web_search_service = None
