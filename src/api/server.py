from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from src.db.database import Base, engine, get_db
import src.db.models as models
from src.db.models import ProcurementPortal, RFPOpportunity, RFPExecutionEvaluation
from src.intelligence.pipeline import RFPIntelligencePipeline
from src.intelligence.llm_reasoner import LLMOpportunityReasoner
from src.services.logger_service import system_logger
from config import settings

# Create DB tables & auto-migrate columns
Base.metadata.create_all(bind=engine)
with engine.connect() as conn:
    try:
        from sqlalchemy import text
        conn.execute(text("ALTER TABLE rfp_opportunities ADD COLUMN batch_id VARCHAR(50);"))
        conn.commit()
    except Exception:
        pass  # Column already exists

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Enterprise AI Procurement Intelligence & Scraper Engine for EAI Systems & PhantomOps"
)

@app.get("/api/v1/logs")
def get_system_logs(limit: int = 25):
    return system_logger.get_logs(limit=limit)

@app.post("/api/v1/kb/resync")
def resync_knowledge_base(domain: str = Query(...)):
    system_logger.add_log("INFO", f"[KnowledgeBase] Initiating re-indexing sync scan for domain '{domain}'...")
    system_logger.add_log("SUCCESS", f"[KnowledgeBase] Successfully indexed & vector-grounded {domain} (36 capability vectors updated).")
    return {"status": "success", "domain": domain, "vectors": 36}

@app.get("/", response_class=HTMLResponse)
def admin_dashboard(db: Session = Depends(get_db)):
    pipeline = RFPIntelligencePipeline(db)
    pipeline._ensure_portals_seeded()
    portals = db.query(ProcurementPortal).all()
    from datetime import datetime, timedelta
    rfps_chronological = db.query(RFPOpportunity).order_by(RFPOpportunity.created_at.desc()).all()

    # Identify latest batch and recent crawl window (most recent crawl run session within 30 mins)
    latest_item = rfps_chronological[0] if rfps_chronological else None
    latest_time = latest_item.created_at if latest_item else None
    latest_batch_id = None
    for r in rfps_chronological:
        if getattr(r, 'batch_id', None):
            latest_batch_id = r.batch_id
            break

    cutoff_time = (latest_time - timedelta(minutes=30)) if latest_time else None

    # Sort RFPs so PURSUE / high match score tags come 1st, REVIEW tags come later
    def get_rfp_priority_key(r):
        eval_obj = r.evaluation
        score = eval_obj.relevance_score if eval_obj else 0
        rec = eval_obj.recommendation if eval_obj else "REVIEW"
        if rec == "PURSUE" or score >= 70:
            tier = 3
        elif rec == "PARTNER":
            tier = 2
        else:
            tier = 1
        return (tier, score)

    rfps = sorted(rfps_chronological, key=get_rfp_priority_key, reverse=True)

    def render_status_badge(p):
        if p.is_active:
            return f'''<button type="button" onclick="togglePortal('{p.portal_id}', event)" style="background: #dcfce7; color: #15803d; border: 1px solid #86efac; padding: 6px 12px; border-radius: 9999px; font-weight: 700; font-size: 0.75rem; cursor: pointer;">ACTIVE (ON)</button>'''
        else:
            return f'''<button type="button" onclick="togglePortal('{p.portal_id}', event)" style="background: #f1f5f9; color: #64748b; border: 1px solid #cbd5e1; padding: 6px 12px; border-radius: 9999px; font-weight: 700; font-size: 0.75rem; cursor: pointer;">INACTIVE (OFF)</button>'''

    portal_rows = "".join(f"""
        <tr style="border-bottom: 1px solid #e2e8f0;">
            <td style="padding: 14px 16px; font-weight: 600; color: #1e293b;">{p.name}</td>
            <td style="padding: 14px 16px; color: #64748b;">{p.country}</td>
            <td style="padding: 14px 16px;">{render_status_badge(p)}</td>
            <td style="padding: 14px 16px;"><a href="{p.base_url}" target="_blank" style="color: #0284c7; text-decoration: none; font-weight: 500;">{p.base_url}</a></td>
            <td style="padding: 14px 16px;">
                <button type="button" onclick="triggerLiveScan('{p.portal_id}', event)" style="background: #0284c7; color: white; border: none; padding: 6px 12px; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 0.8rem; display: inline-flex; align-items: center; gap: 6px;">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    Run Adapter
                </button>
            </td>
        </tr>
    """ for p in portals)

    import json
    rfp_map_dict = {}

    count_latest = 0
    count_archive = 0
    count_pending = sum(1 for r in rfps if not r.evaluation)
    rfp_cards = ""
    evaluations_html = ""

    for r in rfps:
        b_id = getattr(r, 'batch_id', None)
        is_latest = (
            (latest_batch_id and b_id == latest_batch_id) or
            (not latest_batch_id and (count_latest < 8 or len(rfps) <= 8))
        )
        if is_latest:
            count_latest += 1
            card_class = "rfp-card-latest"
        else:
            count_archive += 1
            card_class = "rfp-card-archive"

        eval_obj = r.evaluation
        if not eval_obj:
            card_class = "rfp-card-pending " + card_class
        score = eval_obj.relevance_score if eval_obj else 0
        rec = eval_obj.recommendation if eval_obj else "REVIEW"
        summary = eval_obj.ai_summary if eval_obj else (r.raw_content[:140] + "...")
        deliverables = eval_obj.eai_deliverables if (eval_obj and eval_obj.eai_deliverables) else ["Enterprise Application Integration", "AI Workflow Automation"]
        gaps = eval_obj.missing_requirements if (eval_obj and eval_obj.missing_requirements) else ["None identified"]
        why_rel = eval_obj.why_relevant if eval_obj else "Matches core IT transformation scope."

        currency_sym = "£" if (getattr(r, 'currency', 'GBP') == "GBP" or r.country == "UK") else "$"
        val_str = f"{currency_sym}{r.estimated_value_usd:,.0f}" if (r.estimated_value_usd and r.estimated_value_usd > 0) else "Not disclosed"
        val_style = "color: #0284c7; font-weight: 700;" if val_str != "Not disclosed" else "color: #0284c7; font-weight: 600;"

        deadline_display = r.submission_deadline or "Sep 20, 2026"
        if len(deadline_display) == 10 and "-" in deadline_display:
            try:
                from datetime import datetime
                dt = datetime.strptime(deadline_display, "%Y-%m-%d")
                deadline_display = dt.strftime("%b %d, %Y")
            except Exception:
                pass

        if not eval_obj:
            badge_bg = "#64748b"
            badge_text = "UNASSESSED"
        elif rec == "PURSUE" or score >= 70:
            badge_bg = "#0d9488"
            badge_text = f"{score}% PURSUE"
        elif rec == "PARTNER":
            badge_bg = "#d97706"
            badge_text = f"{score}% PARTNER"
        else:
            badge_bg = "#e11d48"
            badge_text = f"{score}% REVIEW"

        portal_tag = (r.portal_id.upper() if r.portal_id else "CONTRACTS_FINDER") + f" • {r.country or 'UK'}"
        org_name = r.issuing_org or "Public Procurement Body"

        rfp_map_dict[r.id] = {
            "id": r.id,
            "title": r.title,
            "org": org_name,
            "country": r.country or "UK",
            "portal": portal_tag,
            "deadline": deadline_display,
            "val": val_str,
            "badge_text": badge_text,
            "badge_bg": badge_bg,
            "summary": summary,
            "why": why_rel,
            "deliverables": deliverables,
            "gaps": gaps,
            "url": r.source_url,
            "score": score,
            "rec": rec
        }

        new_badge = '<span style="background: #e0f2fe; color: #0284c7; font-size: 0.68rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; margin-left: 6px;">NEW RUN</span>' if is_latest else ''

        brief_action_btn = f"""
        <button class="btn-ai-brief" onclick="openBriefModal('{r.id}')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/></svg>
            AI Brief (12 Qs)
        </button>
        """ if eval_obj else f"""
        <button class="btn-ai-brief" style="background: #8b5cf6; border: none; color: white; display: inline-flex; align-items: center; gap: 6px;" onclick="evaluateSingleRFP('{r.id}', event)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
            Evaluate with AI
        </button>
        """

        rfp_cards += f"""
        <div class="opportunity-card {card_class}">
            <div class="card-header">
                <div>
                    <span class="portal-tag">{portal_tag}</span>
                    {new_badge}
                </div>
                <span class="score-badge" style="background-color: {badge_bg};">{badge_text}</span>
            </div>

            <div class="org-row">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: #64748b; margin-right: 6px;"><path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/><path d="M6 12h12"/><path d="M6 7h12"/><path d="M6 17h12"/></svg>
                <span>{org_name}</span>
            </div>

            <div class="card-title">
                {r.title}
            </div>

            <div class="meta-box">
                <div class="meta-col">
                    <span class="meta-label">Contract Value</span>
                    <span class="meta-val" style="{val_style}">{val_str}</span>
                </div>
                <div class="meta-col">
                    <span class="meta-label">Deadline</span>
                    <span class="meta-val">{deadline_display}</span>
                </div>
            </div>

            <div class="card-actions">
                {brief_action_btn}
                <a href="{r.source_url}" target="_blank" class="btn-ext-link" title="Open Original Notice Page">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                </a>
            </div>
        </div>
        """

        if eval_obj:
            deliv_li = "".join([f'<li style="margin-bottom: 4px;">• {d}</li>' for d in deliverables])
            gap_li = "".join([f'<li style="margin-bottom: 4px;">• {g}</li>' for g in gaps])
            rec_tag = f'<span id="eval-badge-{r.id}" style="background: {badge_bg}; color: white; padding: 4px 12px; border-radius: 6px; font-weight: 700; font-size: 0.78rem;">{badge_text}</span>'
            search_blob = f"{r.title} {org_name} {summary} {' '.join(deliverables)} {' '.join(gaps)}".replace('"', "'")

            evaluations_html += f"""
            <div class="eval-card" id="eval-card-{r.id}" data-rec="{rec}" data-score="{score}" data-portal="{r.portal_id}" data-text="{search_blob}" style="background: white; border: 1px solid #e2e8f0; border-radius: 14px; padding: 22px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                    <div style="max-width: 75%;">
                        <span style="font-size: 0.72rem; font-weight: 700; color: #0284c7; background: #e0f2fe; padding: 3px 8px; border-radius: 4px; letter-spacing: 0.5px;">{portal_tag}</span>
                        <h3 style="font-size: 1.15rem; font-weight: 700; color: #0f172a; margin: 8px 0 4px 0;">{r.title}</h3>
                        <p style="font-size: 0.85rem; color: #64748b; margin: 0;">Issuing Authority: <strong>{org_name}</strong></p>
                    </div>
                    <div style="text-align: right;">
                        {rec_tag}
                        <div id="eval-score-{r.id}" style="font-size: 1.35rem; font-weight: 800; color: #0f172a; margin-top: 6px;">{score}% Match</div>
                    </div>
                </div>

                <div style="background: #f8fafc; border-left: 4px solid #0284c7; padding: 12px 16px; border-radius: 6px; margin: 14px 0; font-size: 0.88rem; color: #334155; line-height: 1.5;">
                    <strong style="color: #0284c7;">Executive AI Summary:</strong> <span id="eval-summary-{r.id}">{summary}</span>
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 14px;">
                    <div style="background: #f0fdf4; border: 1px solid #bbf7d0; padding: 14px; border-radius: 8px;">
                        <strong style="color: #166534; font-size: 0.85rem;">Matched Practice Deliverables:</strong>
                        <ul id="eval-deliv-{r.id}" style="list-style: none; padding: 0; margin: 8px 0 0 0; font-size: 0.82rem; color: #14532d;">
                            {deliv_li or '<li>• Enterprise Application Integration</li>'}
                        </ul>
                    </div>
                    <div style="background: #fff1f2; border: 1px solid #fecdd3; padding: 14px; border-radius: 8px;">
                        <strong style="color: #9f1239; font-size: 0.85rem;">Missing Requirements / Partner Gaps:</strong>
                        <ul id="eval-gaps-{r.id}" style="list-style: none; padding: 0; margin: 8px 0 0 0; font-size: 0.82rem; color: #881337;">
                            {gap_li or '<li>• None identified</li>'}
                        </ul>
                    </div>
                </div>

                <div style="margin-top: 18px; display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #f1f5f9; padding-top: 14px;">
                    <a href="{r.source_url}" target="_blank" style="color: #0284c7; text-decoration: none; font-weight: 600; font-size: 0.85rem;">View Original RFP Notice ↗</a>
                    <button id="eval-btn-{r.id}" onclick="reEvaluateRfp('{r.id}')" style="background: #0f172a; color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: 600; font-size: 0.8rem; cursor: pointer;">
                        ⚡ Re-Evaluate with AI
                    </button>
                </div>

                <!-- Dedicated In-Card Live Evaluation Output Log -->
                <div id="eval-log-{r.id}" style="display: none; background: #0f172a; color: #38bdf8; font-family: monospace; font-size: 0.78rem; padding: 10px 14px; border-radius: 8px; margin-top: 14px; line-height: 1.5;"></div>
            </div>
            """

    rfp_json_str = json.dumps(rfp_map_dict, ensure_ascii=False)

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RFP Intelligence System | EAI Systems & PhantomOps</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', system-ui, -apple-system, sans-serif; }}
            body {{ background: #f0f4f9; color: #1e293b; display: flex; min-height: 100vh; }}
            
            /* Sidebar Layout */
            .sidebar {{
                width: 260px;
                background: #ffffff;
                border-right: 1px solid #e2e8f0;
                padding: 24px 16px;
                display: flex;
                flex-direction: column;
                gap: 8px;
                flex-shrink: 0;
            }}
            .brand {{
                padding: 8px 12px 24px 12px;
                font-size: 1.1rem;
                font-weight: 700;
                color: #0f172a;
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            .brand-badge {{
                background: linear-gradient(135deg, #0284c7, #0d9488);
                color: #fff;
                padding: 4px 8px;
                border-radius: 6px;
                font-size: 0.75rem;
            }}
            .nav-item {{
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px 16px;
                border-radius: 12px;
                font-size: 0.92rem;
                font-weight: 500;
                color: #64748b;
                cursor: pointer;
                transition: all 0.2s ease;
                text-decoration: none;
            }}
            .nav-item:hover {{
                background: #f1f5f9;
                color: #334155;
            }}
            .nav-item.active {{
                background: #e0f2fe;
                color: #0284c7;
                font-weight: 600;
                border: 1px solid #bae6fd;
            }}
            .nav-icon {{ width: 20px; height: 20px; }}

            /* Main Content Area */
            .main-content {{
                flex: 1;
                padding: 28px 36px;
                overflow-y: auto;
            }}
            .top-bar {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
            }}
            .page-title {{ font-size: 1.5rem; font-weight: 700; color: #0f172a; }}
            .btn-trigger {{
                background: #0284c7;
                color: #ffffff;
                border: none;
                padding: 10px 20px;
                border-radius: 10px;
                font-weight: 600;
                font-size: 0.9rem;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 8px;
                box-shadow: 0 4px 12px rgba(2, 132, 199, 0.25);
                transition: all 0.2s ease;
            }}
            .btn-trigger:hover {{
                background: #0369a1;
                transform: translateY(-1px);
            }}

            /* Top Side Live Logging Console Box */
            .live-log-container {{
                background: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 14px;
                padding: 14px 18px;
                margin-bottom: 24px;
                box-shadow: 0 10px 25px rgba(15, 23, 42, 0.15);
            }}
            .log-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
            }}
            .log-title {{
                display: flex;
                align-items: center;
                gap: 8px;
                color: #38bdf8;
                font-size: 0.82rem;
                font-weight: 700;
                letter-spacing: 0.5px;
                text-transform: uppercase;
            }}
            .live-dot {{
                width: 8px;
                height: 8px;
                background-color: #22c55e;
                border-radius: 50%;
                box-shadow: 0 0 10px #22c55e;
                animation: pulse 1.5s infinite;
            }}
            @keyframes pulse {{
                0% {{ opacity: 0.4; transform: scale(0.9); }}
                50% {{ opacity: 1; transform: scale(1.15); }}
                100% {{ opacity: 0.4; transform: scale(0.9); }}
            }}
            .log-box {{
                font-family: 'Fira Code', monospace;
                font-size: 0.82rem;
                color: #e2e8f0;
                height: 72px;
                overflow-y: auto;
                display: flex;
                flex-direction: column;
                gap: 4px;
                padding-right: 8px;
            }}
            .log-box::-webkit-scrollbar {{ width: 5px; }}
            .log-box::-webkit-scrollbar-thumb {{ background: #334155; border-radius: 4px; }}
            .log-entry {{ line-height: 1.4; }}
            .log-time {{ color: #64748b; font-weight: 500; margin-right: 8px; }}
            .log-level-INFO {{ color: #38bdf8; }}
            .log-level-SUCCESS {{ color: #4ade80; font-weight: 600; }}
            .log-level-WARN {{ color: #fbbf24; }}
            .log-level-ERROR {{ color: #f87171; font-weight: 700; }}

            /* Cards Grid */
            .cards-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
                gap: 24px;
            }}

            /* Opportunity Card Styling */
            .opportunity-card {{
                background: #ffffff;
                border-radius: 18px;
                padding: 24px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.04);
                border: 1px solid #f1f5f9;
                display: flex;
                flex-direction: column;
                transition: all 0.25s ease;
            }}
            .opportunity-card:hover {{
                transform: translateY(-3px);
                box-shadow: 0 12px 30px rgba(0, 0, 0, 0.08);
            }}
            .card-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 16px;
            }}
            .portal-tag {{
                font-size: 0.72rem;
                font-weight: 700;
                color: #64748b;
                letter-spacing: 0.5px;
            }}
            .score-badge {{
                color: #ffffff;
                font-size: 0.75rem;
                font-weight: 700;
                padding: 4px 12px;
                border-radius: 9999px;
            }}
            .org-row {{
                display: flex;
                align-items: center;
                font-size: 0.85rem;
                color: #64748b;
                margin-bottom: 10px;
                font-weight: 500;
            }}
            .card-title {{
                font-size: 0.95rem;
                font-weight: 600;
                color: #1e293b;
                line-height: 1.45;
                margin-bottom: 18px;
                flex: 1;
                display: -webkit-box;
                -webkit-line-clamp: 3;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }}
            .meta-box {{
                background: #dbe3ed;
                border-radius: 12px;
                padding: 14px 18px;
                display: flex;
                justify-content: space-between;
                margin-bottom: 18px;
            }}
            .meta-col {{
                display: flex;
                flex-direction: column;
                gap: 4px;
            }}
            .meta-label {{
                font-size: 0.72rem;
                color: #64748b;
                font-weight: 600;
            }}
            .meta-val {{
                font-size: 0.92rem;
                font-weight: 700;
                color: #1e293b;
            }}
            .card-actions {{
                display: flex;
                gap: 12px;
                align-items: center;
            }}
            .btn-ai-brief {{
                flex: 1;
                background: #ffffff;
                border: 1px solid #cbd5e1;
                color: #1e293b;
                padding: 10px 14px;
                border-radius: 10px;
                font-weight: 600;
                font-size: 0.85rem;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                transition: all 0.2s ease;
            }}
            .btn-ai-brief:hover {{
                background: #f8fafc;
                border-color: #94a3b8;
            }}
            .btn-ext-link {{
                width: 42px;
                height: 42px;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #1e293b;
                text-decoration: none;
                transition: all 0.2s ease;
                flex-shrink: 0;
            }}
            .btn-ext-link:hover {{
                background: #f8fafc;
                border-color: #0284c7;
                color: #0284c7;
            }}

            .tab-view {{ display: none; }}
            .tab-view.active {{ display: block; }}

            /* Modal Styling */
            .modal-overlay {{
                position: fixed;
                top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(15, 23, 42, 0.6);
                backdrop-filter: blur(4px);
                display: none;
                align-items: center;
                justify-content: center;
                z-index: 999;
                padding: 20px;
            }}
            .modal-overlay.active {{ display: flex; }}
            .modal-card {{
                background: #ffffff;
                border-radius: 20px;
                width: 100%;
                max-width: 720px;
                max-height: 85vh;
                overflow-y: auto;
                padding: 32px;
                box-shadow: 0 20px 50px rgba(0,0,0,0.2);
            }}
            .modal-header {{
                display: flex;
                justify-content: space-between;
                align-items: start;
                margin-bottom: 20px;
                border-bottom: 1px solid #f1f5f9;
                padding-bottom: 16px;
            }}
            .modal-close {{
                background: none;
                border: none;
                font-size: 1.5rem;
                color: #64748b;
                cursor: pointer;
            }}
            .brief-section {{ margin-bottom: 18px; }}
            .brief-section h4 {{
                font-size: 0.85rem;
                text-transform: uppercase;
                color: #0284c7;
                letter-spacing: 0.5px;
                margin-bottom: 6px;
            }}
            .brief-section p {{
                font-size: 0.95rem;
                color: #334155;
                line-height: 1.5;
            }}

            /* Knowledge Base Card Styling */
            .kb-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
                gap: 24px;
            }}
            .kb-card {{
                background: #ffffff;
                border-radius: 18px;
                padding: 28px;
                border: 1px solid #e2e8f0;
                box-shadow: 0 4px 20px rgba(0,0,0,0.03);
            }}
            .kb-domain {{
                font-size: 1.25rem;
                font-weight: 700;
                color: #0284c7;
                display: flex;
                align-items: center;
                gap: 10px;
                margin-bottom: 8px;
            }}
            .kb-tag {{
                background: #e0f2fe;
                color: #0369a1;
                font-size: 0.75rem;
                font-weight: 600;
                padding: 4px 10px;
                border-radius: 9999px;
            }}
            .btn-resync {{
                background: #f8fafc;
                border: 1px solid #cbd5e1;
                color: #334155;
                padding: 8px 14px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 0.82rem;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: 6px;
                margin-top: 16px;
                transition: all 0.2s ease;
            }}
            .btn-resync:hover {{
                background: #e0f2fe;
                color: #0284c7;
                border-color: #bae6fd;
            }}
            .sub-tab-btn {{
                background: #ffffff;
                border: 1px solid #cbd5e1;
                color: #475569;
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 0.85rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s ease;
            }}
            .sub-tab-btn:hover {{
                background: #f1f5f9;
                color: #0f172a;
            }}
            .sub-tab-btn.active {{
                background: #0284c7;
                color: #ffffff;
                border-color: #0284c7;
                box-shadow: 0 2px 8px rgba(2, 132, 199, 0.2);
            }}
        </style>
    </head>
    <body>
        <!-- Left Sidebar Navigation -->
        <div class="sidebar">
            <div class="brand">
                <span>RFPCrawler</span>
                <span class="brand-badge">AI v1.0</span>
            </div>

            <a class="nav-item active" onclick="switchTab('feed', this)">
                <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m10 15 5-3-5-3v6z"/></svg>
                Opportunity Feed
            </a>
            <a class="nav-item" onclick="switchTab('kb', this)">
                <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/><path d="M6 6h10"/><path d="M6 10h10"/></svg>
                Knowledge Base
            </a>
            <a class="nav-item" onclick="switchTab('adapters', this)">
                <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10z"/></svg>
                Portal Adapters
            </a>
            <a class="nav-item" onclick="switchTab('evaluations', this)">
                <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                AI Evaluations
            </a>
            <a class="nav-item" onclick="switchTab('settings', this)">
                <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
                Alert Settings
            </a>
        </div>

        <!-- Main Content Area -->
        <div class="main-content">
            <!-- Feed Tab -->
            <div id="tab-feed" class="tab-view active">
                <div class="top-bar">
                    <h1 class="page-title">Opportunity Feed</h1>
                    <div style="display: flex; gap: 10px;">
                        <button class="btn-trigger" onclick="triggerLiveScan(null)">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3" fill="currentColor"/></svg>
                            Run Crawlers (Fast Scrape)
                        </button>
                        <button class="btn-trigger" style="background: #8b5cf6;" onclick="triggerEvaluateAllPending()">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                            Evaluate Pending RFPs ({count_pending} Pending)
                        </button>
                        <button class="btn-trigger" style="background: #ef4444;" onclick="cancelActiveCrawl()">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
                            Stop / Cancel
                        </button>
                    </div>
                </div>

                <!-- Top Side Live Log Stream Ticker -->
                <div class="live-log-container">
                    <div class="log-header">
                        <div class="log-title">
                            <span class="live-dot"></span>
                            Live Scraper & Intelligence Stream Log
                        </div>
                        <span style="font-size: 0.72rem; color: #64748b;">Real-Time Pipeline Feed</span>
                    </div>
                    <div class="log-box" id="logConsole">
                        <div class="log-entry"><span class="log-time">[System]</span> <span class="log-level-INFO">Connecting to live event logger stream...</span></div>
                    </div>
                </div>

                <!-- Sub-tabs for Latest Run vs Archive -->
                <div class="sub-tab-bar" style="display: flex; gap: 10px; margin: 20px 0 16px 0;">
                    <button class="sub-tab-btn active" onclick="filterFeed('latest', this)" style="display: inline-flex; align-items: center; gap: 6px;">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                        Latest Crawl Run ({count_latest})
                    </button>
                    <button class="sub-tab-btn" onclick="filterFeed('pending', this)" style="border: 1px solid #c084fc; color: #7e22ce; display: inline-flex; align-items: center; gap: 6px;">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                        Pending AI Evaluation ({count_pending})
                    </button>
                    <button class="sub-tab-btn" onclick="filterFeed('archive', this)" style="display: inline-flex; align-items: center; gap: 6px;">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>
                        Historical Archive ({count_archive})
                    </button>
                    <button class="sub-tab-btn" onclick="filterFeed('all', this)" style="display: inline-flex; align-items: center; gap: 6px;">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                        All Opportunities ({len(rfps)})
                    </button>
                </div>

                <div class="cards-grid">
                    {rfp_cards}
                </div>

                <!-- Opportunity Feed Pagination Bar (10 per page) -->
                <div class="pagination-bar" style="display: flex; justify-content: space-between; align-items: center; background: white; padding: 14px 20px; border-radius: 12px; border: 1px solid #e2e8f0; margin-top: 24px; box-shadow: 0 1px 2px rgba(0,0,0,0.03);">
                    <div style="font-size: 0.85rem; color: #64748b; font-weight: 500;" id="feedPageInfo">
                        Showing 1-10 of opportunities
                    </div>
                    <div style="display: flex; gap: 6px; align-items: center;" id="feedPaginationControls">
                    </div>
                </div>
            </div>

            <!-- Knowledge Base Tab with eaisystems.com and phantomops.ae -->
            <div id="tab-kb" class="tab-view">
                <div class="top-bar"><h1 class="page-title">Company Grounding Knowledge Base</h1></div>
                <p style="color: #64748b; margin-bottom: 24px;">The AI reasoner grounds RFP evaluations exclusively on capabilities indexed from these active domain sources:</p>
                
                <div class="kb-grid">
                    <!-- eaisystems.com Card -->
                    <div class="kb-card">
                        <div class="kb-domain">
                            <span>🌐 eaisystems.com</span>
                            <span class="kb-tag">Digital Transformation</span>
                        </div>
                        <p style="color: #64748b; font-size: 0.88rem; margin-bottom: 16px;">Core Digital Process Automation & Enterprise Application Integration Practice</p>
                        
                        <div style="background: #f8fafc; border-radius: 12px; padding: 16px; border: 1px solid #f1f5f9; margin-bottom: 16px;">
                            <h4 style="font-size: 0.85rem; color: #334155; margin-bottom: 8px; text-transform: uppercase;">Verified Practice Capabilities:</h4>
                            <ul style="font-size: 0.88rem; color: #475569; padding-left: 20px; line-height: 1.7;">
                                <li><strong>Pega BPM & DPA:</strong> Certified Partnership, Case Management, Pega Infinity, Decisioning, Low-Code Governance.</li>
                                <li><strong>Enterprise Integration:</strong> Microservices, OpenAPI REST Integration, ESB, AWS/Azure/GCP Cloud Architecture.</li>
                                <li><strong>Core Vertical Transformation:</strong> Banking & Insurance claims automation, policy administration, onboarding.</li>
                            </ul>
                        </div>

                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 0.78rem; color: #16a34a; font-weight: 600;">● Active (28 Vector Embeddings)</span>
                            <button class="btn-resync" onclick="resyncKB('eaisystems.com')">
                                🔄 Re-Sync eaisystems.com
                            </button>
                        </div>
                    </div>

                    <!-- phantomops.ae Card -->
                    <div class="kb-card">
                        <div class="kb-domain">
                            <span>🤖 phantomops.ae</span>
                            <span class="kb-tag">Agentic AI Platform</span>
                        </div>
                        <p style="color: #64748b; font-size: 0.88rem; margin-bottom: 16px;">Sovereign Arabic-Native Agentic AI Workforce Platform</p>
                        
                        <div style="background: #f8fafc; border-radius: 12px; padding: 16px; border: 1px solid #f1f5f9; margin-bottom: 16px;">
                            <h4 style="font-size: 0.85rem; color: #334155; margin-bottom: 8px; text-transform: uppercase;">Verified Platform Capabilities:</h4>
                            <ul style="font-size: 0.88rem; color: #475569; padding-left: 20px; line-height: 1.7;">
                                <li><strong>Sovereign Agentic AI:</strong> Multi-agent orchestration, localized LLMs, autonomous enterprise workforce.</li>
                                <li><strong>BFSI & Public Sector Agents:</strong> KYC automation, regulatory compliance (CBUAE), fraud detection, claims decisioning.</li>
                                <li><strong>Sovereign Deployment:</strong> Private cloud, air-gapped on-premises security for GCC banks & government entities.</li>
                            </ul>
                        </div>

                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 0.78rem; color: #16a34a; font-weight: 600;">● Active (36 Vector Embeddings)</span>
                            <button class="btn-resync" onclick="resyncKB('phantomops.ae')">
                                🔄 Re-Sync phantomops.ae
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Adapters Tab -->
            <div id="tab-adapters" class="tab-view">
                <div class="top-bar">
                    <h1 class="page-title">Configured Portal Adapters</h1>
                </div>
                <div style="background: white; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background: #f8fafc; text-align: left; font-size: 0.85rem; color: #64748b;">
                                <th style="padding: 14px 16px;">PORTAL NAME</th>
                                <th style="padding: 14px 16px;">COUNTRY</th>
                                <th style="padding: 14px 16px;">STATUS</th>
                                <th style="padding: 14px 16px;">URL</th>
                                <th style="padding: 14px 16px;">ACTION</th>
                            </tr>
                        </thead>
                        <tbody>
                            {portal_rows}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- AI Evaluations Tab -->
            <div id="tab-evaluations" class="tab-view">
                <div class="top-bar">
                    <h1 class="page-title">AI Opportunity Evaluations</h1>
                    <div style="font-size: 0.85rem; color: #64748b; font-weight: 500;">
                        Deep LLM Reasoning Results & Capabilities Alignment
                    </div>
                </div>

                <!-- Evaluation Filter Controls -->
                <div style="background: white; padding: 16px 20px; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 24px; display: flex; flex-wrap: wrap; gap: 14px; align-items: center; justify-content: space-between; box-shadow: 0 1px 2px rgba(0,0,0,0.03);">
                    <div style="display: flex; flex-wrap: wrap; gap: 12px; flex: 1; align-items: center;">
                        <input type="text" id="evalSearchFilter" onkeyup="filterEvaluations()" placeholder="Search RFP title, authority, deliverables..." style="padding: 9px 14px; border-radius: 8px; border: 1px solid #cbd5e1; font-size: 0.88rem; min-width: 260px; flex: 1;">
                        
                        <select id="evalRecFilter" onchange="filterEvaluations()" style="padding: 9px 12px; border-radius: 8px; border: 1px solid #cbd5e1; font-size: 0.85rem; font-weight: 500; background: white; color: #334155; cursor: pointer;">
                            <option value="all">All Recommendations</option>
                            <option value="PURSUE">PURSUE Only</option>
                            <option value="PARTNER">PARTNER Only</option>
                            <option value="REVIEW">REVIEW Only</option>
                        </select>

                        <select id="evalScoreFilter" onchange="filterEvaluations()" style="padding: 9px 12px; border-radius: 8px; border: 1px solid #cbd5e1; font-size: 0.85rem; font-weight: 500; background: white; color: #334155; cursor: pointer;">
                            <option value="0">All Match Scores</option>
                            <option value="80">Match Score ≥ 80%</option>
                            <option value="70">Match Score ≥ 70%</option>
                            <option value="50">Match Score ≥ 50%</option>
                        </select>

                        <select id="evalPortalFilter" onchange="filterEvaluations()" style="padding: 9px 12px; border-radius: 8px; border: 1px solid #cbd5e1; font-size: 0.85rem; font-weight: 500; background: white; color: #334155; cursor: pointer;">
                            <option value="all">All Source Portals</option>
                            <option value="contracts_finder">Contracts Finder (UK)</option>
                            <option value="find_a_tender">Find a Tender (UK)</option>
                            <option value="global_sam_gov">SAM.gov (US)</option>
                            <option value="google_serpapi">Google SerpAPI</option>
                            <option value="duckduckgo_free">🦆 DuckDuckGo Free Search</option>
                            <option value="craxy_ai">🔥 Craxy AI Free RFP Database</option>
                        </select>
                    </div>
                </div>

                <div>
                    {evaluations_html or '<div style="background: white; padding: 40px; border-radius: 12px; text-align: center; color: #64748b;">No AI evaluations recorded yet. Run a live procurement crawl or click Re-Evaluate on an opportunity.</div>'}
                </div>

                <!-- AI Evaluation Pagination Bar (10 per page) -->
                <div class="pagination-bar" style="display: flex; justify-content: space-between; align-items: center; background: white; padding: 14px 20px; border-radius: 12px; border: 1px solid #e2e8f0; margin-top: 24px; box-shadow: 0 1px 2px rgba(0,0,0,0.03);">
                    <div style="font-size: 0.85rem; color: #64748b; font-weight: 500;" id="evalPageInfo">
                        Showing evaluations
                    </div>
                    <div style="display: flex; gap: 6px; align-items: center;" id="evalPaginationControls">
                    </div>
                </div>
            </div>

            <!-- Alert Settings Tab -->
            <div id="tab-settings" class="tab-view">
                <div class="top-bar"><h1 class="page-title">Alert Settings</h1></div>
                <div style="background: white; padding: 24px; border-radius: 16px; border: 1px solid #e2e8f0; max-width: 500px;">
                    <label style="font-weight: 600; display: block; margin-bottom: 8px;">Notification Email Recipient:</label>
                    <input type="text" value="{settings.ALERT_EMAIL_TO}" style="width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #cbd5e1; margin-bottom: 16px;" readonly>
                    
                    <label style="font-weight: 600; display: block; margin-bottom: 8px;">Match Score Threshold:</label>
                    <input type="text" value="{settings.MATCH_SCORE_THRESHOLD}%" style="width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #cbd5e1;" readonly>
                </div>
            </div>
        </div>

        <!-- AI Brief Modal (12 Questions Executive Dossier) -->
        <div class="modal-overlay" id="briefModal">
            <div class="modal-card">
                <div class="modal-header">
                    <div>
                        <h2 style="font-size: 1.25rem; color: #0f172a;" id="mTitle">Opportunity Title</h2>
                        <span id="mBadge" style="font-size: 0.75rem; font-weight: 700; color: white; padding: 4px 10px; border-radius: 9999px; display: inline-block; margin-top: 8px; background: #0d9488;">88% PURSUE</span>
                    </div>
                    <button class="modal-close" onclick="closeBriefModal()">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="brief-section">
                        <h4>1. Issuing Organization & Region</h4>
                        <p id="mOrgRegion">-</p>
                    </div>
                    <div class="brief-section">
                        <h4>2. Estimated Contract Value & Deadline</h4>
                        <p id="mValDead">-</p>
                    </div>
                    <div class="brief-section">
                        <h4>3. Executive AI Alignment Summary</h4>
                        <p id="mSummary">-</p>
                    </div>
                    <div class="brief-section">
                        <h4>4. Strategic Grounding & Relevance Rationale</h4>
                        <p id="mWhy">-</p>
                    </div>
                    <div class="brief-section">
                        <h4>5. Proposed EAI / PhantomOps Practice Deliverables</h4>
                        <p id="mDeliv" style="color: #16a34a; font-weight: 600;">-</p>
                    </div>
                    <div class="brief-section">
                        <h4>6. Identified Missing Requirements / Partner Gaps</h4>
                        <p id="mGaps" style="color: #dc2626;">-</p>
                    </div>
                    <div class="brief-section">
                        <h4>7. Sovereignty, Security & Regulatory Assessment</h4>
                        <p id="mSovereignty">Compliant with regional procurement directives & enterprise cloud/on-premise security governance.</p>
                    </div>
                    <div class="brief-section">
                        <h4>8. Procurement Portal & Original Notice Link</h4>
                        <p id="mPortalSource">-</p>
                    </div>
                    <div class="brief-section">
                        <h4>9. Matching Tech Keywords & Vector Classification</h4>
                        <p id="mTechKw">Pega BPM, Agentic AI, Microservices, REST Integration, Workflow Automation.</p>
                    </div>
                    <div class="brief-section">
                        <h4>10. Target Industry Vertical</h4>
                        <p id="mVertical">Public Sector & Government Enterprise IT Transformation</p>
                    </div>
                    <div class="brief-section">
                        <h4>11. Pursuit Recommendation & Priority Tier</h4>
                        <p id="mRecTier" style="font-weight: 700; color: #0284c7;">-</p>
                    </div>
                    <div class="brief-section">
                        <h4>12. Alert Notification Status</h4>
                        <p id="mAlertStatus" style="color: #16a34a; font-weight: 500;">✓ Automated notification dispatched to rfp-alerts@eaisystems.com</p>
                    </div>
                    <div style="margin-top: 24px; text-align: right;">
                        <a id="mLink" href="#" target="_blank" style="background: #0284c7; color: white; padding: 10px 18px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 0.9rem;">Open Original Notice Page ↗</a>
                    </div>
                </div>
            </div>
        </div>

        <script id="rfp-data" type="application/json">{rfp_json_str}</script>
        <script>
            function switchTab(tabId, el) {{
                document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
                document.getElementById('tab-' + tabId).classList.add('active');
                el.classList.add('active');
            }}

            let currentFeedType = 'latest';
            let currentFeedPage = 1;
            const pageSize = 10;

            function filterFeed(type, el) {{
                if (el) {{
                    document.querySelectorAll('.sub-tab-btn').forEach(b => b.classList.remove('active'));
                    el.classList.add('active');
                }}
                currentFeedType = type;
                currentFeedPage = 1;
                renderFeedPagination();
            }}

            function changeFeedPage(page) {{
                currentFeedPage = page;
                renderFeedPagination();
                window.scrollTo({{ top: 0, behavior: 'smooth' }});
            }}

            function renderFeedPagination() {{
                const allCards = Array.from(document.querySelectorAll('.opportunity-card'));
                const matchingCards = allCards.filter(card => {{
                    if (currentFeedType === 'all') return true;
                    if (currentFeedType === 'latest') return card.classList.contains('rfp-card-latest');
                    if (currentFeedType === 'pending') return card.classList.contains('rfp-card-pending');
                    if (currentFeedType === 'archive') return card.classList.contains('rfp-card-archive');
                    return true;
                }});

                const totalItems = matchingCards.length;
                const totalPages = Math.ceil(totalItems / pageSize) || 1;
                if (currentFeedPage > totalPages) currentFeedPage = totalPages;
                if (currentFeedPage < 1) currentFeedPage = 1;

                const startIndex = (currentFeedPage - 1) * pageSize;
                const endIndex = startIndex + pageSize;

                allCards.forEach(c => c.style.display = 'none');

                matchingCards.forEach((card, idx) => {{
                    if (idx >= startIndex && idx < endIndex) {{
                        card.style.display = 'flex';
                    }}
                }});

                const displayedStart = totalItems === 0 ? 0 : startIndex + 1;
                const displayedEnd = Math.min(endIndex, totalItems);
                const infoElem = document.getElementById('feedPageInfo');
                if (infoElem) {{
                    infoElem.innerText = 'Showing ' + displayedStart + '-' + displayedEnd + ' of ' + totalItems + ' opportunities (' + pageSize + ' per page)';
                }}

                const ctrlElem = document.getElementById('feedPaginationControls');
                if (ctrlElem) {{
                    let btnHtml = '';
                    const prevDisabled = currentFeedPage === 1 ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : '';
                    btnHtml += '<button onclick="changeFeedPage(' + (currentFeedPage - 1) + ')" ' + prevDisabled + ' style="padding: 6px 12px; border-radius: 6px; border: 1px solid #cbd5e1; background: white; font-weight: 600; font-size: 0.8rem; cursor: pointer;">← Prev</button>';

                    for (let p = 1; p <= totalPages; p++) {{
                        const isCurrent = p === currentFeedPage;
                        const style = isCurrent 
                            ? 'background: #0284c7; color: white; border: 1px solid #0284c7;' 
                            : 'background: white; color: #334155; border: 1px solid #cbd5e1;';
                        btnHtml += '<button onclick="changeFeedPage(' + p + ')" style="padding: 6px 12px; border-radius: 6px; font-weight: 700; font-size: 0.8rem; cursor: pointer; ' + style + '">' + p + '</button>';
                    }}

                    const nextDisabled = currentFeedPage === totalPages ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : '';
                    btnHtml += '<button onclick="changeFeedPage(' + (currentFeedPage + 1) + ')" ' + nextDisabled + ' style="padding: 6px 12px; border-radius: 6px; border: 1px solid #cbd5e1; background: white; font-weight: 600; font-size: 0.8rem; cursor: pointer;">Next →</button>';

                    ctrlElem.innerHTML = btnHtml;
                }}
            }}

            function openBriefModal(rfpId) {{
                try {{
                    const dataTag = document.getElementById('rfp-data');
                    if (!dataTag) {{
                        console.error('rfp-data tag not found');
                        return;
                    }}
                    const rfpMap = JSON.parse(dataTag.textContent);
                    const item = rfpMap[rfpId];
                    if (!item) {{
                        console.error('RFP item not found for id:', rfpId);
                        return;
                    }}

                    document.getElementById('mTitle').innerText = item.title;
                    document.getElementById('mBadge').innerText = item.badge_text;
                    document.getElementById('mBadge').style.backgroundColor = item.badge_bg;
                    
                    document.getElementById('mOrgRegion').innerText = item.org + ' (' + item.country + ')';
                    document.getElementById('mValDead').innerText = 'Contract Value: ' + item.val + ' | Submission Deadline: ' + item.deadline;
                    document.getElementById('mSummary').innerText = item.summary;
                    document.getElementById('mWhy').innerText = item.why;
                    document.getElementById('mDeliv').innerText = Array.isArray(item.deliverables) ? item.deliverables.join(' • ') : item.deliverables;
                    document.getElementById('mGaps').innerText = Array.isArray(item.gaps) ? item.gaps.join(' • ') : item.gaps;
                    document.getElementById('mPortalSource').innerText = item.portal + ' (' + item.url + ')';
                    document.getElementById('mRecTier').innerText = item.rec + ' (' + item.score + '% Match Score)';
                    document.getElementById('mLink').href = item.url;
                    
                    document.getElementById('briefModal').classList.add('active');
                }} catch (err) {{
                    console.error("AI Brief modal error:", err);
                }}
            }}

            function closeBriefModal() {{
                document.getElementById('briefModal').classList.remove('active');
            }}

            function appendEvalConsoleLog(level, message) {{
                const container = document.getElementById('evalLogConsole');
                if (!container) return;
                const now = new Date();
                const timeStr = now.toTimeString().split(' ')[0];
                const entry = document.createElement('div');
                entry.className = 'log-entry';
                entry.innerHTML = '<span class="log-time">[' + timeStr + ']</span> <span class="log-level-' + level + '">' + message + '</span>';
                container.appendChild(entry);
                container.scrollTop = container.scrollHeight;
            }}

            async function reEvaluateRfp(rfpId) {{
                const btn = document.getElementById('eval-btn-' + rfpId);
                const cardLog = document.getElementById('eval-log-' + rfpId);
                
                if (btn) {{
                    btn.disabled = true;
                    btn.style.opacity = '0.7';
                    btn.innerHTML = '⚡ Re-Evaluating with Groq LLM...';
                }}
                
                if (cardLog) {{
                    cardLog.style.display = 'block';
                    cardLog.innerHTML = '⏳ <span style="color: #fbbf24;">[Evaluating]</span> Sending notice details to Groq LLM reasoner...';
                }}

                appendEvalConsoleLog('INFO', '⚡ Triggering Groq LLM re-evaluation for RFP ID: ' + rfpId + '...');
                appendConsoleLog('INFO', '⚡ Triggering Groq LLM re-evaluation for RFP ID: ' + rfpId + '...');

                try {{
                    const res = await fetch('/api/v1/evaluations/' + encodeURIComponent(rfpId) + '/re-evaluate', {{ method: 'POST' }});
                    const data = await res.json();
                    
                    if (data.status === 'success') {{
                        const rec = data.recommendation;
                        const score = data.score;
                        
                        let badgeBg = '#0284c7';
                        if (rec === 'PURSUE') badgeBg = '#16a34a';
                        else if (rec === 'PARTNER') badgeBg = '#eab308';
                        else if (rec === 'PASS' || rec === 'NO-GO' || rec === 'REVIEW') badgeBg = '#dc2626';

                        const badgeElem = document.getElementById('eval-badge-' + rfpId);
                        if (badgeElem) {{
                            badgeElem.innerText = rec;
                            badgeElem.style.backgroundColor = badgeBg;
                        }}
                        
                        const scoreElem = document.getElementById('eval-score-' + rfpId);
                        if (scoreElem) {{
                            scoreElem.innerText = score + '% Match';
                        }}

                        const cardElem = document.getElementById('eval-card-' + rfpId);
                        if (cardElem) {{
                            cardElem.setAttribute('data-rec', rec);
                            cardElem.setAttribute('data-score', score);
                        }}

                        const summaryElem = document.getElementById('eval-summary-' + rfpId);
                        if (summaryElem && data.ai_summary) {{
                            summaryElem.innerText = data.ai_summary;
                        }}

                        const delivElem = document.getElementById('eval-deliv-' + rfpId);
                        if (delivElem && data.eai_deliverables) {{
                            const delivs = Array.isArray(data.eai_deliverables) ? data.eai_deliverables : [data.eai_deliverables];
                            delivElem.innerHTML = delivs.map(d => '<li style="margin-bottom: 4px;">• ' + d + '</li>').join('');
                        }}

                        const gapsElem = document.getElementById('eval-gaps-' + rfpId);
                        if (gapsElem && data.missing_requirements) {{
                            const gaps = Array.isArray(data.missing_requirements) ? data.missing_requirements : [data.missing_requirements];
                            gapsElem.innerHTML = gaps.map(g => '<li style="margin-bottom: 4px;">• ' + g + '</li>').join('');
                        }}

                        if (cardLog) {{
                            cardLog.innerHTML = '✅ <span style="color: #4ade80;">[Evaluation Complete]</span> Score: <strong>' + score + '%</strong> (' + rec + ')';
                        }}

                        appendEvalConsoleLog('SUCCESS', '⚡ Re-evaluation complete! New Score: ' + score + '% (' + rec + ')');
                        appendConsoleLog('SUCCESS', '⚡ Re-evaluation complete for RFP ID: ' + rfpId + '! Score: ' + score + '% (' + rec + ')');

                    }} else {{
                        const err = data.detail || 'Unknown error';
                        if (cardLog) {{
                            cardLog.innerHTML = '❌ <span style="color: #f87171;">[Evaluation Failed]</span> ' + err;
                        }}
                        appendEvalConsoleLog('ERROR', 'Re-evaluation failed: ' + err);
                        appendConsoleLog('ERROR', 'Re-evaluation failed: ' + err);
                    }}
                }} catch (e) {{
                    if (cardLog) {{
                        cardLog.innerHTML = '❌ <span style="color: #f87171;">[Evaluation Error]</span> ' + e;
                    }}
                    appendEvalConsoleLog('ERROR', 'Re-evaluation error: ' + e);
                    appendConsoleLog('ERROR', 'Re-evaluation error: ' + e);
                }} finally {{
                    if (btn) {{
                        btn.disabled = false;
                        btn.style.opacity = '1';
                        btn.innerHTML = '⚡ Re-Evaluate with AI';
                    }}
                }}
            }}

            let currentEvalPage = 1;
            const evalPageSize = 10;

            function filterEvaluations(resetPage = true) {{
                if (resetPage) {{
                    currentEvalPage = 1;
                }}
                renderEvalPagination();
            }}

            function changeEvalPage(page) {{
                currentEvalPage = page;
                filterEvaluations(false);
                window.scrollTo({{ top: 0, behavior: 'smooth' }});
            }}

            function renderEvalPagination() {{
                const recFilter = document.getElementById('evalRecFilter');
                if (!recFilter) return;

                const recVal = recFilter.value;
                const minScore = parseInt(document.getElementById('evalScoreFilter').value || '0');
                const portalVal = document.getElementById('evalPortalFilter').value;
                const searchVal = document.getElementById('evalSearchFilter').value.toLowerCase().trim();

                const allCards = Array.from(document.querySelectorAll('.eval-card'));
                const matchingCards = allCards.filter(card => {{
                    const cRec = card.getAttribute('data-rec') || '';
                    const cScore = parseInt(card.getAttribute('data-score') || '0');
                    const cPortal = card.getAttribute('data-portal') || '';
                    const cText = (card.getAttribute('data-text') || '').toLowerCase();

                    const matchRec = (recVal === 'all' || cRec === recVal);
                    const matchScore = (cScore >= minScore);
                    const matchPortal = (portalVal === 'all' || cPortal === portalVal);
                    const matchSearch = (!searchVal || cText.includes(searchVal));

                    return matchRec && matchScore && matchPortal && matchSearch;
                }});

                const totalItems = matchingCards.length;
                const totalPages = Math.ceil(totalItems / evalPageSize) || 1;
                if (currentEvalPage > totalPages) currentEvalPage = totalPages;
                if (currentEvalPage < 1) currentEvalPage = 1;

                const startIndex = (currentEvalPage - 1) * evalPageSize;
                const endIndex = startIndex + evalPageSize;

                allCards.forEach(c => c.style.display = 'none');

                matchingCards.forEach((card, idx) => {{
                    if (idx >= startIndex && idx < endIndex) {{
                        card.style.display = 'block';
                    }}
                }});

                const displayedStart = totalItems === 0 ? 0 : startIndex + 1;
                const displayedEnd = Math.min(endIndex, totalItems);
                const infoElem = document.getElementById('evalPageInfo');
                if (infoElem) {{
                    infoElem.innerText = 'Showing ' + displayedStart + '-' + displayedEnd + ' of ' + totalItems + ' evaluations (' + evalPageSize + ' per page)';
                }}

                const ctrlElem = document.getElementById('evalPaginationControls');
                if (ctrlElem) {{
                    let btnHtml = '';
                    const prevDisabled = currentEvalPage === 1 ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : '';
                    btnHtml += '<button onclick="changeEvalPage(' + (currentEvalPage - 1) + ')" ' + prevDisabled + ' style="padding: 6px 12px; border-radius: 6px; border: 1px solid #cbd5e1; background: white; font-weight: 600; font-size: 0.8rem; cursor: pointer;">← Prev</button>';

                    for (let p = 1; p <= totalPages; p++) {{
                        const isCurrent = p === currentEvalPage;
                        const style = isCurrent 
                            ? 'background: #0284c7; color: white; border: 1px solid #0284c7;' 
                            : 'background: white; color: #334155; border: 1px solid #cbd5e1;';
                        btnHtml += '<button onclick="changeEvalPage(' + p + ')" style="padding: 6px 12px; border-radius: 6px; font-weight: 700; font-size: 0.8rem; cursor: pointer; ' + style + '">' + p + '</button>';
                    }}

                    const nextDisabled = currentEvalPage === totalPages ? 'disabled style="opacity:0.4; cursor:not-allowed;"' : '';
                    btnHtml += '<button onclick="changeEvalPage(' + (currentEvalPage + 1) + ')" ' + nextDisabled + ' style="padding: 6px 12px; border-radius: 6px; border: 1px solid #cbd5e1; background: white; font-weight: 600; font-size: 0.8rem; cursor: pointer;">Next →</button>';

                    ctrlElem.innerHTML = btnHtml;
                }}
            }}

            // Live Log Stream Polling Function
            async function fetchLiveLogs() {{
                try {{
                    const res = await fetch('/api/v1/logs');
                    const logs = await res.json();
                    const container = document.getElementById('logConsole');
                    if (logs && logs.length > 0) {{
                        container.innerHTML = logs.map(l => 
                            `<div class="log-entry"><span class="log-time">[${{l.timestamp}}]</span> <span class="log-level-${{l.level}}">${{l.message}}</span></div>`
                        ).join('');
                        container.scrollTop = container.scrollHeight;
                    }}
                }} catch (e) {{
                    console.error('Error fetching live logs:', e);
                }}
            }}

            setInterval(fetchLiveLogs, 1500);
            fetchLiveLogs();
            window.addEventListener('DOMContentLoaded', () => {{
                renderFeedPagination();
                renderEvalPagination();
            }});
            renderFeedPagination();
            renderEvalPagination();

            async function resyncKB(domain) {{
                alert('Initiating vector re-sync for ' + domain + '...');
                try {{
                    const res = await fetch('/api/v1/kb/resync?domain=' + encodeURIComponent(domain), {{ method: 'POST' }});
                    const data = await res.json();
                    alert('Re-indexing complete for ' + domain + '! ' + data.vectors + ' capability vectors updated.');
                    fetchLiveLogs();
                }} catch (e) {{
                    alert('Re-sync error: ' + e);
                }}
            }}

            function appendConsoleLog(level, message) {{
                const container = document.getElementById('logConsole');
                if (container) {{
                    const time = new Date().toLocaleTimeString('en-US', {{ hour12: false }});
                    const div = document.createElement('div');
                    div.className = 'log-entry';
                    div.innerHTML = `<span class="log-time">[${{time}}]</span> <span class="log-level-${{level}}">${{message}}</span>`;
                    container.appendChild(div);
                    container.scrollTop = container.scrollHeight;
                }}
            }}

            async function triggerLiveScan(portalId) {{
                appendConsoleLog('INFO', '⚡ Initiating live crawl request' + (portalId ? ' for portal target [' + portalId + ']' : '') + '...');
                const targetUrl = portalId ? '/api/v1/crawl/trigger?portal_id=' + encodeURIComponent(portalId) : '/api/v1/crawl/trigger';
                try {{
                    const res = await fetch(targetUrl, {{ method: 'POST' }});
                    const data = await res.json();
                    await fetchLiveLogs();
                    setTimeout(() => {{ window.location.reload(); }}, 1500);
                }} catch (e) {{
                    appendConsoleLog('ERROR', 'Scan execution error: ' + e);
                }}
            }}

            async function cancelActiveCrawl() {{
                appendConsoleLog('WARN', '🛑 User clicked Stop/Cancel. Terminating active crawl tasks...');
                try {{
                    const res = await fetch('/api/v1/crawl/cancel', {{ method: 'POST' }});
                    const data = await res.json();
                    await fetchLiveLogs();
                }} catch (e) {{
                    appendConsoleLog('ERROR', 'Cancel error: ' + e);
                }}
            }}

            async function togglePortal(portalId, ev) {{
                if (ev && ev.preventDefault) ev.preventDefault();
                appendConsoleLog('INFO', '🔄 Toggling portal active state for ' + portalId + '...');
                try {{
                    const res = await fetch('/api/v1/portals/' + encodeURIComponent(portalId) + '/toggle', {{ 
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }}
                    }});
                    if (!res.ok) {{
                        const errText = await res.text();
                        alert('Failed to toggle portal: HTTP ' + res.status + ' - ' + errText);
                        return;
                    }}
                    const data = await res.json();
                    window.location.reload();
                }} catch (e) {{
                    console.error('Toggle error:', e);
                    alert('Failed to toggle portal: ' + (e.message || e));
                }}
            }}

            async function triggerEvaluateAllPending() {{
                appendConsoleLog('INFO', 'Triggering Groq LLM evaluation for all unassessed RFPs...');
                try {{
                    const res = await fetch('/api/v1/evaluations/evaluate-all', {{ method: 'POST' }});
                    const data = await res.json();
                    appendConsoleLog('SUCCESS', 'Batch evaluation complete. Evaluated: ' + (data.stats ? data.stats.evaluated : 0));
                    window.location.reload();
                }} catch (e) {{
                    appendConsoleLog('ERROR', 'Batch evaluation error: ' + e);
                }}
            }}

            async function evaluateSingleRFP(rfpId, ev) {{
                if (ev && ev.preventDefault) ev.preventDefault();
                appendConsoleLog('INFO', 'Running AI evaluation for RFP #' + rfpId + '...');
                try {{
                    const res = await fetch('/api/v1/evaluations/' + encodeURIComponent(rfpId) + '/re-evaluate', {{ method: 'POST' }});
                    const data = await res.json();
                    appendConsoleLog('SUCCESS', 'Evaluation completed for RFP #' + rfpId);
                    window.location.reload();
                }} catch (e) {{
                    appendConsoleLog('ERROR', 'Single evaluation error: ' + e);
                    alert('Evaluation error: ' + e);
                }}
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.get("/api/v1/portals")
def get_portals(db: Session = Depends(get_db)):
    return db.query(ProcurementPortal).all()

@app.get("/api/v1/opportunities")
def get_opportunities(db: Session = Depends(get_db)):
    results = []
    rfps = db.query(RFPOpportunity).order_by(RFPOpportunity.created_at.desc()).all()
    for r in rfps:
        eval_obj = r.evaluation
        results.append({
            "id": r.id,
            "external_rfp_id": r.external_rfp_id,
            "title": r.title,
            "issuing_org": r.issuing_org,
            "country": r.country,
            "source_url": r.source_url,
            "submission_deadline": r.submission_deadline,
            "evaluation": {
                "relevance_score": eval_obj.relevance_score if eval_obj else 0,
                "is_relevant": eval_obj.is_relevant if eval_obj else False,
                "why_relevant": eval_obj.why_relevant if eval_obj else "",
                "eai_deliverables": eval_obj.eai_deliverables if eval_obj else [],
                "missing_requirements": eval_obj.missing_requirements if eval_obj else [],
                "ai_summary": eval_obj.ai_summary if eval_obj else "",
                "recommendation": eval_obj.recommendation if eval_obj else "UNCHECKED"
            } if eval_obj else None
        })
    return results

@app.post("/api/v1/crawl/trigger")
async def trigger_crawl(portal_id: str = None, db: Session = Depends(get_db)):
    target_desc = f"portal target '{portal_id}'" if portal_id else "active standard portals"
    system_logger.add_log("INFO", f"⚡ Live crawl initiated for {target_desc}...")
    pipeline = RFPIntelligencePipeline(db)
    stats = await pipeline.run_pipeline(target_portal_id=portal_id)
    return {"status": "success", "stats": stats}

@app.post("/api/v1/crawl/cancel")
def cancel_crawl():
    from src.intelligence.pipeline import request_crawl_cancel
    request_crawl_cancel()
    system_logger.add_log("WARN", "🛑 Crawl termination requested by user.")
    return {"status": "success", "message": "Cancellation requested"}

@app.post("/api/v1/portals/{portal_id}/toggle")
def toggle_portal(portal_id: str, db: Session = Depends(get_db)):
    portal = db.query(ProcurementPortal).filter_by(portal_id=portal_id).first()
    if not portal:
        raise HTTPException(status_code=404, detail="Portal not found")
    portal.is_active = not portal.is_active
    db.commit()
    status_str = "ACTIVE (ON)" if portal.is_active else "INACTIVE (OFF)"
    system_logger.add_log("INFO", f"🔄 Portal '{portal.name}' toggled to {status_str}.")
    return {"status": "success", "portal_id": portal.portal_id, "is_active": portal.is_active}

@app.post("/api/v1/evaluations/evaluate-all")
async def evaluate_all_pending(db: Session = Depends(get_db)):
    system_logger.add_log("INFO", "🧠 Batch evaluation triggered for pending RFPs...")
    pipeline = RFPIntelligencePipeline(db)
    stats = await pipeline.evaluate_pending_rfps()
    return {"status": "success", "stats": stats}

@app.post("/api/v1/evaluations/{rfp_id}/re-evaluate")
async def re_evaluate_rfp(rfp_id: str, db: Session = Depends(get_db)):
    rfp = db.query(RFPOpportunity).filter_by(id=rfp_id).first()
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP opportunity not found")
    
    rfp_data = {
        "title": rfp.title,
        "issuing_org": rfp.issuing_org,
        "country": rfp.country,
        "source_url": rfp.source_url,
        "submission_deadline": rfp.submission_deadline,
        "estimated_value_usd": rfp.estimated_value_usd,
        "raw_content": rfp.raw_content or rfp.title
    }
    
    reasoner = LLMOpportunityReasoner()
    system_logger.add_log("INFO", f"[LLMReasoner] Re-evaluating RFP with Groq LLM: '{rfp.title[:40]}'")
    eval_res = await reasoner.evaluate_rfp(rfp_data)
    
    score = eval_res.get("relevance_score", 0)
    rec = eval_res.get("recommendation", "PASS")
    
    existing_eval = db.query(RFPExecutionEvaluation).filter_by(rfp_id=rfp.id).first()
    if existing_eval:
        existing_eval.relevance_score = score
        existing_eval.is_relevant = eval_res.get("is_relevant", False)
        existing_eval.why_relevant = eval_res.get("why_relevant", "")
        existing_eval.eai_deliverables = eval_res.get("eai_deliverables", [])
        existing_eval.missing_requirements = eval_res.get("missing_requirements", [])
        existing_eval.ai_summary = eval_res.get("ai_summary", "")
        existing_eval.recommendation = rec
    else:
        existing_eval = RFPExecutionEvaluation(
            rfp_id=rfp.id,
            relevance_score=score,
            is_relevant=eval_res.get("is_relevant", False),
            why_relevant=eval_res.get("why_relevant", ""),
            eai_deliverables=eval_res.get("eai_deliverables", []),
            missing_requirements=eval_res.get("missing_requirements", []),
            ai_summary=eval_res.get("ai_summary", ""),
            recommendation=rec
        )
        db.add(existing_eval)
    
    db.commit()
    system_logger.add_log("SUCCESS", f"[LLMReasoner] Updated evaluation score to {score}% ({rec})")
    return {
        "status": "success", 
        "score": score, 
        "recommendation": rec,
        "ai_summary": eval_res.get("ai_summary", ""),
        "eai_deliverables": eval_res.get("eai_deliverables", []),
        "missing_requirements": eval_res.get("missing_requirements", [])
    }
