from .tax_estimator import estimate_tax_and_refund


def analyze_tax_advisory(profile, eic_analysis):
    estimate = estimate_tax_and_refund(profile, eic_analysis)
    if not estimate["available"]:
        headline = "More information is needed for a tax and refund estimate."
    elif estimate["refund_estimate"] > 0:
        headline = f"Limited estimated federal refund: ${estimate['refund_estimate']:,.2f}"
    elif estimate["balance_due"] > 0:
        headline = f"Limited estimated federal balance due: ${estimate['balance_due']:,.2f}"
    else:
        headline = "The included amounts currently produce no estimated refund or balance due."
    return {"brand": "Taxpayer Advisory by Mr. Reid", "headline": headline, "estimate": estimate}
