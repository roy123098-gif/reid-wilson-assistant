import re

from .tax_profile import update_tax_profile

STATUS_LABELS = {
    "single": "Single",
    "hoh": "Head of household",
    "mfj": "Married filing jointly",
    "mfs": "Married filing separately",
    "qss": "Qualifying surviving spouse",
}

PATTERNS = (
    ("hoh", r"\b(head of household|single (?:mom|mother|dad|father|parent))\b"),
    ("mfj", r"\b(married filing jointly|file jointly|filing jointly|joint return|file together)\b"),
    ("mfs", r"\b(married filing separately|file separately|filing separately)\b"),
    ("qss", r"\b(qualifying surviving spouse|surviving spouse)\b"),
    ("single", r"\b(i am single|i'm single|im single|filing single|not married|divorced)\b"),
)


def detect_filing_status_from_text(text):
    normalized = text.lower().replace("’", "'")
    for status, pattern in PATTERNS:
        if re.search(pattern, normalized):
            return status
    return None


def maybe_update_filing_status(profile, user_text, persist=True):
    detected = detect_filing_status_from_text(user_text)
    if not detected:
        return profile, None, None

    current = profile.get("filing_status")
    if current and current != detected:
        message = (
            f"Your saved filing status is {STATUS_LABELS[current]}, but this question sounds like "
            f"{STATUS_LABELS[detected]}. Update the profile if the saved status is wrong."
        )
        return profile, message, None

    if current == detected:
        return profile, None, None

    if persist:
        profile = update_tax_profile(profile, filing_status=detected)
    else:
        profile = {**profile, "filing_status": detected}
    return profile, f"Filing status detected: {STATUS_LABELS[detected]}.", detected
