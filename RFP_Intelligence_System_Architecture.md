# Technical Architecture & Specification: AI-Powered RFP/RFI Scraper & Intelligence System

**Client/Target Entity:** EAI Systems & PhantomOps  
**Document Version:** 1.0.0  
**Author:** AI Systems Architecture Team  
**Date:** August 28, 2026  

---

## 1. Project Overview

### 1.1 Purpose
The **AI-Powered RFP/RFI Scraper & Intelligence System** is an enterprise-grade automated intelligence platform designed to scan global procurement portals, discover tenders, Requests for Proposals (RFPs), and Requests for Information (RFIs), compare their requirements against **EAI Systems** and **PhantomOps** core business capabilities, filter out irrelevant leads, estimate project scale and budget, and generate high-fidelity AI summaries delivered straight to executive decision-makers' mailboxes.

### 1.2 Context & Mission
EAI Systems is a digital transformation consultancy specializing in Enterprise Application Integration (EAI), Certified Pega BPM/DPA implementation, cloud architecture, and Agentic AI solutions via its proprietary platform, **PhantomOps** (sovereign, Arabic-native AI agent workforce tailored for BFSI and enterprise automation in the GCC and global markets). 

Rather than indiscriminately scraping and spamming internal mailboxes with every public procurement listing, this system operates as a **hyper-targeted opportunity filter**. It uses a multi-tier pipeline combining deterministic criteria with semantic vector searching and LLM reasoning to ensure that EAI leadership only receives high-probability, high-value procurement opportunities matched precisely to EAI's operational capabilities.

---

## 2. System Architecture & Components

The application codebase is structured as follows:

```
c:/Users/USER/Downloads/RFPCrawler/
├── .env                              # Groq API Key & App Config
├── config.py                         # Settings Pydantic Model
├── main.py                           # FastAPI / Uvicorn Server Entry Point
├── requirements.txt                  # Python dependencies
├── rfp_intelligence.db               # SQLite database
├── RFP_Intelligence_System_Architecture.md
└── src/
    ├── api/
    │   └── server.py                 # FastAPI Routes & Admin Web Dashboard
    ├── db/
    │   ├── database.py               # SQLAlchemy Engine & Session
    │   └── models.py                 # DB Tables Schema (Portals, RFPs, AI Evaluations)
    ├── intelligence/
    │   ├── llm_reasoner.py           # Groq LLM Evaluation Engine
    │   ├── pipeline.py               # Main Orchestration Engine
    │   └── stage1_filter.py          # Deterministic Keyword & Deadline Filter
    ├── services/
    │   └── email_service.py          # SMTP HTML Notification Service
    └── sources/
        ├── base_adapter.py           # Abstract Base Portal Adapter
        └── contracts_finder_adapter.py # UK Contracts Finder Live Scraper
```
