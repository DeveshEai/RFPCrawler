import json
import re
import asyncio
import httpx
from typing import Dict, Any, Optional
from config import settings
from src.services.logger_service import system_logger
from src.intelligence.graph_state import RFPState
from src.intelligence.agents import (
    route_domain,
    evaluate_eai,
    evaluate_phantomops,
    generate_brief,
    QuotaExceededException
)
from langgraph.graph import StateGraph, END

def select_next_node(state: RFPState) -> str:
    """Conditional edge routing decision function based on state['domain_route']."""
    route = state.get("domain_route", "eaisystems").lower()
    if route == "reject":
        return END
    elif route == "phantomops":
        return "evaluate_phantomops"
    else:
        return "evaluate_eai"

def build_rfp_graph():
    """Build and compile the LangGraph StateGraph workflow for RFP Intelligence."""
    graph_builder = StateGraph(RFPState)

    # 1. Add agent nodes
    graph_builder.add_node("route_domain", route_domain)
    graph_builder.add_node("evaluate_eai", evaluate_eai)
    graph_builder.add_node("evaluate_phantomops", evaluate_phantomops)
    graph_builder.add_node("generate_brief", generate_brief)

    # 2. Set entry point
    graph_builder.set_entry_point("route_domain")

    # 3. Add conditional routing edge from route_domain
    graph_builder.add_conditional_edges(
        "route_domain",
        select_next_node,
        {
            END: END,
            "evaluate_eai": "evaluate_eai",
            "evaluate_phantomops": "evaluate_phantomops"
        }
    )

    # 4. Connect evaluators to synthesis node (generate_brief)
    graph_builder.add_edge("evaluate_eai", "generate_brief")
    graph_builder.add_edge("evaluate_phantomops", "generate_brief")

    # 5. Connect synthesis node to END
    graph_builder.add_edge("generate_brief", END)

    return graph_builder.compile()

# Compile global LangGraph instance
rfp_langgraph_app = build_rfp_graph()

class LLMOpportunityReasoner:
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self.graph = rfp_langgraph_app

    async def evaluate_rfp(self, rfp_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the LangGraph Multi-Agent RFP Intelligence Workflow.
        """
        title = rfp_data.get("title", "")
        raw_content = rfp_data.get("raw_content", "") or title
        tender_id = str(rfp_data.get("external_rfp_id") or rfp_data.get("id") or "N/A")

        system_logger.add_log("INFO", f"[LangGraph] Invoking multi-agent state graph for RFP '{title[:40]}'")

        initial_state: RFPState = {
            "tender_id": tender_id,
            "title": title,
            "issuing_org": rfp_data.get("issuing_org", ""),
            "source_url": rfp_data.get("source_url", ""),
            "raw_text": raw_content,
            "pdf_extracted_text": rfp_data.get("pdf_text", ""),
            "domain_route": "",
            "tech_score": 0,
            "compliance_flags": [],
            "final_brief": ""
        }

        try:
            final_state = await self.graph.ainvoke(initial_state)

            score = final_state.get("tech_score", 0)
            rec = final_state.get("recommendation", "PASS")
            route = final_state.get("domain_route", "")

            system_logger.add_log(
                "SUCCESS" if score >= 50 else "WARN",
                f"[LangGraph] Completed execution for '{title[:35]}' -> Route: {route} | Score: {score}% ({rec})"
            )

            return {
                "relevance_score": score,
                "is_relevant": final_state.get("is_relevant", False),
                "why_relevant": final_state.get("why_relevant", final_state.get("rejection_reason", "Evaluated via LangGraph multi-agent workflow.")),
                "eai_deliverables": final_state.get("eai_deliverables", []),
                "missing_requirements": final_state.get("missing_requirements", []),
                "ai_summary": final_state.get("ai_summary", final_state.get("final_brief", "")[:300]),
                "recommendation": rec,
                "domain_route": route,
                "final_brief": final_state.get("final_brief", "")
            }
        except QuotaExceededException as qe:
            system_logger.add_log("ERROR", f"🛑 [LangGraph] Quota Exceeded Exception: {qe}")
            raise
        except Exception as e:
            system_logger.add_log("ERROR", f"[LangGraph] Error during graph execution: {e}")
            # Safe Fallback
            return {
                "relevance_score": 30,
                "is_relevant": False,
                "why_relevant": f"LangGraph execution exception fallback: {e}",
                "eai_deliverables": [],
                "missing_requirements": ["Manual review required due to execution exception"],
                "ai_summary": f"Evaluation incomplete for '{title[:60]}'.",
                "recommendation": "REVIEW",
                "domain_route": "error"
            }
