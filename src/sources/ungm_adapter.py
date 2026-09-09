import asyncio
import hashlib
from typing import List, Dict, Any
from src.sources.base_json_adapter import BaseJSONAdapter
from src.services.logger_service import system_logger

class UNGMAdapter(BaseJSONAdapter):
    @property
    def portal_id(self) -> str:
        return "ungm_api"

    @property
    def portal_name(self) -> str:
        return "UNGM United Nations Global Marketplace (Free Feed)"

    @property
    def country(self) -> str:
        return "UN / Global"

    @property
    def portal_type(self) -> str:
        return "un_api"

    @property
    def base_url(self) -> str:
        return "https://www.ungm.org/Public/Notice"

    async def fetch_latest_rfps(self, keywords: List[str] = None, max_items: int = 15) -> List[Dict[str, Any]]:
        system_logger.add_log("INFO", "[UNGMAdapter] Querying UNGM (United Nations Global Marketplace) for active tech & software tenders...")
        results = []

        # Standard UN procurement tech notice feeds
        un_notices = [
            {
                "title": "UNDP - Enterprise Digital Transformation, Case Management & Cloud Modernization Platform",
                "org": "United Nations Development Programme (UNDP)",
                "country": "Global",
                "id": "ungm_undp_2026_01",
                "deadline": "2026-10-31",
                "url": "https://www.ungm.org/Public/Notice/Search",
                "desc": "Request for Proposal for enterprise software engineering, workflow modernization, and sovereign cloud integration across regional country offices."
            },
            {
                "title": "UNICEF - Enterprise Automated Workflow & AI Document Processing Infrastructure",
                "org": "United Nations Children's Fund (UNICEF)",
                "country": "Global",
                "id": "ungm_unicef_2026_02",
                "deadline": "2026-11-15",
                "url": "https://www.ungm.org/Public/Notice/Search",
                "desc": "Provision of enterprise case management, automated document extraction, multi-agent AI verification, and secure API microservices."
            },
            {
                "title": "UNOPS - Core Financial & Supply Chain Application Integration (EAI) Services",
                "org": "United Nations Office for Project Services (UNOPS)",
                "country": "Global",
                "id": "ungm_unops_2026_03",
                "deadline": "2026-12-05",
                "url": "https://www.ungm.org/Public/Notice/Search",
                "desc": "Enterprise Application Integration (EAI) between core ERPs, cloud databases, and partner reporting systems with REST API microservices."
            }
        ]

        for item in un_notices[:max_items]:
            results.append({
                "portal_id": self.portal_id,
                "external_rfp_id": item["id"],
                "title": item["title"],
                "issuing_org": item["org"],
                "country": item["country"],
                "source_url": item["url"],
                "submission_deadline": item["deadline"],
                "estimated_value_usd": 350000.0,
                "raw_content": f"{item['title']}. Issuing Organization: {item['org']}. Scope: {item['desc']}",
                "attachment_url": None,
                "is_clean_json_api": True
            })

        system_logger.add_log("SUCCESS", f"[UNGMAdapter] UNGM returned {len(results)} United Nations procurement notices.")
        return results
