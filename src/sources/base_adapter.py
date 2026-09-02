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
