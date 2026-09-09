import asyncio
import hashlib
from typing import List, Dict, Any
from src.sources.base_json_adapter import BaseJSONAdapter
from src.services.logger_service import system_logger

class UKContractsAPIAdapter(BaseJSONAdapter):
    @property
    def portal_id(self) -> str:
        return "uk_contracts_api"

    @property
    def portal_name(self) -> str:
        return "UK Contracts Finder REST API (Free JSON Feed)"

    @property
    def country(self) -> str:
        return "UK"

    @property
    def portal_type(self) -> str:
        return "government_api"

    @property
    def base_url(self) -> str:
        return "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"

    async def fetch_latest_rfps(self, keywords: List[str] = None, max_items: int = 15) -> List[Dict[str, Any]]:
        system_logger.add_log("INFO", "[UKContractsAPIAdapter] Querying UK Contracts Finder REST API for IT & Software CPV codes...")
        results = []

        # CPV 72000000 (IT Services) & CPV 48000000 (Software packages)
        data = await self.fetch_json_data(
            self.base_url,
            method="GET",
            params={"cpv": "72000000", "size": max_items}
        )

        if not data or not isinstance(data, dict) or not data.get("releases"):
            # Try software CPV fallback
            data = await self.fetch_json_data(
                self.base_url,
                method="GET",
                params={"cpv": "48000000", "size": max_items}
            )

        if data and isinstance(data, dict):
            releases = data.get("releases") or data.get("noticeList") or data.get("results") or []
            for rel in releases:
                if len(results) >= max_items:
                    break

                if not isinstance(rel, dict):
                    continue

                tender = rel.get("tender") or {}
                buyer = rel.get("buyer") or {}
                
                title = tender.get("title") or rel.get("title") or ""
                description = tender.get("description") or tender.get("summary") or title
                org_name = buyer.get("name") or rel.get("organisationName") or "UK Public Sector"
                
                tender_period = tender.get("tenderPeriod") or {}
                closing_date = tender_period.get("endDate") or tender.get("closingDate") or "Check Notice"
                
                rel_id = rel.get("id") or tender.get("id") or ""
                clean_id = str(rel_id).replace("ocds-b6fded-", "").replace("/", "_")
                if not clean_id or len(clean_id) < 3:
                    clean_id = hashlib.md5(title.encode('utf-8')).hexdigest()[:10]
                
                source_url = f"https://www.contractsfinder.service.gov.uk/Notice/{clean_id}"

                if not title:
                    continue

                results.append({
                    "portal_id": self.portal_id,
                    "external_rfp_id": f"uk_cpv_{clean_id}",
                    "title": str(title)[:180],
                    "issuing_org": str(org_name),
                    "country": "UK",
                    "source_url": source_url,
                    "submission_deadline": str(closing_date)[:10],
                    "estimated_value_usd": 0.0,
                    "raw_content": f"{title}. {description}",
                    "attachment_url": None,
                    "is_clean_json_api": True
                })

        system_logger.add_log("SUCCESS", f"[UKContractsAPIAdapter] UK Contracts Finder API returned {len(results)} IT procurement notices.")
        return results

