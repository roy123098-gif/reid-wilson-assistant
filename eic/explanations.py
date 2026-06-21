STATUS_HEADLINES = {
    "potentially_eligible": "You appear to pass the EIC checks currently captured.",
    "incomplete": "A preliminary estimate is available, but important eligibility details are still missing.",
    "ineligible": "The current profile contains one or more EIC eligibility blockers.",
}


def build_eic_explanation(profile, eligibility, estimate):
    amount = estimate.get("amount")
    if estimate.get("available") and amount is not None:
        amount_text = f"${amount:,.0f}"
    else:
        amount_text = None

    lines = [STATUS_HEADLINES[eligibility["status"]]]
    if amount_text:
        label = "Preliminary estimated credit" if estimate.get("is_preliminary") else "Estimated credit"
        lines.append(f"{label}: {amount_text} for tax year {eligibility['tax_year']}.")
    if eligibility["blockers"]:
        lines.append("Eligibility blockers: " + " ".join(eligibility["blockers"]))
    if eligibility["missing"]:
        lines.append("Still needed: " + "; ".join(eligibility["missing"]) + ".")
    if eligibility["warnings"]:
        lines.append("Important notes: " + " ".join(eligibility["warnings"]))
    lines.append(estimate["note"])

    return {
        "headline": STATUS_HEADLINES[eligibility["status"]],
        "amount_text": amount_text,
        "text": " ".join(lines),
        "documents": [
            "W-2s, 1099s, and self-employment income records",
            "Social Security numbers for you, your spouse, and qualifying children",
            "School, medical, housing, or childcare records showing where each child lived",
            "Records supporting relationship, age, and filing status",
        ],
    }
