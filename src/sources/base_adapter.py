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

async def fetch_deep_page_content(client: httpx.AsyncClient, url: str, max_chars: int = 3000) -> str:
    """Asynchronously fetches the inner detail page URL and extracts full structured body text."""
    if not url or not url.startswith("http"):
        return ""
    try:
        resp = await client.get(url, timeout=12.0)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "header", "footer", "nav", "svg", "noscript"]):
                tag.decompose()
            main_content = soup.find("main") or soup.find("div", class_=re.compile(r"content|notice|detail|description|summary|body", re.I)) or soup.body
            if main_content:
                text = main_content.get_text(" ", strip=True)
                clean_text = re.sub(r'\s+', ' ', text).strip()
                if len(clean_text) > 150:
                    return clean_text[:max_chars]
    except Exception:
        pass
    return ""

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
