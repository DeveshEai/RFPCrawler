import asyncio
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from src.db.models import ProcurementPortal, RFPOpportunity, RFPExecutionEvaluation
from src.sources.contracts_finder_adapter import ContractsFinderAdapter
from src.sources.find_a_tender_adapter import FindATenderAdapter
from src.sources.global_tech_tenders_adapter import GlobalTechTendersAdapter
from src.sources.serpapi_google_adapter import SerpApiGoogleAdapter
from src.intelligence.stage1_filter import Stage1DeterministicFilter
from src.intelligence.llm_reasoner import LLMOpportunityReasoner
from src.services.email_service import EmailAlertService
from src.services.logger_service import system_logger

_cancellation_requested = False

def request_crawl_cancel():
    global _cancellation_requested
    _cancellation_requested = True

def is_cancel_requested() -> bool:
    global _cancellation_requested
    return _cancellation_requested

def reset_crawl_cancel():
    global _cancellation_requested
    _cancellation_requested = False

class RFPIntelligencePipeline:
    def __init__(self, db: Session):
        self.db = db
        self.adapters = [
            ContractsFinderAdapter(),
            FindATenderAdapter(),
            GlobalTechTendersAdapter(),
            SerpApiGoogleAdapter()
        ]
        self.stage1_filter = Stage1DeterministicFilter()
        self.reasoner = LLMOpportunityReasoner()
        self.email_service = EmailAlertService()

    def _ensure_portals_seeded(self):
        for adapter in self.adapters:
            portal = self.db.query(ProcurementPortal).filter_by(portal_id=adapter.portal_id).first()
            if not portal:
                portal = ProcurementPortal(
                    portal_id=adapter.portal_id,
                    name=adapter.portal_name,
                    country=adapter.country,
                    portal_type=adapter.portal_type,
                    base_url=adapter.base_url,
                    is_active=True
                )
                self.db.add(portal)
        self.db.commit()

    async def run_pipeline(self, target_portal_id: str = None) -> Dict[str, Any]:
        reset_crawl_cancel()
        self._ensure_portals_seeded()
        stats = {"scraped": 0, "stage1_passed": 0, "evaluated": 0, "pursued": 0, "emails_sent": 0}

        # Retrieve enabled portal IDs from database
        active_portal_ids = {
            p.portal_id for p in self.db.query(ProcurementPortal).filter_by(is_active=True).all()
        }

        active_adapters = self.adapters
        if target_portal_id:
            active_adapters = [a for a in self.adapters if a.portal_id == target_portal_id]
        else:
            # Standard crawl runs enabled portals only
            active_adapters = [a for a in self.adapters if a.portal_id in active_portal_ids and a.portal_id != "google_serpapi"]

        from datetime import datetime
        batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        for adapter in active_adapters:
            if is_cancel_requested():
                system_logger.add_log("WARN", "🛑 Crawl run terminated by user request.")
                reset_crawl_cancel()
                return stats

            system_logger.add_log("INFO", f"[Pipeline] Starting execution of adapter: {adapter.portal_name} (Batch: {batch_id})")
            rfps = await adapter.fetch_latest_rfps(max_items=30)
            stats["scraped"] += len(rfps)

            for rfp_data in rfps:
                if is_cancel_requested():
                    system_logger.add_log("WARN", "🛑 Crawl run terminated by user request.")
                    reset_crawl_cancel()
                    return stats
                ext_id = rfp_data.get("external_rfp_id")
                source_url = rfp_data.get("source_url")
                title = rfp_data.get("title")
                org = rfp_data.get("issuing_org")

                # Multi-field deduplication check
                existing = self.db.query(RFPOpportunity).filter(
                    (RFPOpportunity.external_rfp_id == ext_id) |
                    (RFPOpportunity.source_url == source_url) |
                    ((RFPOpportunity.title == title) & (RFPOpportunity.issuing_org == org))
                ).first()

                if existing:
                    system_logger.add_log("INFO", f"[Pipeline] Skipping duplicate record: '{title[:40]}'")
                    continue

                # Stage 1: Deterministic hard filter
                passed_stage1, reason = self.stage1_filter.evaluate(rfp_data)
                if not passed_stage1:
                    system_logger.add_log("WARN", f"[Stage1Filter] Rejected '{rfp_data['title'][:40]}': {reason}")
                    continue

                stats["stage1_passed"] += 1
                system_logger.add_log("SUCCESS", f"[Stage1Filter] Passed: '{rfp_data['title'][:50]}'")

                # Save RFP opportunity record with batch_id
                rfp_obj = RFPOpportunity(
                    portal_id=rfp_data["portal_id"],
                    external_rfp_id=ext_id,
                    title=rfp_data["title"],
                    issuing_org=rfp_data.get("issuing_org"),
                    country=rfp_data.get("country"),
                    opportunity_type=rfp_data.get("opportunity_type", "RFP"),
                    source_url=rfp_data["source_url"],
                    publication_date=rfp_data.get("publication_date"),
                    submission_deadline=rfp_data.get("submission_deadline"),
                    estimated_value_usd=rfp_data.get("estimated_value_usd", 0.0),
                    raw_content=rfp_data.get("raw_content", ""),
                    batch_id=batch_id
                )
                self.db.add(rfp_obj)
                self.db.flush()

                # Stage 2: Semantic / LLM reasoning
                system_logger.add_log("INFO", f"[LLMReasoner] Evaluating alignment against EAI/PhantomOps KB for RFP: '{rfp_data['title'][:40]}'")
                eval_res = await self.reasoner.evaluate_rfp(rfp_data)
                stats["evaluated"] += 1

                score = eval_res.get("relevance_score", 0)
                rec = eval_res.get("recommendation", "PASS")
                system_logger.add_log("SUCCESS", f"[LLMReasoner] Score: {score}% ({rec}) for '{rfp_data['title'][:40]}'")

                eval_obj = RFPExecutionEvaluation(
                    rfp_id=rfp_obj.id,
                    relevance_score=score,
                    is_relevant=eval_res.get("is_relevant", False),
                    why_relevant=eval_res.get("why_relevant", ""),
                    eai_deliverables=eval_res.get("eai_deliverables", []),
                    missing_requirements=eval_res.get("missing_requirements", []),
                    ai_summary=eval_res.get("ai_summary", ""),
                    recommendation=rec
                )
                self.db.add(eval_obj)
                self.db.commit()

                if rec == "PURSUE":
                    stats["pursued"] += 1

                # Dispatch email alert if score >= threshold
                if eval_res.get("is_relevant"):
                    system_logger.add_log("INFO", f"[EmailService] Dispatching alert email to rfp-alerts@eaisystems.com...")
                    sent = self.email_service.send_opportunity_alert(rfp_data, eval_res)
                    if sent:
                        stats["emails_sent"] += 1

        system_logger.add_log("SUCCESS", f"[Pipeline] Pipeline run completed. Total Scraped: {stats['scraped']} | Evaluated: {stats['evaluated']} | Pursued: {stats['pursued']}")
        return stats
