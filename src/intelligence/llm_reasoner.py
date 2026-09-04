import json
import re
import httpx
from typing import Dict, Any, Optional
from config import settings
from src.services.logger_service import system_logger

EAI_KNOWLEDGE_CONTEXT = """
Verified Corporate Knowledge Bases:

1. EAI Systems (https://eaisystems.com) - Enterprise Transformation & Low-Code Integration:
   - Certified Pega BPM & DPA Implementation: Enterprise Case Management, Pega Infinity, Decisioning, Customer Service, Low-Code Governance.
   - Enterprise Application Integration (EAI): Microservices architecture, OpenAPI/REST integrations, ESB, Cloud Migration (AWS, Azure, GCP), ERP & CRM orchestration.
   - Core Banking & Insurance Digital Transformation: Claims automation, onboarding workflows, policy administration modernizations.

2. PhantomOps (https://phantomops.ae) - Sovereign Agentic AI Workforce Platform:
   - Sovereign Arabic-Native Agentic AI Workforce: Multi-agent orchestration, LLM reasoning, autonomous enterprise tasks.
   - BFSI & Government Specialized AI Agents: KYC automation, regulatory compliance (CBUAE), fraud detection, claims decisioning, localized NLP.
   - Sovereign Deployment Models: On-premises, private cloud, air-gapped sovereign AI execution for government and banking security.

Operating Regions: GCC (UAE, KSA, Oman, Qatar), UK, US, EU, APAC.
Target Verticals: BFSI (Banking, Financial Services, Insurance), Public Sector, Telecom, Healthcare, Retail.
"""

SYSTEM_PROMPT = f"""
You are the Chief Enterprise Architect for EAI Systems (https://eaisystems.com) and PhantomOps (https://phantomops.ae).
Your task is to analyze procurement RFP notices and evaluate alignment against our verified capabilities.

{EAI_KNOWLEDGE_CONTEXT}

STRICT RULE: Only ground your evaluation on verified EAI/PhantomOps capabilities from eaisystems.com and phantomops.ae. Never hallucinate capabilities. If an RFP requires something EAI lacks (e.g. physical hardware, civil engineering, janitorial, lab equipment), explicitly tag it under missing_requirements.

You MUST respond strictly in valid JSON with this exact structure:
{{
  "relevance_score": <int 0-100>,
  "is_relevant": <bool>,
  "why_relevant": "<explanation>",
  "eai_deliverables": ["<list of specific EAI/PhantomOps offerings matching this RFP>"],
  "missing_requirements": ["<list of requirements EAI lacks or requires partners for>"],
  "ai_summary": "<concise 2-sentence executive summary>",
  "recommendation": "<PURSUE | PASS | PARTNER>"
}}
"""

class QuotaExceededException(Exception):
    """Raised when an LLM provider (Gemini or Groq) returns HTTP 429 Quota Exceeded / Rate Limit."""
    pass

class LLMOpportunityReasoner:
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL

    async def evaluate_with_gemini(self, title: str, raw_content: str) -> Optional[Dict[str, Any]]:
        gemini_key = settings.GEMINI_API_KEY
        if not gemini_key:
            return None

        gemini_model = getattr(settings, "GEMINI_MODEL", "gemini-3.6-flash")
        system_logger.add_log("INFO", f"[LLMReasoner] Querying Google Gemini API ({gemini_model}) with eaisystems.com & phantomops.ae grounding context...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={gemini_key}"
        prompt_text = f"{SYSTEM_PROMPT}\n\nEvaluate this procurement notice:\nTitle: {title}\nDetails: {raw_content}\nRespond strictly in valid JSON matching the schema."
        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    text_content = data["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = json.loads(text_content)
                    return parsed
                elif resp.status_code == 429 or "quota" in resp.text.lower() or "RESOURCE_EXHAUSTED" in resp.text:
                    system_logger.add_log("ERROR", "🛑 [LLMReasoner] Gemini API Quota Exceeded (HTTP 429 / Quota Exhausted)! Halting evaluations immediately.")
                    raise QuotaExceededException("Google Gemini API Quota / Rate Limit Exceeded (HTTP 429). Please verify API key plan.")
                else:
                    system_logger.add_log("WARN", f"[LLMReasoner] Gemini API returned HTTP {resp.status_code}: {resp.text[:150]}")
        except QuotaExceededException:
            raise
        except Exception as e:
            system_logger.add_log("ERROR", f"[LLMReasoner] Gemini API exception: {e}")
        return None

    async def evaluate_rfp(self, rfp_data: Dict[str, Any]) -> Dict[str, Any]:
        title = rfp_data.get("title", "")
        raw_content = rfp_data.get("raw_content", "")
        combined_text = f"{title} {raw_content}".lower()

        # 0. Hardware / Non-IT Rejection Check
        hardware_terms = ["air conditioner", "air conditioners", "hvac", "laboratory equipment", "lab equipment", "furniture", "tires", "car rental", "vehicle", "cleaning", "plumbing", "roofing", "vending", "gritting", "boiler", "painting", "construction"]
        if any(term in combined_text for term in hardware_terms):
            system_logger.add_log("WARN", f"[LLMReasoner] Direct Hardware Rejection for '{title[:40]}'")
            return {
                "relevance_score": 10,
                "is_relevant": False,
                "why_relevant": "Non-IT physical hardware or facilities requirement outside EAI Systems / PhantomOps core software domain.",
                "eai_deliverables": [],
                "missing_requirements": ["Requires physical hardware/facilities servicing"],
                "ai_summary": "Tender is for physical equipment/facilities services, not enterprise software or AI integration.",
                "recommendation": "PASS"
            }

        # Try Groq API if key is set
        if self.api_key and settings.LLM_PROVIDER != "gemini":
            try:
                system_logger.add_log("INFO", f"[LLMReasoner] Querying Groq API model ({self.model}) with eaisystems.com & phantomops.ae grounding context...")
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": f"Evaluate this procurement notice:\nTitle: {title}\nDetails: {raw_content}"}
                            ],
                            "temperature": 0.2,
                            "max_tokens": 600,
                            "response_format": {"type": "json_object"}
                        }
                    )

                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"]
                        parsed = json.loads(content)
                        return parsed
                    elif resp.status_code == 429:
                        system_logger.add_log("WARN", "⚠️ [LLMReasoner] Groq API Rate Limit Exceeded (HTTP 429). Attempting Gemini failover...")
                        gemini_res = await self.evaluate_with_gemini(title, raw_content)
                        if gemini_res:
                            return gemini_res
                        raise QuotaExceededException("Both Groq & Gemini API Quotas / Rate Limits Exceeded (HTTP 429). Evaluation run halted.")
                    else:
                        system_logger.add_log("WARN", f"[LLMReasoner] Groq API HTTP {resp.status_code}, attempting Gemini failover...")
                        gemini_res = await self.evaluate_with_gemini(title, raw_content)
                        if gemini_res:
                            return gemini_res
            except QuotaExceededException:
                raise
            except Exception as e:
                system_logger.add_log("ERROR", f"[LLMReasoner] Groq API error: {e}")

        # Try Google Gemini if configured as primary provider
        if settings.LLM_PROVIDER == "gemini":
            gemini_res = await self.evaluate_with_gemini(title, raw_content)
            if gemini_res:
                return gemini_res

        # Deterministic Heuristic Fallback
        system_logger.add_log("INFO", f"[LLMReasoner] Applying eaisystems.com & phantomops.ae heuristic matcher...")
        score = 40
        recommendation = "PASS"
        why = "Generic procurement item outside primary target criteria."
        deliverables = ["Digital Process Automation", "API Integration Services"]
        missing = ["Detailed technical specification review required"]

        if any(k in combined_text for k in ["pega", "bpm", "case management", "dpa"]):
            score = 88
            recommendation = "PURSUE"
            why = "Strong alignment with EAI Systems' Certified Pega BPM/DPA implementation practice (eaisystems.com)."
            deliverables = ["Pega Low-Code DPA Implementation", "Case Management Architecture", "Decisioning & Workflow Automation"]
            missing = ["Local UK onshore resource allocation confirmation"]

        elif any(k in combined_text for k in ["sovereign ai", "arabic ai", "agentic ai", "phantomops"]):
            score = 85
            recommendation = "PURSUE"
            why = "Direct alignment with PhantomOps Sovereign Agentic AI Workforce platform (phantomops.ae)."
            deliverables = ["PhantomOps Sovereign AI Agents", "Automated Workflow Bots", "NLP & Intelligent Document Processing"]
            missing = ["Private cloud air-gapped hosting requirements check"]

        elif any(k in combined_text for k in ["software", "cyber", "security", "cloud", "data", "automation"]):
            score = 55
            recommendation = "REVIEW"
            why = "Matches general EAI Systems domain but requires technical specification review (eaisystems.com)."
            deliverables = ["Enterprise Integration Services", "Microservices & Cloud API Architecture"]

        return {
            "relevance_score": score,
            "is_relevant": score >= settings.MATCH_SCORE_THRESHOLD,
            "why_relevant": why,
            "eai_deliverables": deliverables,
            "missing_requirements": missing,
            "ai_summary": f"Procurement opportunity '{title[:80]}' evaluated against eaisystems.com and phantomops.ae capability matrix. Score: {score}%.",
            "recommendation": recommendation
        }
