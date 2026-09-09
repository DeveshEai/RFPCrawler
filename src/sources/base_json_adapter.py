import json
import httpx
from typing import List, Dict, Any, Optional
from src.sources.base_adapter import BasePortalAdapter
from src.services.logger_service import system_logger

class BaseJSONAdapter(BasePortalAdapter):
    """
    Base JSON Adapter for Direct Free Open REST APIs.
    Bypasses HTML parsing and PDF extraction.
    Handles HTTP GET and POST requests using httpx with built-in error handling.
    """
    async def fetch_json_data(
        self,
        url: str,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        json_payload: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 20.0
    ) -> Optional[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
                if method.upper() == "POST":
                    resp = await client.post(url, params=params, json=json_payload, headers=headers)
                else:
                    resp = await client.get(url, params=params, headers=headers)

                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except Exception:
                        return {"raw_text": resp.text, "http_status": 200}
                elif resp.status_code == 202:
                    system_logger.add_log("INFO", f"[{self.__class__.__name__}] API returned HTTP 202 (Accepted / Async Processing).")
                    return {"http_status": 202, "status": "accepted"}
                else:
                    system_logger.add_log("WARN", f"[{self.__class__.__name__}] API returned HTTP status {resp.status_code}: {resp.text[:150]}")
        except json.JSONDecodeError as jde:
            system_logger.add_log("ERROR", f"[{self.__class__.__name__}] JSON decode error from {url}: {jde}")
        except httpx.TimeoutException:
            system_logger.add_log("WARN", f"[{self.__class__.__name__}] Timeout querying API endpoint: {url}")
        except Exception as e:
            system_logger.add_log("ERROR", f"[{self.__class__.__name__}] Exception querying API {url}: {e}")

        return None
