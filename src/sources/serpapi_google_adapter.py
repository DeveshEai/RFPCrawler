import asyncio
import httpx
import re
import hashlib
import random
from typing import List, Dict, Any
from src.sources.base_adapter import BasePortalAdapter
from src.services.logger_service import system_logger
from config import settings

class SerpApiGoogleAdapter(BasePortalAdapter):
    @property
    def portal_id(self) -> str:
        return "google_serpapi"

    @property
    def portal_name(self) -> str:
        return "Google SerpAPI RFP & Tender Crawler"

    @property
    def country(self) -> str:
        return "Global/UK/US"

    @property
    def portal_type(self) -> str:
        return "search_engine"

    @property
    def base_url(self) -> str:
        return "https://serpapi.com"

    async def fetch_latest_rfps(self, keywords: List[str] = None, max_items: int = 15) -> List[Dict[str, Any]]:
        results = []
        api_key = settings.SERPAPI_KEY.strip()

        system_logger.add_log("INFO", "[SerpApiGoogleAdapter] Initiating SerpAPI Google Search RFP crawl...")

        if not api_key:
            system_logger.add_log("WARN", "[SerpApiGoogleAdapter] SERPAPI_KEY not configured in .env. Skipping Google search crawl.")
            return results

        # Precise Google Dorks targeting specific contract notice pages
        queries = [
            'intitle:"Contract Notice" "AI" OR "Software" site:service.gov.uk',
            'intitle:"Tender" "Digital Transformation" OR "Automation" site:gov.uk',
            'intitle:"Solicitation" "Artificial Intelligence" OR "Cloud" site:sam.gov',
            '"Request for Proposal" "Cyber Security" OR "Software" site:gov.uk',
            'intitle:"RFP" "Workflow" OR "Pega" site:service.gov.uk',
            'intitle:"Tender Notice" "Data Platform" OR "Machine Learning" site:gov.uk'
        ]

        # Pick 3 queries per run to vary results
        selected_queries = random.sample(queries, min(3, len(queries)))

        async with httpx.AsyncClient(timeout=25.0) as client:
            for q in selected_queries:
                try:
                    system_logger.add_log("INFO", f"[SerpApiGoogleAdapter] Querying Google SerpAPI: '{q[:60]}...'")
                    params = {
                        "engine": "google",
                        "q": q,
                        "tbs": "qdr:m",  # Past month to fetch recent live opportunities
                        "api_key": api_key
                    }
                    resp = await client.get(f"{self.base_url}/search.json", params=params)

                    if resp.status_code in (401, 403):
                        system_logger.add_log("WARN", "[SerpApiGoogleAdapter] SerpAPI key unauthorized. Please check your key at https://serpapi.com.")
                        break

                    if resp.status_code != 200:
                        system_logger.add_log("WARN", f"[SerpApiGoogleAdapter] SerpAPI returned HTTP status {resp.status_code}")
                        continue

                    data = resp.json()
                    organic = data.get("organic_results", [])

                    for item in organic:
                        if len(results) >= max_items:
                            break

                        title = item.get("title", "").strip()
                        snippet = item.get("snippet", "").strip()
                        link = item.get("link", "").strip()
                        domain = item.get("displayed_link", "Google Search Portal")

                        if not title or not link:
                            continue

                        # Filter out generic search result aggregator landing pages
                        lower_title = title.lower()
                        if "search results" in lower_title or "search page" in lower_title or lower_title == "find a tender":
                            continue

                        link_hash = hashlib.md5(link.encode('utf-8')).hexdigest()[:12]
                        results.append({
                            "external_rfp_id": f"google_serpapi_{link_hash}",
                            "title": title,
                            "issuing_org": domain,
                            "country": "Global",
                            "estimated_value_usd": 0.0,
                            "currency": "USD",
                            "submission_deadline": "See Source Notice",
                            "source_url": link,
                            "raw_content": f"{title}\n\n{snippet}",
                            "portal_id": self.portal_id
                        })

                except Exception as e:
                    system_logger.add_log("WARN", f"[SerpApiGoogleAdapter] Query exception: {e}")

        system_logger.add_log("SUCCESS", f"[SerpApiGoogleAdapter] Returned {len(results)} live Google RFP search records.")
        return results
