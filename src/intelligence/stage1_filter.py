from datetime import datetime
from typing import Dict, Any, Tuple

# Negative keywords for non-IT / hardware / civil works tenders
EXCLUDED_KEYWORDS = [
    "janitorial", "cleaning service", "lawn care", "plumbing", "roof repair",
    "hardware purchase", "physical security guard", "trash collection",
    "catering", "tires", "fleet maintenance", "air conditioner", "air conditioners",
    "hvac", "laboratory equipment", "lab equipment", "furniture", "car rental",
    "vehicle", "cabling", "floral", "flowers", "vending", "gritting", "boiler",
    "painting", "construction", "roofing", "liquid handling", "pharmaceutical",
    "courier", "transport", "taxi", "fuel card", "decommissioning", "surveying",
    "grounds maintenance", "laundry", "waste", "mining", "infrastructure project",
    "capital works", "audit service", "conservation", "renewable energy", "carbon market",
    "video wall", "display screen"
]

class Stage1DeterministicFilter:
    @staticmethod
    def evaluate(rfp_data: Dict[str, Any]) -> Tuple[bool, str]:
        title = rfp_data.get("title", "").lower()
        raw_content = rfp_data.get("raw_content", "").lower()
        combined_text = f"{title} {raw_content}"

        # 1. Deadline filter
        deadline_str = rfp_data.get("submission_deadline")
        if deadline_str:
            try:
                deadline_dt = datetime.strptime(deadline_str[:10], "%Y-%m-%d")
                if deadline_dt < datetime.utcnow():
                    return False, f"Expired deadline: {deadline_str}"
            except Exception:
                pass

        # 2. Negative keyword check
        for kw in EXCLUDED_KEYWORDS:
            if kw in combined_text:
                return False, f"Matched negative keyword: '{kw}'"

        return True, "Passed Stage 1 hard filters"
