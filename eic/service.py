from .eic_calculator import estimate_eic_amount
from .eic_eligibility import basic_eic_eligibility
from .explanations import build_eic_explanation
from .profile_extraction import update_profile_from_text
from .tax_advisor import analyze_tax_advisory


def analyze_eic(profile):
    eligibility = basic_eic_eligibility(profile)
    estimate = estimate_eic_amount(profile, eligibility)
    explanation = build_eic_explanation(profile, eligibility, estimate)
    return {
        "eligibility": eligibility,
        "estimate": estimate,
        "explanation": explanation,
    }


def process_eic_text(profile, user_text, persist=True):
    profile, updates, messages = update_profile_from_text(profile, user_text, persist=persist)
    return profile, updates, messages, analyze_eic(profile)


def analyze_full_advisory(profile):
    eic = analyze_eic(profile)
    return {"eic": eic, "tax_advisory": analyze_tax_advisory(profile, eic)}
