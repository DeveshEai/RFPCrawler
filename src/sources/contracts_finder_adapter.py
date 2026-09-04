import asyncio
import httpx
import re
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Any
from src.sources.base_adapter import BasePortalAdapter, fetch_deep_page_content
from src.services.logger_service import system_logger

class ContractsFinderAdapter(BasePortalAdapter):
    @property
    def portal_id(self) -> str:
        return "contracts_finder"

    @property
    def portal_name(self) -> str:
        return "UK Contracts Finder (Official Public Procurement)"

    @property
    def country(self) -> str:
        return "UK"

    @property
    def portal_type(self) -> str:
        return "government"

    @property
    def base_url(self) -> str:
        return "https://www.contractsfinder.service.gov.uk"

    async def fetch_latest_rfps(self, keywords: List[str] = None, max_items: int = 30) -> List[Dict[str, Any]]:
        results = []
        seen_urls = set()

        system_logger.add_log("INFO", "[ContractsFinderAdapter] Initiating live multi-page scrape against UK Contracts Finder portal...")

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

        # Non-IT physical & facilities terms to exclude
        bad_keywords = [
            "cabling", "floral", "flowers", "catering", "vending", "cleaning",
            "gritting", "boiler", "painting", "construction", "plumbing", "roofing",
            "tires", "hvac", "air conditioner", "liquid handling", "pharmaceutical",
            "courier", "transport", "taxi", "fuel card", "decommissioning", "surveying",
            "grounds maintenance", "security guard", "laundry", "waste",
            "mining", "capital works", "minibus", "biomass", "window cleaning", "furniture"
        ]

        async def scrape_page(client: httpx.AsyncClient, page: int) -> List[dict]:
            items = []
            try:
                url = f"{self.base_url}/Search/Results?&status=live&page={page}"
                system_logger.add_log("INFO", f"[Scraper:ContractsFinder] Fetching search page {page}/15: {url}")
                resp = await client.get(url, headers=headers, timeout=25.0)
                if resp.status_code != 200:
                    system_logger.add_log("WARN", f"[Scraper] Page {page} returned HTTP status {resp.status_code}")
                    return items

                soup = BeautifulSoup(resp.text, "html.parser")
                search_results = soup.find_all("div", class_="search-result")

                for sr in search_results:
                    title_el = sr.find("h2")
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

                    text_lines = [l.strip() for l in sr.get_text("\n", strip=True).splitlines() if l.strip()]
                    buyer = "UK Public Sector Body"
                    if len(text_lines) > 1 and text_lines[0] == title:
                        buyer = text_lines[1]

                    full_text = sr.get_text(" ", strip=True)

                    # Extract closing date (e.g., "Closing 15 September 2026, 12pm")
                    closing_date_str = None
                    closing_match = re.search(r"Closing\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})", full_text, re.IGNORECASE)
                    if closing_match:
                        raw_d = closing_match.group(1).strip()
                        for fmt in ("%d %B %Y", "%d %b %Y"):
                            try:
                                closing_date_str = datetime.strptime(raw_d, fmt).strftime("%Y-%m-%d")
                                break
                            except Exception:
                                pass

                    # Extract contract value in GBP £
                    contract_val = 0.0
                    value_match = re.search(r"Contract value\s*(?:[£$€]?\s*([\d,]+))", full_text, re.IGNORECASE)
                    if value_match:
                        val_num_str = value_match.group(1).replace(",", "")
                        try:
                            contract_val = float(val_num_str)
                        except Exception:
                            pass

                    items.append({
                        "title": title,
                        "url": notice_url,
                        "buyer": buyer,
                        "closing": closing_date_str,
                        "val_num": contract_val,
                        "raw_text": full_text[:600]
                    })
            except Exception as e:
                err_msg = str(e) or type(e).__name__
                system_logger.add_log("WARN", f"[Scraper] Page {page} notice fetch note: {err_msg}")
            return items

        try:
            limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
            async with httpx.AsyncClient(follow_redirects=True, limits=limits) as client:
                all_notices = []
                for p in range(1, 16):
                    page_items = await scrape_page(client, p)
                    all_notices.extend(page_items)
                    await asyncio.sleep(0.4)

                system_logger.add_log("INFO", f"[ContractsFinderAdapter] Found {len(all_notices)} total notices across 15 search pages.")

                tech_candidates = []
                for item in all_notices:
                    combined_text = (item["title"] + " " + item["raw_text"]).lower()
                    if any(kw in combined_text for kw in tech_keywords):
                        if not any(bad in combined_text for bad in bad_keywords):
                            tech_candidates.append(item)

                system_logger.add_log("INFO", f"[KeywordFilter] Filtered down to {len(tech_candidates)} candidate software/AI tenders out of {len(all_notices)} notices.")

                for item in tech_candidates:
                    if len(results) >= max_items:
                        break

                    deep_body = await fetch_deep_page_content(client, item["url"], max_chars=3000)
                    full_content = deep_body if len(deep_body) > 200 else item["raw_text"]

                    results.append({
                        "external_rfp_id": f"uk_cf_{hash(item['url']) & 0xFFFFFFFF}",
                        "title": item["title"],
                        "issuing_org": item["buyer"],
                        "country": "UK",
                        "estimated_value_usd": item["val_num"],
                        "currency": "GBP",
                        "submission_deadline": item["closing"],
                        "source_url": item["url"],
                        "raw_content": f"{item['title']}. {full_content}",
                        "portal_id": self.portal_id
                    })

                system_logger.add_log("SUCCESS", f"[ContractsFinderAdapter] Successfully returned {len(results)} structured UK RFP records.")

        except Exception as e:
            system_logger.add_log("ERROR", f"[ContractsFinderAdapter] Global fetch exception: {e}")

        return results
