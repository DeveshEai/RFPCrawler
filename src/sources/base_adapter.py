from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BasePortalAdapter(ABC):
    @property
    @abstractmethod
    def portal_id(self) -> str:
        pass

    @property
    @abstractmethod
    def portal_name(self) -> str:
        pass

    @property
    @abstractmethod
    def country(self) -> str:
        pass

    @property
    @abstractmethod
    def portal_type(self) -> str:
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        pass

    @abstractmethod
    async def fetch_latest_rfps(self, keywords: List[str] = None, max_items: int = 10) -> List[Dict[str, Any]]:
        pass

import httpx
import re
from bs4 import BeautifulSoup

import io
import pypdf

async def extract_pdf_text_from_url(client: httpx.AsyncClient, pdf_url: str, max_chars: int = 4000) -> str:
    """Downloads a PDF in memory and extracts readable text across pages."""
    try:
        resp = await client.get(pdf_url, timeout=15.0)
        if resp.status_code == 200 and resp.content:
            pdf_file = io.BytesIO(resp.content)
            reader = pypdf.PdfReader(pdf_file)
            extracted = []
            for page in reader.pages[:10]:
                text = page.extract_text()
                if text:
                    extracted.append(text)
            full_text = " ".join(extracted)
            clean_text = re.sub(r'\s+', ' ', full_text).strip()
            if len(clean_text) > 100:
                return clean_text[:max_chars]
    except Exception:
        pass
    return ""

def find_pdf_links_in_html(soup: BeautifulSoup, page_url: str) -> List[str]:
    """Finds all downloadable PDF attachment and specification document URLs within a notice webpage."""
    pdf_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        lower_href = href.lower()
        
        # Match explicit .pdf or common tender document download endpoints
        is_doc = (
            lower_href.endswith(".pdf") or 
            ".pdf?" in lower_href or 
            "/attachment/" in lower_href or 
            "/download" in lower_href or
            "resources/files" in lower_href or
            "tender_document" in lower_href or
            "notice/attachment" in lower_href
        )

        if is_doc and not lower_href.startswith("javascript:") and not lower_href.startswith("#"):
            if not href.startswith("http"):
                if href.startswith("/"):
                    match = re.match(r'(https?://[^/]+)', page_url)
                    base_domain = match.group(1) if match else page_url
                    href = base_domain + href
                else:
                    href = page_url.rstrip("/") + "/" + href
            if href not in pdf_links:
                pdf_links.append(href)
    return pdf_links

async def fetch_deep_page_content(client: httpx.AsyncClient, url: str, max_chars: int = 3000) -> tuple:
    """Asynchronously fetches inner detail page URL, extracts body text, and checks for attached PDF specs."""
    if not url or not url.startswith("http"):
        return ("", "")

    # Direct PDF target check
    if url.lower().endswith(".pdf") or ".pdf?" in url.lower():
        pdf_text = await extract_pdf_text_from_url(client, url, max_chars=max_chars)
        return (pdf_text, url)

    try:
        resp = await client.get(url, timeout=12.0)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Check for PDF attachment links
            pdf_links = find_pdf_links_in_html(soup, url)
            pdf_url = pdf_links[0] if pdf_links else ""
            pdf_extra_text = ""
            if pdf_url:
                pdf_extra_text = await extract_pdf_text_from_url(client, pdf_url, max_chars=2000)

            for tag in soup(["script", "style", "header", "footer", "nav", "svg", "noscript"]):
                tag.decompose()
            main_content = soup.find("main") or soup.find("div", class_=re.compile(r"content|notice|detail|description|summary|body", re.I)) or soup.body
            if main_content:
                text = main_content.get_text(" ", strip=True)
                clean_text = re.sub(r'\s+', ' ', text).strip()
                combined_text = f"{clean_text} {pdf_extra_text}".strip()
                if len(combined_text) > 150:
                    return (combined_text[:max_chars], pdf_url)
    except Exception:
        pass
    return ("", "")

NON_RFP_URL_PATTERNS = [
    "/blog", "/glossary", "/article", "/resources/", "/post/", "/news/",
    "/pricing", "/features", "/templates", "/product/", "/solutions/",
    "inventive.ai", "procurementsciences.com", "uplandsoftware.com",
    "sparrowgenie.com", "arphie.ai", "medium.com", "linkedin.com"
]

NON_RFP_TITLE_PATTERNS = [
    "best tools", "top 5", "top 8", "top 10", "what is", "definition",
    "examples", "templates", "how to", " software ", "guide to", "tips for",
    "checklist", "ultimate guide", "best rfp", "platforms", "comparison"
]

def is_valid_rfp_notice(title: str, url: str) -> bool:
    """Returns False if the result is a blog, glossary, marketing ad, or non-tender page."""
    lower_title = title.lower()
    lower_url = url.lower()

    if any(p in lower_url for p in NON_RFP_URL_PATTERNS):
        return False

    if any(p in lower_title for p in NON_RFP_TITLE_PATTERNS):
        return False

    return True
