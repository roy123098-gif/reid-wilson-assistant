import re

from .filing_status import maybe_update_filing_status
from .tax_profile import update_tax_profile

NUMBER_WORDS = {"no": 0, "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _money_value(raw):
    value = raw.lower().replace("$", "").replace(",", "").strip()
    multiplier = 1000 if value.endswith("k") else 1
    if multiplier != 1:
        value = value[:-1]
    try:
        return float(value) * multiplier
    except ValueError:
        return None


def _extract_money(text, labels):
    label_group = "|".join(re.escape(label) for label in labels)
    patterns = (
        rf"(?:{label_group})\s*(?:is|was|of|about|around|=|:)??\s*\$?([0-9][0-9,]*(?:\.\d+)?k?)",
        rf"\$?([0-9][0-9,]*(?:\.\d+)?k?)\s+(?:in\s+)?(?:{label_group})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _money_value(match.group(1))
    return None


def extract_profile_updates(text):
    normalized = text.lower().replace("’", "'")
    updates = {}

    withholding = _extract_money(normalized, ["federal tax withheld", "federal withholding", "tax withholding", "withheld"])
    investment = _extract_money(normalized, ["investment income", "interest and dividends"])
    agi = _extract_money(normalized, ["agi", "adjusted gross income"])
    earned = _extract_money(
        normalized,
        ["earned income", "income", "wages", "made", "earned", "make", "salary", "brought home"],
    )
    if investment is not None:
        updates["investment_income"] = investment
    if withholding is not None:
        updates["withholding"] = withholding
    if agi is not None:
        updates["agi"] = agi
    if earned is not None and investment is None and withholding is None:
        updates["earned_income"] = earned

    child_match = re.search(r"\b(\d+|no|zero|one|two|three|four|five)\s+(?:qualifying\s+)?(?:kid|kids|child|children|dependents?)\b", normalized)
    if child_match:
        token = child_match.group(1)
        updates["num_children"] = int(token) if token.isdigit() else NUMBER_WORDS[token]

    age_match = re.search(r"\b(?:i am|i'm|im|age)\s+(\d{2})\b|\b(\d{2})\s+years old\b", normalized)
    if age_match:
        updates["taxpayer_age"] = int(age_match.group(1) or age_match.group(2))

    if re.search(r"\b(valid (?:social security number|ssn)|ssn is valid)\b", normalized):
        updates["ssn_valid"] = True
    if re.search(r"\b(no valid (?:social security number|ssn)|ssn is not valid|invalid ssn)\b", normalized):
        updates["ssn_valid"] = False
    if re.search(r"\b(lived|live|home was) in (?:the )?(?:u\.?s\.?|united states) (?:for )?more than half\b", normalized):
        updates["residency_confirmed"] = True
    if re.search(r"\b(?:u\.?s\.? citizen|resident alien all year|citizen all year)\b", normalized):
        updates["citizen_or_resident_all_year"] = True
    if "self-employed" in normalized or "self employed" in normalized:
        updates["self_employed"] = True

    return updates


def update_profile_from_text(profile, user_text, persist=True):
    messages = []
    updates = extract_profile_updates(user_text)
    if updates:
        if persist:
            profile = update_tax_profile(profile, **updates)
        else:
            profile = {**profile, **updates}
        labels = {
            "earned_income": "earned income",
            "agi": "AGI",
            "investment_income": "investment income",
            "withholding": "federal withholding",
            "num_children": "qualifying children",
            "taxpayer_age": "age",
            "ssn_valid": "SSN status",
            "residency_confirmed": "U.S. residency",
            "citizen_or_resident_all_year": "citizenship/resident status",
            "self_employed": "self-employment status",
        }
        messages.append("Profile details detected: " + ", ".join(labels[key] for key in updates) + ".")

    profile, status_message, detected_status = maybe_update_filing_status(profile, user_text, persist=persist)
    if status_message:
        messages.append(status_message)
    if detected_status:
        updates["filing_status"] = detected_status
    return profile, updates, messages
