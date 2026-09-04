# RFP Intelligence & Automated Procurement System

> **Enterprise AI-powered procurement intelligence engine for real-time RFP scraping, deep PDF document parsing, and grounding evaluation tuned for EAI Systems (`eaisystems.com`) and PhantomOps (`phantomops.ae`).**

---

## 🖼️ Dashboard Overview & Interface Tour

### 1. Opportunity Feed & Real-Time Pipeline Stream
The main dashboard presents live procurement opportunities scraped across global portals, featuring real-time LLM reasoning event stream logs, PURSUE/REVIEW match tags, and fast scraping controls.

![Opportunity Feed](docs/images/opportunity_feed_v4.png)

---

### 2. 12-Question Executive AI Brief Modal
Clicking **`📄 AI Brief (12 Qs)`** on any tender card opens an executive briefing dossier outlining issuing authority, estimated contract value, executive alignment summary, practice deliverables, and missing requirement gaps.

![Executive AI Brief Modal](docs/images/executive_ai_brief_v4.png)

---

### 3. Company Grounding Knowledge Base
Grounding domain knowledge store indexed for **EAI Systems** (`eaisystems.com`) and **PhantomOps** (`phantomops.ae`) with 1-click domain vector re-sync capability.

![Knowledge Base Grounding](docs/images/knowledge_base_v4.png)

---

### 4. Configured Portal Adapters
Multi-portal scraping control panel supporting UK Contracts Finder, Find a Tender, SAM.gov, Google Serper, SerpApi, DuckDuckGo, and Craxy AI.

![Portal Adapters](docs/images/portal_adapters_v4.png)

---

### 5. Deep AI Opportunity Evaluations
Dedicated analysis workspace with score filters (`PURSUE Only`, `Match Score >= 70%`), matched practice deliverables, missing gap tags, and 1-click re-evaluations.

![AI Opportunity Evaluations](docs/images/ai_evaluations_v4.png)

---

## ⚡ Key Features

- **🌐 Multi-Portal Live Procurement Crawling**:
  - **UK Contracts Finder** — Live web scraper with GBP budget extraction & deadline tracking.
  - **Find a Tender (UK)** — Enterprise-level UK high-value public procurement notices.
  - **SAM.gov (US Federal Solicitations)** — Dynamic search dorking for US government solicitations.
  - **Craxy AI & DuckDuckGo** — Multi-portal fallback scrapers for international tenders.
- **📄 Deep PDF Attachment Extraction**:
  - Automatically detects, downloads, and parses attached PDF specification documents using `pypdf`.
  - Injects visual **`📄 PDF`** badges onto dashboard cards with direct specification download links.
- **🧠 Dual AI Evaluation Engine**:
  - **Primary**: Groq API (`qwen/qwen3.8-27b`).
  - **Secondary**: Google Gemini API (`gemini-3.6-flash`).
  - Grounded evaluations against Pega BPM, Enterprise Integration, and Sovereign Agentic AI capabilities.
- **🛑 Quota Exhaustion Circuit Breaker**:
  - Catches HTTP `429 Rate Limit / Quota Exhausted` errors and **immediately halts** batch evaluations to preserve resources.
  - Built-in rate-limit pacing delay (`1.2s`) to prevent API rate-limit spikes.
- **🔄 Live Domain Knowledge Re-Sync**:
  - Live HTTPS probes and vector grounding refresh for `eaisystems.com` and `phantomops.ae`.
- **📊 Interactive Management Dashboard**:
  - Live streaming log console, RFP filtering (PURSUE / REVIEW / PASS), detailed 12-question executive AI briefs, and 1-click batch evaluation.

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| **Backend Framework** | FastAPI (Python 3.10+) |
| **Database ORM** | SQLAlchemy with SQLite (`rfp_intelligence.db`) |
| **Web Crawling** | `httpx`, `BeautifulSoup4`, SerpApi |
| **PDF Extraction** | `pypdf` (In-memory text extraction) |
| **AI LLM Engines** | Groq API (`qwen/qwen3.8-27b`), Google Gemini 3.6 Flash |
| **Alerts & Logging** | SMTP Email Alerts, In-Memory System Event Logger |
| **Frontend UI** | Modern Vanilla CSS, Responsive Glassmorphic Dashboard |

---

## ⚙️ Quick Start Guide

### 1. Clone the Repository
```bash
git clone https://github.com/DeveshEAI/RFPCrawler.git
cd RFPCrawler
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration (`.env`)
Create or edit the `.env` file in the root directory:

```ini
APP_NAME="RFP Intelligence System"
VERSION="1.0.0"
DATABASE_URL="sqlite:///./rfp_intelligence.db"

# Primary LLM Configuration (groq or gemini)
LLM_PROVIDER="groq"
GROQ_API_KEY="gsk_your_groq_api_key_here"
GROQ_MODEL="qwen/qwen3.8-27b"

# Backup LLM Configuration
GEMINI_API_KEY="your_gemini_api_key_here"
GEMINI_MODEL="gemini-3.6-flash"

# Search Dorking
SERPAPI_KEY="your_serpapi_key_here"

# Alerts
ALERT_EMAIL_TO="rfp-alerts@eaisystems.com"
MATCH_SCORE_THRESHOLD=70
HIGH_PRIORITY_SCORE=85
```

### 4. Run the Application
```bash
python main.py
```
Open your browser and navigate to: **`http://localhost:8000`**

---

## 🔄 How to Switch AI Providers (Groq ↔ Gemini)

You can toggle between Groq and Gemini anytime by changing `LLM_PROVIDER` in `.env`:

* **To Use Groq (Fast & Free of Gemini Quotas)**:
  ```ini
  LLM_PROVIDER="groq"
  ```
* **To Switch to Gemini**:
  ```ini
  LLM_PROVIDER="gemini"
  ```
* **Restart Server**:
  ```bash
  python main.py
  ```

---

## 📁 Repository Architecture

```
RFPCrawler/
├── main.py                          # Application entry point
├── config.py                        # Pydantic environment configuration
├── requirements.txt                 # Dependencies
├── .env                             # Active environment credentials
├── docs/
│   └── images/                      # Dashboard UI screenshots & diagrams
├── src/
│   ├── api/
│   │   └── server.py                # FastAPI dashboard routes & endpoints
│   ├── db/
│   │   ├── database.py              # SQLite session & engine setup
│   │   └── models.py                # Database models (RFPOpportunity, RFPExecutionEvaluation)
│   ├── intelligence/
│   │   ├── llm_reasoner.py          # Groq & Gemini reasoning logic + Quota Guards
│   │   ├── pipeline.py              # Crawl, Stage 1 Filter, and Batch AI Evaluation pipeline
│   │   └── stage1_filter.py         # Deterministic anti-noise filter
│   ├── services/
│   │   ├── logger_service.py        # System event logger
│   │   └── email_service.py         # Email notification alerts
│   └── sources/
│       ├── base_adapter.py          # Base adapter & PDF extraction utilities
│       ├── contracts_finder_adapter.py  # UK Contracts Finder scraper
│       ├── find_a_tender_adapter.py     # UK Find a Tender scraper
│       ├── global_tech_tenders_adapter.py # SAM.gov SerpApi dorking scraper
│       ├── craxy_ai_adapter.py      # Craxy AI scraper
│       └── duckduckgo_free_adapter.py # DuckDuckGo fallback scraper
```

---

## 🌐 Grounding Capabilities

| Domain | Corporate Focus | Core Capabilities |
|---|---|---|
| **`eaisystems.com`** | Enterprise Integration & Low-Code | Certified Pega BPM & DPA, Enterprise Case Management, Cloud Migration (AWS/Azure/GCP), Banking & Insurance Workflows |
| **`phantomops.ae`** | Sovereign Agentic AI | Sovereign Arabic-Native AI Agents, BFSI/Government KYC & Compliance, Air-Gapped/Private Cloud Deployments |

---

## 📜 License

Distributed under the **MIT License**. Built for **EAI Systems** & **PhantomOps**.
