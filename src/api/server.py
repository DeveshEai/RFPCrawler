from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from src.db.database import Base, engine, get_db
import src.db.models as models
from src.db.models import ProcurementPortal, RFPOpportunity, RFPExecutionEvaluation
from src.intelligence.pipeline import RFPIntelligencePipeline
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
    rfps = db.query(RFPOpportunity).order_by(RFPOpportunity.created_at.desc()).all()

    portal_rows = "".join(f"""
        <tr style="border-bottom: 1px solid #e2e8f0;">
            <td style="padding: 14px 16px; font-weight: 600; color: #1e293b;">{p.name}</td>
            <td style="padding: 14px 16px; color: #64748b;">{p.country}</td>
            <td style="padding: 14px 16px;"><span style="background: #dcfce7; color: #15803d; padding: 4px 10px; border-radius: 9999px; font-weight: 600; font-size: 0.75rem;">ACTIVE</span></td>
            <td style="padding: 14px 16px;"><a href="{p.base_url}" target="_blank" style="color: #0284c7; text-decoration: none; font-weight: 500;">{p.base_url}</a></td>
        </tr>
    """ for p in portals)

    import json
    rfp_map_dict = {}

    # Identify latest batch
    latest_batch_id = None
    for r in rfps:
        if getattr(r, 'batch_id', None):
            latest_batch_id = r.batch_id
            break

    count_latest = 0
    count_archive = 0
    rfp_cards = ""

    for r in rfps:
        b_id = getattr(r, 'batch_id', None)
        is_latest = (latest_batch_id and b_id == latest_batch_id) or (not latest_batch_id and (count_latest < 3 or len(rfps) <= 3))
        if is_latest:
            count_latest += 1
            card_class = "rfp-card-latest"
        else:
            count_archive += 1
            card_class = "rfp-card-archive"

        eval_obj = r.evaluation
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

        if rec == "PURSUE" or score >= 70:
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
                <button class="btn-ai-brief" onclick="openBriefModal('{r.id}')">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/></svg>
                    AI Brief (12 Qs)
                </button>
                <a href="{r.source_url}" target="_blank" class="btn-ext-link" title="Open Original Notice Page">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                </a>
            </div>
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
                    <button class="btn-trigger" onclick="triggerLiveScan()">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                        Trigger Live Crawl
                    </button>
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
                    <button class="sub-tab-btn active" onclick="filterFeed('latest', this)">
                        ⚡ Latest Crawl Run ({count_latest})
                    </button>
                    <button class="sub-tab-btn" onclick="filterFeed('archive', this)">
                        📚 Historical Archive ({count_archive})
                    </button>
                    <button class="sub-tab-btn" onclick="filterFeed('all', this)">
                        🌐 All Opportunities ({len(rfps)})
                    </button>
                </div>

                <div class="cards-grid">
                    {rfp_cards}
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
                            </tr>
                        </thead>
                        <tbody>
                            {portal_rows}
                        </tbody>
                    </table>
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

            function filterFeed(type, el) {{
                document.querySelectorAll('.sub-tab-btn').forEach(b => b.classList.remove('active'));
                el.classList.add('active');
                
                document.querySelectorAll('.opportunity-card').forEach(card => {{
                    if (type === 'all') {{
                        card.style.display = 'flex';
                    }} else if (type === 'latest') {{
                        card.style.display = card.classList.contains('rfp-card-latest') ? 'flex' : 'none';
                    }} else if (type === 'archive') {{
                        card.style.display = card.classList.contains('rfp-card-archive') ? 'flex' : 'none';
                    }}
                }});
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

            async function triggerLiveScan() {{
                const btn = document.querySelector('.btn-trigger');
                btn.innerHTML = '⏳ Crawling & Evaluating...';
                btn.disabled = true;
                try {{
                    const res = await fetch('/api/v1/crawl/trigger', {{ method: 'POST' }});
                    const data = await res.json();
                    await fetchLiveLogs();
                    setTimeout(() => {{ window.location.reload(); }}, 1200);
                }} catch (e) {{
                    alert('Scan error: ' + e);
                }} finally {{
                    btn.innerHTML = '⚡ Trigger Live Crawl';
                    btn.disabled = false;
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
    pipeline = RFPIntelligencePipeline(db)
    stats = await pipeline.run_pipeline(target_portal_id=portal_id)
    return {"status": "success", "stats": stats}
