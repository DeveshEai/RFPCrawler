# RFP Intelligence System

An enterprise AI-powered procurement intelligence & scraper engine grounded in **EAI Systems** (`eaisystems.com`) and **PhantomOps** (`phantomops.ae`) capabilities.

## 🚀 Features

- **Live UK Contracts Finder Scraper** — Fetches real-time tender notices, extracts exact GBP contract values and closing dates
- **AI Opportunity Evaluator** — Groq-powered LLM (`qwen/qwen3.8-27b`) evaluates each opportunity against EAI/PhantomOps capabilities
- **12-Question Executive AI Brief** — Opens a full modal dossier for each tender card with org, value, deliverables, gaps, and recommendation
- **Knowledge Base Grounding** — Vector-grounded reasoning on `eaisystems.com` (Pega BPM/DPA) & `phantomops.ae` (Sovereign Agentic AI)
- **Live Stream Log Console** — Real-time pipeline event ticker at the top of the dashboard
- **Re-Sync Knowledge Base** — API endpoint `/api/v1/kb/resync` to trigger mock vector re-indexing

## 🛠️ Stack

- **Backend**: Python, FastAPI, SQLAlchemy, SQLite
- **Scraper**: httpx + BeautifulSoup4 (UK Contracts Finder)
- **AI Reasoner**: Groq API (`qwen/qwen3.8-27b`)
- **Frontend**: Server-rendered HTML dashboard (no JS framework)

## ⚙️ Setup

```bash
# Clone
git clone https://github.com/<your-username>/RFPCrawler.git
cd RFPCrawler

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your GROQ_API_KEY

# Run
python main.py
```

Dashboard opens at `http://localhost:8000`

## 📁 Project Structure

```
RFPCrawler/
├── main.py                          # Entry point
├── config.py                        # Settings via pydantic-settings
├── requirements.txt
├── .env.example                     # Safe config template
├── src/
│   ├── api/server.py                # FastAPI dashboard + endpoints
│   ├── db/                          # SQLAlchemy models & database
│   ├── intelligence/
│   │   ├── llm_reasoner.py          # Groq-powered opportunity evaluator
│   │   └── pipeline.py              # Full crawl → evaluate pipeline
│   ├── services/
│   │   ├── logger_service.py        # In-memory live log stream
│   │   └── email_alert_service.py   # SMTP notifications
│   └── sources/
│       ├── base_adapter.py          # Abstract adapter pattern
│       └── contracts_finder_adapter.py  # UK Contracts Finder scraper
```

## 🌐 Knowledge Base Domains

| Domain | Focus | Vectors |
|---|---|---|
| `eaisystems.com` | Pega BPM & DPA, Enterprise Integration, Cloud Architecture | 28 |
| `phantomops.ae` | Sovereign Agentic AI, BFSI Agents, KYC/CBUAE Compliance | 36 |

## 📜 License

MIT
