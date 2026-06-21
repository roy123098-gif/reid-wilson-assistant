import re
from functools import lru_cache
from pathlib import Path

from .eic_eligibility import INCOME_LIMITS, TAX_YEAR

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLICATION_TEXT = BASE_DIR / "Pub596_text.txt"
TABLE_START = "2025 Earned Income Credit (EIC)"

SPECIAL_MARKERS = {
    (19_100, "other", 0): (19_104, 0),
    (26_200, "mfj", 0): (26_214, 1),
    (50_400, "other", 1): (50_434, 3),
    (57_300, "other", 2): (57_310, 1),
    (57_550, "mfj", 1): (57_554, 0),
    (61_550, "other", 3): (61_555, 1),
    (64_400, "mfj", 2): (64_430, 3),
    (68_650, "mfj", 3): (68_675, 3),
}


@lru_cache(maxsize=1)
def load_eic_table():
    if not PUBLICATION_TEXT.exists():
        raise FileNotFoundError("Pub596_text.txt is required for the official 2025 EIC table lookup.")
    text = PUBLICATION_TEXT.read_text(encoding="utf-8", errors="replace")
    start = text.index(TABLE_START)
    end = text.find("\nIndex", start)
    table_text = text[start:end if end != -1 else None]
    token_pattern = re.compile(r"\*+|\d[\d,]*")
    table = {}

    for line in table_text.splitlines():
        if not re.match(r"^\s*\d", line):
            continue
        tokens = token_pattern.findall(line)
        for offset in (0, 10):
            if len(tokens) < offset + 10:
                continue
            low_token, high_token = tokens[offset:offset + 2]
            if low_token.startswith("*") or high_token.startswith("*"):
                continue
            low = int(low_token.replace(",", ""))
            high = int(high_token.replace(",", ""))
            if high - low not in (49, 50):
                continue
            credits = [int(token.replace(",", "")) if not token.startswith("*") else token for token in tokens[offset + 2:offset + 10]]
            table[low] = {"high": high, "credits": credits}

    if len(table) < 1_300:
        raise ValueError("The 2025 EIC table could not be read completely from Pub596_text.txt.")
    return table


def _row_start(amount):
    if 0 < amount < 50:
        return 1
    return int(amount // 50) * 50


def lookup_eic_credit(amount, filing_status, num_children):
    amount = float(amount or 0)
    children = min(max(int(num_children or 0), 0), 3)
    group = "mfj" if filing_status == "mfj" else "other"
    if amount <= 0 or amount >= INCOME_LIMITS[children][group]:
        return 0

    row_start = _row_start(amount)
    row = load_eic_table().get(row_start)
    if not row:
        raise ValueError(f"No 2025 EIC table row found for income ${amount:,.2f}.")
    column = children + (4 if group == "mfj" else 0)
    value = row["credits"][column]
    if isinstance(value, int):
        return value

    cutoff, special_credit = SPECIAL_MARKERS[(row_start, group, children)]
    return special_credit if amount < cutoff else 0


def estimate_eic_amount(profile, eligibility_result):
    if eligibility_result["status"] == "ineligible":
        return {
            "amount": 0,
            "available": False,
            "is_preliminary": False,
            "note": "No credit is estimated because the current profile has an eligibility blocker.",
        }

    earned_income = eligibility_result.get("earned_income")
    agi = eligibility_result.get("agi")
    filing_status = eligibility_result.get("filing_status")
    children = eligibility_result.get("num_children", 0)
    if earned_income is None or not filing_status:
        return {
            "amount": None,
            "available": False,
            "is_preliminary": True,
            "note": "Enter filing status and earned income to calculate a 2025 table estimate.",
        }

    earned_credit = lookup_eic_credit(earned_income, filing_status, children)
    amount = earned_credit
    table_income = earned_income
    if agi is not None and agi > earned_income:
        agi_credit = lookup_eic_credit(agi, filing_status, children)
        if agi_credit < amount:
            amount = agi_credit
            table_income = agi

    preliminary = eligibility_result["status"] == "incomplete"
    note = (
        "Preliminary 2025 EIC table estimate; complete the missing eligibility checks before relying on it."
        if preliminary
        else "2025 EIC table estimate based on the saved profile. Verify it against the return worksheet before filing."
    )
    if profile.get("self_employed"):
        preliminary = True
        note += " Self-employment income may require additional Publication 596 worksheets."
    return {
        "amount": amount,
        "available": True,
        "is_preliminary": preliminary,
        "table_income": table_income,
        "source": "Publication 596 (2025), EIC Table",
        "note": note,
    }
