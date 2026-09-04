import asyncio
import re
import hashlib
import random
from typing import List, Dict, Any
from duckduckgo_search import DDGS
import httpx
from src.sources.base_adapter import BasePortalAdapter, fetch_deep_page_content, is_valid_rfp_notice
from src.services.logger_service import system_logger

class DuckDuckGoFreeAdapter(BasePortalAdapter):
    @property
    def portal_id(self) -> str:
        return "duckduckgo_free"

    @property
    def portal_name(self) -> str:
        return "DuckDuckGo Free Search Crawler (No API Key)"

    @property
    def country(self) -> str:
        return "Global/UK/US"

    @property
    def portal_type(self) -> str:
        return "search_engine"

    @property
    def base_url(self) -> str:
        return "https://duckduckgo.com"

    async def fetch_latest_rfps(self, keywords: List[str] = None, max_items: int = 15) -> List[Dict[str, Any]]:
        results = []
        system_logger.add_log("INFO", "[DuckDuckGoFreeAdapter] Initiating 100% Free DuckDuckGo search dork crawl...")

        queries = [
            'intitle:"Contract Notice" "Pega" OR "BPM" site:service.gov.uk',
            'intitle:"Tender" "Sovereign AI" OR "Arabic AI" OR "Agentic" site:gov.ae',
            'intitle:"Solicitation" "Microservices" OR "Integration Platform" site:sam.gov',
            '"Request for Proposal" "Case Management" OR "Process Automation" site:gov.uk',
            'intitle:"RFP" "MuleSoft" OR "API Gateway" site:service.gov.uk',
            'intitle:"Tender Notice" "Workflow Automation" site:gov.uk'
        ]

        selected_queries = random.sample(queries, min(3, len(queries)))

        def _do_search(query_str: str) -> List[Dict[str, Any]]:
            items = []
            try:
                with DDGS() as ddgs:
                    raw_results = list(ddgs.text(query_str, max_results=8))
                    for r in raw_results:
                        items.append(r)
            except Exception as e:
                system_logger.add_log("WARN", f"[DuckDuckGoFreeAdapter] Search error for '{query_str[:30]}': {e}")
            return items

        loop = asyncio.get_event_loop()

        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            for q in selected_queries:
                system_logger.add_log("INFO", f"[DuckDuckGoFreeAdapter] Executing precision dork: '{q[:55]}...'")
                raw_items = await loop.run_in_executor(None, _do_search, q)

                for item in raw_items:
                    if len(results) >= max_items:
                        break

                    title = item.get("title", "").strip()
                    href = item.get("href", "").strip()
                    snippet = item.get("body", "").strip()

                    if not title or not href:
                        continue

                    lower_title = title.lower()
                    if "search results" in lower_title or "search page" in lower_title or lower_title == "find a tender":
                        continue

                    # Reject blogs, glossaries, top lists & software tools
                    if not is_valid_rfp_notice(title, href):
                        system_logger.add_log("INFO", f"[DuckDuckGoFreeAdapter] Excluded blog/article noise: '{title[:45]}'")
                        continue

                    link_hash = hashlib.md5(href.encode('utf-8')).hexdigest()[:12]
                    clean_title = re.sub(r'<[^>]+>', '', title)

                    deep_body = await fetch_deep_page_content(client, href, max_chars=2500)
                    full_text = deep_body if len(deep_body) > 200 else snippet

                    results.append({
                        "portal_id": self.portal_id,
                        "external_rfp_id": f"duckduckgo_free_{link_hash}",
                        "title": clean_title[:180],
                        "issuing_org": "DuckDuckGo Free Web Search",
                        "country": "Global",
                        "source_url": href,
                        "submission_deadline": "Check Notice Details",
                        "estimated_value_usd": 0.0,
                        "raw_content": f"{clean_title}. {full_text}"
                    })

        system_logger.add_log("SUCCESS", f"[DuckDuckGoFreeAdapter] Free search crawl complete. Scraped {len(results)} opportunities.")
        return results
