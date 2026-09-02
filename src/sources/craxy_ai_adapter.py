import asyncio
import re
import hashlib
from typing import List, Dict, Any
import httpx
from src.sources.base_adapter import BasePortalAdapter
from src.services.logger_service import system_logger

class CraxyAIAdapter(BasePortalAdapter):
    @property
    def portal_id(self) -> str:
        return "craxy_ai"

    @property
    def portal_name(self) -> str:
        return "Craxy AI Free RFP Database (Global/US/UK)"

    @property
    def country(self) -> str:
        return "Global/US/UK"

    @property
    def portal_type(self) -> str:
        return "rfp_aggregator"

    @property
    def base_url(self) -> str:
        return "https://craxy.ai/find-rfps"

    async def fetch_latest_rfps(self, keywords: List[str] = None, max_items: int = 15) -> List[Dict[str, Any]]:
        results = []
        system_logger.add_log("INFO", "[CraxyAIAdapter] Initiating Crawl from Craxy AI Free RFP Database...")

        categories = [
            "https://craxy.ai/find-rfps/industry/it-technology",
            "https://craxy.ai/find-rfps/industry/professional-services",
            "https://craxy.ai/find-rfps/industry/federal"
        ]

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        async with httpx.AsyncClient(headers=headers, timeout=12.0, follow_redirects=True) as client:
            opp_ids = set()
            for cat_url in categories:
                try:
                    system_logger.add_log("INFO", f"[CraxyAIAdapter] Fetching opportunities from {cat_url}...")
                    resp = await client.get(cat_url)
                    if resp.status_code == 200:
                        matches = re.findall(r'/find-rfps/(cm[a-zA-Z0-9]+)', resp.text)
                        for m in matches:
                            opp_ids.add(m)
                except Exception as e:
                    system_logger.add_log("WARN", f"[CraxyAIAdapter] Error fetching category {cat_url}: {e}")

            system_logger.add_log("INFO", f"[CraxyAIAdapter] Discovered {len(opp_ids)} RFP listings from Craxy AI catalog. Extracting top notices...")

            sorted_ids = list(opp_ids)[:max_items]

            for opp_id in sorted_ids:
                opp_url = f"https://craxy.ai/find-rfps/{opp_id}"
                try:
                    resp = await client.get(opp_url)
                    if resp.status_code != 200:
                        continue

                    html_text = resp.text
                    clean_text = re.sub(r'<[^>]+>', ' ', html_text)
                    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

                    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html_text, re.DOTALL)
                    title = title_match.group(1).strip() if title_match else "RFP Opportunity Notice"
                    title = re.sub(r'<[^>]+>', '', title)

                    org_match = re.search(r'([A-Za-z0-9\s,\.]+(?:Department|Authority|Commission|Council|Agency|District|County|State|Gov|Services|Inc|LLC))', clean_text)
                    issuing_org = org_match.group(1).strip() if org_match else "Craxy AI Government RFP Catalog"

                    deadline_match = re.search(r'(\d+\s*days?\s*left|\d{4}-\d{2}-\d{2})', clean_text, re.IGNORECASE)
                    deadline = deadline_match.group(1) if deadline_match else "Check Notice Details"

                    snippet = clean_text[:600]

                    results.append({
                        "portal_id": self.portal_id,
                        "external_rfp_id": f"craxy_ai_{opp_id}",
                        "title": title[:180],
                        "issuing_org": issuing_org[:100],
                        "country": "US/Global",
                        "source_url": opp_url,
                        "submission_deadline": deadline,
                        "estimated_value_usd": 0.0,
                        "raw_content": f"{title}. {snippet}"
                    })

                except Exception as e:
                    system_logger.add_log("WARN", f"[CraxyAIAdapter] Error fetching detail for {opp_id}: {e}")

        system_logger.add_log("SUCCESS", f"[CraxyAIAdapter] Craxy AI crawl complete. Scraped {len(results)} opportunities.")
        return results
