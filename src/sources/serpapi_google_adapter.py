import asyncio
import httpx
import re
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

        queries = [
            'Request for Proposal Pega AI Digital Transformation site:service.gov.uk',
            'Tender Notice Cloud Migration Microservices Automation site:gov.uk',
            'RFP Software Development Artificial Intelligence site:gov',
            'Solicitation Workflow Automation Pega site:sam.gov'
        ]

        async with httpx.AsyncClient(timeout=25.0) as client:
            for q in queries:
                try:
                    system_logger.add_log("INFO", f"[SerpApiGoogleAdapter] Querying SerpAPI: {q[:60]}...")
                    params = {
                        "engine": "google",
                        "q": q,
                        "api_key": api_key
                    }
                    resp = await client.get(f"{self.base_url}/search.json", params=params)

                    if resp.status_code == 401 or resp.status_code == 403:
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

                        title = item.get("title", "")
                        snippet = item.get("snippet", "")
                        link = item.get("link", "")
                        domain = item.get("displayed_link", "Google Search Portal")

                        if not title or not link:
                            continue

                        results.append({
                            "external_rfp_id": f"google_serpapi_{hash(link) & 0xFFFFFFFF}",
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
