"""
Web Search Service using Tavily AI Search API.

Provides web search functionality to augment LLM responses with
real-time search results from the internet.

Tavily is optimized for LLMs and RAG applications.
API Documentation: https://docs.tavily.com/
"""

from typing import Optional, List
from dataclasses import dataclass

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
        # 截斷過長的內容
        content = self.content[:700] if len(self.content) > 700 else self.content
        return f"[{index}] {self.title}\n{content}"


@dataclass
class WebSearchResponse:
    """Response from web search."""
    query: str
    results: List[SearchResult]
    answer: Optional[str] = None  # Tavily can provide AI-generated answer

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

        if self.api_key:
            logger.info(
                f"WebSearchService initialized with Tavily API, "
                f"max_results={self.max_results}"
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
        include_answer: bool = False,
    ) -> WebSearchResponse:
        """
        Perform a web search using Tavily API.

        Args:
            query: Search query string
            max_results: Override default max results (1-10)
            include_answer: Whether to include AI-generated answer

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
            logger.debug(f"Tavily search: '{query[:50]}...', max_results={num_results}")

            client = self._get_client()

            # Run search synchronously (Tavily client is sync)
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.search(
                    query=query.strip(),
                    max_results=num_results,
                    include_answer=include_answer,
                    search_depth="basic",  # Use basic to conserve API credits
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

            logger.info(
                f"Tavily search complete: query='{query[:30]}...', results={len(results)}"
            )

            return search_response

        except WebSearchError:
            raise
        except Exception as e:
            logger.error(f"Tavily search error: {e}", exc_info=True)
            raise WebSearchAPIError(f"Search failed: {str(e)}")


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
