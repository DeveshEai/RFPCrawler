import asyncio
import hashlib
from typing import List, Dict, Any
from src.sources.base_json_adapter import BaseJSONAdapter
from src.services.logger_service import system_logger

class WorldBankAPIAdapter(BaseJSONAdapter):
    @property
    def portal_id(self) -> str:
        return "world_bank_api"

    @property
    def portal_name(self) -> str:
        return "World Bank Global Procurement API (Free JSON Feed)"

    @property
    def country(self) -> str:
        return "Global / Multilateral"

    @property
    def portal_type(self) -> str:
        return "multilateral_api"

    @property
    def base_url(self) -> str:
        return "https://search.worldbank.org/api/v2/procnotices"

    async def fetch_latest_rfps(self, keywords: List[str] = None, max_items: int = 15) -> List[Dict[str, Any]]:
        system_logger.add_log("INFO", "[WorldBankAPIAdapter] Querying World Bank Global Procurement API for IT & Software tenders...")
        results = []

        params = {
            "format": "json",
            "qterm": "software OR digital OR \"information technology\"",
            "rows": max_items,
            "sort": "noticedate desc"
        }

        data = await self.fetch_json_data(
            self.base_url,
            method="GET",
            params=params
        )

        if not data or not isinstance(data, dict):
            # Fallback simpler query term
            data = await self.fetch_json_data(
                self.base_url,
                method="GET",
                params={"format": "json", "qterm": "software", "rows": max_items}
            )

        if data and isinstance(data, dict):
            notices = data.get("procnotices", [])
            if isinstance(notices, dict):
                notices = list(notices.values())

            for item in notices:
                if len(results) >= max_items:
                    break

                if not isinstance(item, dict):
                    continue

                item_id = str(item.get("id") or "")
                title = item.get("bid_description") or item.get("project_name") or ""
                project_name = item.get("project_name") or "World Bank Digital Project"
                country = item.get("project_ctry_name") or "Global"
                org_name = f"World Bank - {country} ({project_name[:35]})"
                deadline = str(item.get("submission_date") or item.get("noticedate") or "Check Notice")[:10]
                
                source_url = f"https://projects.worldbank.org/en/projects-operations/procurement-detail/{item_id}" if item_id else "https://projects.worldbank.org/en/projects-operations/procurement/brief/procurement-notices"

                raw_desc = item.get("notice_text") or f"{title}. {project_name}"
                # Clean basic HTML tags from notice_text
                import re
                clean_text = re.sub(r"<[^>]+>", " ", str(raw_desc)).strip()
                clean_text = re.sub(r"\s+", " ", clean_text)

                if not title or len(title) < 5:
                    continue

                results.append({
                    "portal_id": self.portal_id,
                    "external_rfp_id": f"wb_{item_id or hashlib.md5(title.encode('utf-8')).hexdigest()[:10]}",
                    "title": str(title)[:180],
                    "issuing_org": str(org_name),
                    "country": str(country),
                    "source_url": source_url,
                    "submission_deadline": deadline,
                    "estimated_value_usd": 0.0,
                    "raw_content": f"{title}. Project: {project_name}. Scope: {clean_text[:400]}",
                    "attachment_url": None,
                    "is_clean_json_api": True
                })

        system_logger.add_log("SUCCESS", f"[WorldBankAPIAdapter] World Bank API returned {len(results)} global procurement notices.")
        return results
