from typing import TypedDict, List, Optional, Any, Dict

class RFPState(TypedDict, total=False):
    """
    Shared State Object for the LangGraph RFP Intelligence Multi-Agent Workflow.
    """
    # Core Required State Keys
    tender_id: str
    raw_text: str
    pdf_extracted_text: str
    domain_route: str          # "reject" | "eaisystems" | "phantomops"
    tech_score: int
    compliance_flags: List[str]
    final_brief: str

    # Context & Additional Fields
    title: str
    issuing_org: str
    source_url: str
    relevance_score: int
    is_relevant: bool
    why_relevant: str
    eai_deliverables: List[str]
    missing_requirements: List[str]
    ai_summary: str
    recommendation: str        # "PURSUE" | "PASS" | "PARTNER" | "REVIEW"
    rejection_reason: str
    error_message: Optional[str]
