"""Web search tool — Tavily API with DuckDuckGo fallback."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlparse

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.security.ssrf import check_ssrf
from openjarvis.tools._stubs import BaseTool, ToolSpec

logger = logging.getLogger(__name__)
_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


@ToolRegistry.register("web_search")
class WebSearchTool(BaseTool):
    """Search the web via Tavily API."""

    tool_id = "web_search"
    is_local = False

    def __init__(self, api_key: str | None = None, max_results: int = 5):
        self._api_key = api_key or os.environ.get("TAVILY_API_KEY")
        self._max_results = max_results

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="web_search",
            description=(
                "Search the web for current information."
                " Returns relevant search results."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results to return.",
                    },
                },
                "required": ["query"],
            },
            category="search",
            risk_level="medium",
            metadata={
                "requires_api_key": "TAVILY_API_KEY",
                "fallback": "duckduckgo",
                "risk_level": "medium",
            },
        )

    @staticmethod
    def _is_url(text: str) -> bool:
        """Check if text is a URL."""
        stripped = text.strip()
        return stripped.startswith("http://") or stripped.startswith("https://")

    @staticmethod
    def _extract_url(text: str) -> str | None:
        """Extract the first URL from text, if any."""
        import re as _re

        match = _re.search(r"https?://[^\s,;\"'<>]+", text)
        return match.group(0).rstrip(".,;)") if match else None

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Convert known PDF URLs to their HTML equivalents."""
        import re as _re

        # arxiv: /pdf/ID → /abs/ID (abstract page with full metadata)
        m = _re.match(r"(https?://arxiv\.org)/pdf/(.+?)(?:\.pdf)?$", url)
        if m:
            return f"{m.group(1)}/abs/{m.group(2)}"
        return url

    @staticmethod
    def _fetch_url(url: str, max_chars: int = 6000) -> str:
        """Fetch a URL and return extracted text content."""
        import re as _re

        import httpx

        url = WebSearchTool._normalize_url(url)
        ssrf_error = check_ssrf(url)
        if ssrf_error:
            raise ValueError(ssrf_error)
        max_redirects = 20
        sec = None
        try:
            from openjarvis.core.config import load_config

            sec = load_config().security
        except Exception:
            sec = None

        if sec is not None and sec.web_risk_policy_enabled:
            host = (urlparse(url).hostname or "").lower()
            allowlist = {
                d.strip().lower()
                for d in (sec.web_allowlist_domains or "").split(",")
                if d.strip()
            }
            denylist = {
                d.strip().lower()
                for d in (sec.web_denylist_domains or "").split(",")
                if d.strip()
            }
            if host in denylist or (allowlist and host not in allowlist):
                raise ValueError(
                    f"Blocked by web policy for domain: {host or '<unknown>'}"
                )
            max_redirects = max(0, int(sec.web_max_redirects))
        with httpx.Client(
            follow_redirects=max_redirects > 0,
            max_redirects=max_redirects,
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; OpenJarvis/1.0; +https://github.com/openjarvis)"
            },
        ) as client:
            resp = client.get(url.strip())
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "application/pdf" in content_type:
            return (
                "[This URL points to a PDF file which"
                f" cannot be read directly. URL: {url}]"
            )
        html = resp.text
        # Strip script/style tags and their contents
        html = _re.sub(
            r"<(script|style)[^>]*>.*?</\1>",
            "",
            html,
            flags=_re.DOTALL | _re.IGNORECASE,
        )
        # Strip HTML tags
        text = _re.sub(r"<[^>]+>", " ", html)
        # Collapse whitespace
        text = _re.sub(r"\s+", " ", text).strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[Content truncated]"
        return text

    def _duckduckgo_search(self, query: str, max_results: int) -> str:
        """Search using DuckDuckGo as fallback."""
        from ddgs import DDGS

        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=max_results))
        formatted = "\n\n".join(
            f"**{r.get('title', 'Untitled')}**\n"
            f"{r.get('href', '')}\n{r.get('body', '')}"
            for r in results
        )
        return formatted

    def execute(self, **params: Any) -> ToolResult:
        query = params.get("query", "")
        if not query:
            return ToolResult(
                tool_name="web_search",
                content="No query provided.",
                success=False,
            )

        # If the query contains a URL, fetch it directly instead of searching
        url = self._extract_url(query) if not self._is_url(query) else query.strip()
        if url:
            try:
                content = self._fetch_url(url)
                return ToolResult(
                    tool_name="web_search",
                    content=content or "No content found at URL.",
                    success=True,
                    metadata={"url": url, "mode": "fetch"},
                )
            except Exception as exc:
                return ToolResult(
                    tool_name="web_search",
                    content=f"Failed to fetch URL: {exc}",
                    success=False,
                )

        max_results = params.get("max_results", self._max_results)

        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=self._api_key)
            response = client.search(query, max_results=max_results)
            results = response.get("results", [])
            formatted = "\n\n".join(
                f"**{r.get('title', 'Untitled')}**\n"
                f"{r.get('url', '')}\n{r.get('content', '')}"
                for r in results
            )
            return ToolResult(
                tool_name="web_search",
                content=formatted or "No results found.",
                success=True,
                metadata={"num_results": len(results), "engine": "tavily"},
            )
        except Exception as exc:
            logger.debug(
                "Tavily error (%s), falling back to DuckDuckGo", type(exc).__name__
            )

        try:
            formatted = self._duckduckgo_search(query, max_results)
            return ToolResult(
                tool_name="web_search",
                content=formatted or "No results found.",
                success=True,
                metadata={"engine": "duckduckgo"},
            )
        except ImportError:
            return ToolResult(
                tool_name="web_search",
                content=(
                    "tavily-python not installed and ddgs not available."
                    " Install with: pip install tavily-python ddgs"
                ),
                success=False,
            )
        except Exception as exc:
            return ToolResult(
                tool_name="web_search",
                content=f"Search error: {exc}",
                success=False,
            )


__all__ = ["WebSearchTool"]
