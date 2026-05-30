from __future__ import annotations

from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup

from config import SEARCH_MAX_PAGE_CHARS, SEARCH_MAX_RESULTS, SEARCH_TIMEOUT_SECONDS


def _extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return " ".join(text.split())[:SEARCH_MAX_PAGE_CHARS]


async def search_web(query: str) -> str:
    search_url = f"https://html.duckduckgo.com/html/?q={quote(query)}"

    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
        search_response = await client.get(
            search_url,
            headers={"User-Agent": "Mozilla/5.0 (Project-Yachiyo-Phase1)"},
        )
        search_response.raise_for_status()

        soup = BeautifulSoup(search_response.text, "html.parser")
        candidates = []
        for result in soup.select(".result")[:SEARCH_MAX_RESULTS]:
            anchor = result.select_one("a.result__a")
            snippet = result.select_one(".result__snippet")
            if anchor is None:
                continue
            title_text = anchor.get_text(" ", strip=True)
            href = anchor.get("href", "")
            snippet_text = snippet.get_text(" ", strip=True) if snippet else ""
            candidates.append((title_text, href, snippet_text))

        if not candidates:
            return "No search results found."

        rendered_results = []
        for title_text, href, snippet_text in candidates:
            page_excerpt = ""
            if href:
                try:
                    page_response = await client.get(
                        href,
                        headers={"User-Agent": "Mozilla/5.0 (Project-Yachiyo-Phase1)"},
                    )
                    page_response.raise_for_status()
                    page_excerpt = _extract_visible_text(page_response.text)
                except Exception:  # noqa: BLE001
                    page_excerpt = ""

            result_text = f"{title_text}: {snippet_text}".strip()
            if page_excerpt:
                result_text += f"\nExcerpt: {page_excerpt}"
            rendered_results.append(result_text)

        return "\n\n".join(rendered_results)
