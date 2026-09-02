import asyncio
import httpx
import re
from typing import List, Dict, Any
from src.sources.base_adapter import BasePortalAdapter
from src.services.logger_service import system_logger
from config import settings

class SerperGoogleAdapter(BasePortalAdapter):
    @property
    def portal_id(self) -> str:
        return "google_serper"

    @property
    def portal_name(self) -> str:
        return "Google Serper RFP & Tender Crawler"

    @property
    def country(self) -> str:
        return "Global/UK/US"

    @property
    def portal_type(self) -> str:
        return "search_engine"

    @property
    def base_url(self) -> str:
        return "https://google.serper.dev"

    async def fetch_latest_rfps(self, keywords: List[str] = None, max_items: int = 15) -> List[Dict[str, Any]]:
        results = []
        api_key = settings.SERPER_API_KEY.strip()

        system_logger.add_log("INFO", "[SerperGoogleAdapter] Initiating Google Serper RFP search crawl...")

        if not api_key:
            system_logger.add_log("WARN", "[SerperGoogleAdapter] SERPER_API_KEY not configured in .env. Skipping Google search crawl.")
            return results

        queries = [
            '"Request for Proposal" ("Pega" OR "Agentic AI" OR "Digital Transformation")',
            '"Tender Notice" ("Cloud Migration" OR "Microservices" OR "Automation")',
            'site:.gov.uk "RFP" ("Information Technology" OR "Software Development")',
            'site:sam.gov "Solicitation" ("Artificial Intelligence" OR "Workflow")'
        ]

        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            for q in queries:
                try:
                    system_logger.add_log("INFO", f"[SerperGoogleAdapter] Executing Google Dork query: {q[:60]}...")
                    resp = await client.post(
                        f"{self.base_url}/search",
                        json={"q": q, "num": 10},
                        headers=headers
                    )

                    if resp.status_code == 403:
                        system_logger.add_log("WARN", "[SerperGoogleAdapter] Serper API Key returned 403 Unauthorized. Please verify key status at https://serper.dev.")
                        break

                    if resp.status_code != 200:
                        system_logger.add_log("WARN", f"[SerperGoogleAdapter] Serper returned HTTP status {resp.status_code}")
                        continue

                    data = resp.json()
                    organic = data.get("organic", [])

                    for item in organic:
                        if len(results) >= max_items:
                            break

                        title = item.get("title", "")
                        snippet = item.get("snippet", "")
                        link = item.get("link", "")

                        if not title or not link:
                            continue

                        results.append({
                            "external_rfp_id": f"google_serper_{hash(link) & 0xFFFFFFFF}",
                            "title": title,
                            "issuing_org": item.get("domain", "Public Procurement Portal"),
                            "country": "Global",
                            "estimated_value_usd": 0.0,
                            "currency": "USD",
                            "submission_deadline": "See Source Notice",
                            "source_url": link,
                            "raw_content": f"{title}\n\n{snippet}",
                            "portal_id": self.portal_id
                        })

                except Exception as e:
                    system_logger.add_log("WARN", f"[SerperGoogleAdapter] Query error: {e}")

        system_logger.add_log("SUCCESS", f"[SerperGoogleAdapter] Returned {len(results)} live Google RFP search records.")
        return results
