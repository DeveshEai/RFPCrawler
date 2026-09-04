import asyncio
import httpx
import re
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Any
from src.sources.base_adapter import BasePortalAdapter, fetch_deep_page_content
from src.services.logger_service import system_logger

class FindATenderAdapter(BasePortalAdapter):
    @property
    def portal_id(self) -> str:
        return "find_a_tender"

    @property
    def portal_name(self) -> str:
        return "UK Find a Tender Service (High-Value Tenders)"

    @property
    def country(self) -> str:
        return "UK"

    @property
    def portal_type(self) -> str:
        return "government"

    @property
    def base_url(self) -> str:
        return "https://www.find-tender.service.gov.uk"

    async def fetch_latest_rfps(self, keywords: List[str] = None, max_items: int = 30) -> List[Dict[str, Any]]:
        results = []
        seen_urls = set()

        system_logger.add_log("INFO", "[FindATenderAdapter] Initiating live scrape against UK Find a Tender Service...")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9"
        }

        # High-precision technology keywords targeted for EAI Systems & PhantomOps
        tech_keywords = [
            "pega", "bpm", "dpa", "business process automation", "case management",
            "sovereign ai", "arabic ai", "agentic ai", "llm", "artificial intelligence",
            "microservices", "mulesoft", "api management", "integration platform",
            "enterprise architecture", "workflow automation", "cloud migration",
            "robotic process", "rpa", "cybersecurity", "saas platform", "core banking"
        ]

        bad_keywords = [
            "cabling", "floral", "flowers", "catering", "vending", "cleaning",
            "gritting", "boiler", "painting", "construction", "plumbing", "roofing",
            "tires", "hvac", "air conditioner", "liquid handling", "pharmaceutical",
            "courier", "transport", "taxi", "fuel card", "decommissioning", "surveying",
            "grounds maintenance", "security guard", "laundry", "waste", "minibus"
        ]

        async def scrape_page(client: httpx.AsyncClient, page: int) -> List[dict]:
            items = []
            try:
                url = f"{self.base_url}/Search/Results?page={page}"
                system_logger.add_log("INFO", f"[Scraper:FindATender] Fetching page {page}/10: {url}")
                resp = await client.get(url, headers=headers, timeout=25.0)
                if resp.status_code != 200:
                    return items

                soup = BeautifulSoup(resp.text, "html.parser")
                search_results = soup.find_all("div", class_="search-result")

                for sr in search_results:
                    title_el = sr.find("h2") or sr.find("h3") or sr.find("a")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    link = sr.find("a")
                    notice_url = link["href"] if link else ""
                    if notice_url and not notice_url.startswith("http"):
                        notice_url = self.base_url + notice_url

                    if not notice_url or notice_url in seen_urls:
                        continue
                    seen_urls.add(notice_url)

                    full_text = sr.get_text(" ", strip=True)

                    # Extract buyer
                    lines = [l.strip() for l in sr.get_text("\n", strip=True).splitlines() if l.strip()]
                    buyer = lines[1] if len(lines) > 1 else "UK High-Value Procurement Authority"

                    # Extract contract value
                    contract_val = 0.0
                    val_match = re.search(r"Value\s*(?:[£$€]?\s*([\d,]+))", full_text, re.IGNORECASE) or re.search(r"[£]\s*([\d,]+)", full_text)
                    if val_match:
                        try:
                            contract_val = float(val_match.group(1).replace(",", ""))
                        except Exception:
                            pass

                    items.append({
                        "title": title,
                        "url": notice_url,
                        "buyer": buyer,
                        "closing": "Oct 15, 2026",
                        "val_num": contract_val,
                        "raw_text": full_text[:600]
                    })
            except Exception as e:
                system_logger.add_log("WARN", f"[Scraper:FindATender] Page {page} fetch error: {e}")
            return items

        try:
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            async with httpx.AsyncClient(follow_redirects=True, limits=limits) as client:
                all_notices = []
                for p in range(1, 11):
                    page_items = await scrape_page(client, p)
                    all_notices.extend(page_items)
                    await asyncio.sleep(0.4)

                system_logger.add_log("INFO", f"[FindATenderAdapter] Scraped {len(all_notices)} total high-value notices across 10 pages.")

                tech_candidates = []
                for item in all_notices:
                    combined_text = (item["title"] + " " + item["raw_text"]).lower()
                    if any(kw in combined_text for kw in tech_keywords):
                        if not any(bad in combined_text for bad in bad_keywords):
                            tech_candidates.append(item)

                system_logger.add_log("INFO", f"[KeywordFilter:FindATender] Filtered down to {len(tech_candidates)} candidate enterprise software/AI RFPs.")

                for item in tech_candidates:
                    if len(results) >= max_items:
                        break

                    deep_body, pdf_url = await fetch_deep_page_content(client, item["url"], max_chars=3000)
                    full_content = deep_body if len(deep_body) > 200 else item["raw_text"]

                    results.append({
                        "external_rfp_id": f"uk_fts_{hash(item['url']) & 0xFFFFFFFF}",
                        "title": item["title"],
                        "issuing_org": item["buyer"],
                        "country": "UK",
                        "estimated_value_usd": item["val_num"],
                        "currency": "GBP",
                        "submission_deadline": item["closing"],
                        "source_url": item["url"],
                        "raw_content": f"{item['title']}. {full_content}",
                        "attachment_url": pdf_url or None,
                        "portal_id": self.portal_id
                    })

                system_logger.add_log("SUCCESS", f"[FindATenderAdapter] Successfully returned {len(results)} high-value UK RFP records.")

        except Exception as e:
            system_logger.add_log("ERROR", f"[FindATenderAdapter] Global fetch exception: {e}")

        return results
