import json
import httpx
import asyncio
from typing import Dict, Any, List
from config import settings
from src.intelligence.graph_state import RFPState
from src.services.logger_service import system_logger

class QuotaExceededException(Exception):
    """Raised when an LLM provider returns HTTP 429 / Quota Exhausted."""
    pass

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

async def query_llm_json(prompt: str, system_prompt: str) -> Dict[str, Any]:
    """Helper to query Groq or Gemini with structured JSON output and rate-limit circuit breakers."""
    api_key = settings.GROQ_API_KEY
    model = settings.GROQ_MODEL

    if api_key and settings.LLM_PROVIDER != "gemini":
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                for attempt in range(3):
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.2,
                            "max_tokens": 600,
                            "response_format": {"type": "json_object"}
                        }
                    )
                    if resp.status_code == 200:
                        content = resp.json()["choices"][0]["message"]["content"]
                        return json.loads(content)
                    elif resp.status_code == 429:
                        retry_after = float(resp.headers.get("retry-after", 3.0))
                        if attempt < 2:
                            await asyncio.sleep(retry_after)
                            continue
                        break
                    else:
                        break
        except Exception as e:
            system_logger.add_log("WARN", f"[Agents] Groq LLM query warning: {e}")

    # Fallback to Gemini if configured or Groq failed
    gemini_key = settings.GEMINI_API_KEY
    if gemini_key:
        gemini_model = getattr(settings, "GEMINI_MODEL", "gemini-3.6-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={gemini_key}"
        full_prompt = f"{system_prompt}\n\n{prompt}\nRespond strictly in valid JSON."
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"}
        }
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    text_content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(text_content)
                elif resp.status_code == 429 or "RESOURCE_EXHAUSTED" in resp.text:
                    raise QuotaExceededException("Google Gemini API Quota Exceeded (HTTP 429).")
        except QuotaExceededException:
            raise
        except Exception as e:
            system_logger.add_log("WARN", f"[Agents] Gemini LLM query warning: {e}")

    return {}

async def route_domain(state: RFPState) -> RFPState:
    """
    Node 1: Domain Router Agent
    Classifies the RFP notice.
    Constraint: Explicitly returns "reject" for supplier profiles, DPS directories,
    expired contracts, or physical non-IT hardware/facilities.
    Otherwise returns "eaisystems" or "phantomops".
    """
    title = state.get("title", "")
    raw_text = state.get("raw_text", "")
    pdf_text = state.get("pdf_extracted_text", "")
    combined = f"{title} {raw_text} {pdf_text}".lower()

    # 1. Deterministic Rejection Checks (Hardware & Non-IT)
    rejection_keywords = [
        "supplier profile", "supplier directory", "dps questionnaire", "dynamic purchasing system directory",
        "expired contract", "contract award notice", "historical award", "prior award notice",
        "air conditioner", "hvac", "laboratory equipment", "furniture", "tires", "car rental",
        "cleaning", "plumbing", "roofing", "vending", "gritting", "boiler", "painting", "construction"
    ]
    for kw in rejection_keywords:
        if kw in combined:
            system_logger.add_log("WARN", f"[Agent:Router] Explicit Rejection ('{kw}') for '{title[:40]}'")
            state["domain_route"] = "reject"
            state["rejection_reason"] = f"Filtered out non-opportunity item: matching '{kw}'."
            state["tech_score"] = 0
            state["recommendation"] = "PASS"
            state["is_relevant"] = False
            state["compliance_flags"] = [f"REJECTED: Contains '{kw}'"]
            state["eai_deliverables"] = []
            state["missing_requirements"] = ["Notice is not a viable active software RFP opportunity"]
            state["ai_summary"] = f"Notice '{title[:60]}' rejected (classified as supplier profile/expired/hardware)."
            return state

    # 1b. Deterministic Expired Year Rejection (Current Year: 2026)
    import re
    expired_years = ["2015", "2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025"]
    date_pattern = r"(response\s*date|deadline|published|due\s*date|closes|closing|updated\s*response\s*date|archive\s*date)[:\s]{1,30}([^\n\r,]{1,50})"
    date_matches = re.findall(date_pattern, combined, re.IGNORECASE)
    for kw, date_snippet in date_matches:
        for past_year in expired_years:
            if past_year in date_snippet:
                system_logger.add_log("WARN", f"[Agent:Router] Explicit Year Rejection ('{past_year}') for '{title[:40]}'")
                state["domain_route"] = "reject"
                state["rejection_reason"] = f"Expired contract: detected '{past_year}' in date '{date_snippet.strip()}'."
                state["tech_score"] = 0
                state["recommendation"] = "PASS"
                state["is_relevant"] = False
                state["compliance_flags"] = [f"REJECTED: Expired contract date ('{past_year}')"]
                state["eai_deliverables"] = []
                state["missing_requirements"] = ["Notice is an expired contract opportunity"]
                state["ai_summary"] = f"Notice '{title[:60]}' rejected (expired contract from {past_year})."
                return state

    # 2. LLM Router Prompt
    system_prompt = """You are an AI Procurement Classifier.
CRITICAL RULE: The current year is 2026. You MUST scan the text for 'Response Date', 'Deadline', 'Updated Response Date', or 'Closing Date'. If the deadline is in the years 2020, 2021, 2022, 2023, 2024, or 2025, you must INSTANTLY classify the route as 'reject' with the reason 'Expired contract'. Do not evaluate technical fit if the contract is expired.

Analyze the procurement notice and classify it strictly into ONE of the following 3 domain routes:
1. "reject": If the notice is an expired contract (past year 2020-2025), a supplier profile, DPS directory, vendor registration form, or non-IT hardware/civil work.
2. "phantomops": If the notice focuses on Sovereign AI, Agentic Workforces, Arabic NLP, BFSI AI compliance, or AI autonomous agents.
3. "eaisystems": If the notice focuses on Pega BPM, Low-Code DPA, Enterprise Integration, Microservices, Cloud Migration, or Core IT Systems.

Respond strictly in JSON with this structure:
{
  "domain_route": "reject" | "phantomops" | "eaisystems",
  "reasoning": "<short explanation>"
}"""

    user_prompt = f"Procurement Notice:\nTitle: {title}\nContent: {raw_text[:1500]}"

    try:
        res = await query_llm_json(user_prompt, system_prompt)
        route = res.get("domain_route", "").lower()
        if route in ["reject", "phantomops", "eaisystems"]:
            state["domain_route"] = route
            if route == "reject":
                state["rejection_reason"] = res.get("reasoning", "LLM classified notice as noise/non-RFP.")
                state["tech_score"] = 0
                state["recommendation"] = "PASS"
                state["is_relevant"] = False
                state["compliance_flags"] = ["REJECTED: LLM Classified as Non-Opportunity"]
                state["ai_summary"] = f"Notice '{title[:60]}' rejected by Router Agent."
                return state
    except QuotaExceededException:
        raise
    except Exception as e:
        system_logger.add_log("WARN", f"[Agent:Router] LLM classification error: {e}")

    # Fallback heuristic classification
    if any(k in combined for k in ["sovereign ai", "arabic", "agentic", "phantomops", "ai workforce"]):
        state["domain_route"] = "phantomops"
    else:
        state["domain_route"] = "eaisystems"

    system_logger.add_log("INFO", f"[Agent:Router] Routed '{title[:35]}' -> {state['domain_route']}")
    return state


async def evaluate_eai(state: RFPState) -> RFPState:
    """
    Node 2: EAI Systems Evaluator
    Evaluates RFP strictly against EAI Systems capabilities (Pega BPM, Cloud Migration, ESB).
    """
    title = state.get("title", "")
    raw_text = state.get("raw_text", "")

    system_prompt = f"""You are the Lead Solutions Architect for EAI Systems (https://eaisystems.com).
Evaluate this RFP strictly against EAI Systems verified capabilities:
{EAI_KNOWLEDGE_CONTEXT}

Respond strictly in JSON matching this schema:
{{
  "tech_score": <int 0-100>,
  "is_relevant": <bool>,
  "why_relevant": "<explanation>",
  "eai_deliverables": ["<matching EAI offerings>"],
  "missing_requirements": ["<requirements EAI lacks or needs partners for>"],
  "compliance_flags": ["<risk or compliance flags, e.g. UK Onshore Resource Required>"],
  "ai_summary": "<concise 2-sentence summary>",
  "recommendation": "<PURSUE | PASS | PARTNER | REVIEW>"
}}"""

    user_prompt = f"Evaluate RFP for EAI Systems:\nTitle: {title}\nContent: {raw_text[:2000]}"

    try:
        res = await query_llm_json(user_prompt, system_prompt)
        if res and "tech_score" in res:
            state["tech_score"] = int(res.get("tech_score", 50))
            state["is_relevant"] = bool(res.get("is_relevant", state["tech_score"] >= settings.MATCH_SCORE_THRESHOLD))
            state["why_relevant"] = str(res.get("why_relevant", "Matches EAI Systems enterprise integration practices."))
            state["eai_deliverables"] = list(res.get("eai_deliverables", []))
            state["missing_requirements"] = list(res.get("missing_requirements", []))
            state["compliance_flags"] = list(res.get("compliance_flags", []))
            state["ai_summary"] = str(res.get("ai_summary", ""))
            state["recommendation"] = str(res.get("recommendation", "REVIEW"))
            return state
    except QuotaExceededException:
        raise
    except Exception as e:
        system_logger.add_log("WARN", f"[Agent:EAI] LLM evaluation warning: {e}")

    # Fallback Heuristic
    combined = f"{title} {raw_text}".lower()
    score = 40
    rec = "REVIEW"
    deliverables = ["Digital Process Automation", "API Integration Services"]
    missing = ["Technical specification review required"]
    flags = ["Standard UK/EU Compliance Verification"]

    if any(k in combined for k in ["pega", "bpm", "case management", "dpa"]):
        score = 88
        rec = "PURSUE"
        deliverables = ["Pega Low-Code DPA Implementation", "Case Management Architecture", "Decisioning & Workflow Automation"]
        flags.append("Pega Certified Lead Architect Required")
    elif any(k in combined for k in ["cloud", "migration", "microservices", "integration", "aws", "azure"]):
        score = 75
        rec = "PURSUE"
        deliverables = ["Cloud Migration & Microservices Architecture", "API Gateway & ESB Integration"]

    state["tech_score"] = score
    state["is_relevant"] = score >= settings.MATCH_SCORE_THRESHOLD
    state["why_relevant"] = "Evaluated against EAI Systems Pega & Integration capability framework."
    state["eai_deliverables"] = deliverables
    state["missing_requirements"] = missing
    state["compliance_flags"] = flags
    state["ai_summary"] = f"EAI evaluation completed for '{title[:60]}'. Score: {score}%."
    state["recommendation"] = rec
    return state


async def evaluate_phantomops(state: RFPState) -> RFPState:
    """
    Node 3: PhantomOps Evaluator
    Evaluates RFP strictly against PhantomOps capabilities (Sovereign AI, Arabic-native AI, BFSI compliance).
    """
    title = state.get("title", "")
    raw_text = state.get("raw_text", "")

    system_prompt = f"""You are the Chief AI Officer for PhantomOps (https://phantomops.ae).
Evaluate this RFP strictly against PhantomOps verified capabilities:
{EAI_KNOWLEDGE_CONTEXT}

Respond strictly in JSON matching this schema:
{{
  "tech_score": <int 0-100>,
  "is_relevant": <bool>,
  "why_relevant": "<explanation>",
  "eai_deliverables": ["<matching PhantomOps Agentic AI offerings>"],
  "missing_requirements": ["<missing requirements or sovereign hosting needs>"],
  "compliance_flags": ["<compliance flags, e.g. CBUAE Regulatory Audit Required, Air-Gap Hosting Required>"],
  "ai_summary": "<concise 2-sentence summary>",
  "recommendation": "<PURSUE | PASS | PARTNER | REVIEW>"
}}"""

    user_prompt = f"Evaluate RFP for PhantomOps:\nTitle: {title}\nContent: {raw_text[:2000]}"

    try:
        res = await query_llm_json(user_prompt, system_prompt)
        if res and "tech_score" in res:
            state["tech_score"] = int(res.get("tech_score", 50))
            state["is_relevant"] = bool(res.get("is_relevant", state["tech_score"] >= settings.MATCH_SCORE_THRESHOLD))
            state["why_relevant"] = str(res.get("why_relevant", "Matches PhantomOps Sovereign Agentic AI capabilities."))
            state["eai_deliverables"] = list(res.get("eai_deliverables", []))
            state["missing_requirements"] = list(res.get("missing_requirements", []))
            state["compliance_flags"] = list(res.get("compliance_flags", []))
            state["ai_summary"] = str(res.get("ai_summary", ""))
            state["recommendation"] = str(res.get("recommendation", "REVIEW"))
            return state
    except QuotaExceededException:
        raise
    except Exception as e:
        system_logger.add_log("WARN", f"[Agent:PhantomOps] LLM evaluation warning: {e}")

    # Fallback Heuristic
    combined = f"{title} {raw_text}".lower()
    score = 85
    rec = "PURSUE"
    deliverables = ["PhantomOps Sovereign AI Agents", "Arabic-Native NLP & Automated Document Workflows"]
    missing = ["Air-gapped private cloud infrastructure validation"]
    flags = ["GCC / CBUAE Regulatory Compliance Flag", "Sovereign Data Residency Required"]

    state["tech_score"] = score
    state["is_relevant"] = score >= settings.MATCH_SCORE_THRESHOLD
    state["why_relevant"] = "Direct alignment with PhantomOps Sovereign Agentic AI Workforce platform."
    state["eai_deliverables"] = deliverables
    state["missing_requirements"] = missing
    state["compliance_flags"] = flags
    state["ai_summary"] = f"PhantomOps evaluation completed for '{title[:60]}'. Score: {score}%."
    state["recommendation"] = rec
    return state


async def generate_brief(state: RFPState) -> RFPState:
    """
    Node 4: Synthesis & 12-Question AI Brief Generator
    Synthesizes the evaluation data into the 12-Question AI Brief markdown format.
    """
    title = state.get("title", "Untitled RFP")
    tender_id = state.get("tender_id", "N/A")
    route = state.get("domain_route", "eaisystems").upper()
    score = state.get("tech_score", 0)
    rec = state.get("recommendation", "REVIEW")
    org = state.get("issuing_org", "Unknown Authority")
    summary = state.get("ai_summary", "Evaluation complete.")
    deliverables = "\n".join([f"- {d}" for d in state.get("eai_deliverables", [])]) or "- N/A"
    gaps = "\n".join([f"- {g}" for g in state.get("missing_requirements", [])]) or "- N/A"
    flags = "\n".join([f"- {f}" for f in state.get("compliance_flags", [])]) or "- None"

    brief_markdown = f"""# 📋 12-Question AI Executive RFP Brief

1. **Opportunity Title & ID**: {title} (ID: {tender_id})
2. **Target Domain Route**: `{route}`
3. **Technical Relevance Score**: {score}%
4. **Strategic Recommendation**: **{rec}**
5. **Executive Summary**: {summary}
6. **Primary Buyer / Issuing Authority**: {org}
7. **Core Matched Deliverables**:
{deliverables}
8. **Gaps & Missing Requirements**:
{gaps}
9. **Compliance & Risk Flags**:
{flags}
10. **Deployment & Sovereignty Model**: {"Air-Gapped Sovereign / On-Prem" if route == "PHANTOMOPS" else "Public / Hybrid Enterprise Cloud"}
11. **Required Certifications & Skillsets**: {"Pega Infinity Certified Lead Architect" if route == "EAISYSTEMS" else "Arabic NLP & Sovereign Agentic AI Architect"}
12. **Pursuit Strategy & Next Steps**: {"Initiate partner outreach & technical proposal deck" if rec in ["PURSUE", "PARTNER"] else "Monitor notice updates"}
"""

    state["final_brief"] = brief_markdown
    state["relevance_score"] = score
    system_logger.add_log("SUCCESS", f"[Agent:Synthesis] Synthesized 12-Question AI Brief for '{title[:35]}'")
    return state
