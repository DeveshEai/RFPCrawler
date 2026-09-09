import re
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

EXPIRED_YEARS = ["2015", "2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025"]

class Stage1DeterministicFilter:
    @staticmethod
    def evaluate(rfp_data: Dict[str, Any]) -> Tuple[bool, str]:
        title = rfp_data.get("title", "")
        raw_content = rfp_data.get("raw_content", "")
        submission_deadline = rfp_data.get("submission_deadline", "")
        combined_text = f"{title} {raw_content} {submission_deadline}".lower()

        # 1. Hardcoded Past Year Rejection Check near Date Keywords
        # e.g., "Updated Response Date: Sep 30, 2021", "Deadline: 2023-11-04", "Closes: Oct 15, 2022"
        date_keyword_pattern = r"(response\s*date|deadline|published|due\s*date|closes|closing|updated\s*response\s*date|archive\s*date)[:\s]{1,30}([^\n\r,]{1,50})"
        matches = re.findall(date_keyword_pattern, combined_text, re.IGNORECASE)
        for kw, date_snippet in matches:
            for past_year in EXPIRED_YEARS:
                if past_year in date_snippet:
                    return False, f"Expired contract (detected '{past_year}' in date string '{date_snippet.strip()}')"

        # Check if any expired year appears in submission_deadline or title directly
        if submission_deadline:
            for past_year in EXPIRED_YEARS:
                if past_year in str(submission_deadline):
                    return False, f"Expired deadline year detected in submission_deadline: '{past_year}'"

        # General Past Year Rejection Regex for explicitly dated SAM.gov / Portal headers
        # Matches patterns like "Sep 30, 2021", "Oct 15, 2023", "May 12, 2024"
        expired_date_regex = r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+(201[5-9]|202[0-5])\b"
        found_expired = re.search(expired_date_regex, combined_text, re.IGNORECASE)
        if found_expired:
            match_str = found_expired.group(0)
            return False, f"Expired contract date detected: '{match_str}'"

        # Standard ISO Deadline filter (%Y-%m-%d)
        if submission_deadline:
            try:
                deadline_dt = datetime.strptime(str(submission_deadline)[:10], "%Y-%m-%d")
                if deadline_dt < datetime.utcnow():
                    return False, f"Expired deadline: {submission_deadline}"
            except Exception:
                pass

        # 2. Negative keyword check
        for kw in EXCLUDED_KEYWORDS:
            if kw in combined_text:
                return False, f"Matched negative keyword: '{kw}'"

        return True, "Passed Stage 1 hard filters"
