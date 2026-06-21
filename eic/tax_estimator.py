TAX_YEAR = 2025

STANDARD_DEDUCTIONS = {
    "single": 15_000,
    "mfs": 15_000,
    "hoh": 22_500,
    "mfj": 30_000,
    "qss": 30_000,
}

TAX_BRACKETS = {
    "single": [(11_925, .10), (48_475, .12), (103_350, .22), (197_300, .24), (250_525, .32), (626_350, .35), (None, .37)],
    "mfs": [(11_925, .10), (48_475, .12), (103_350, .22), (197_300, .24), (250_525, .32), (375_800, .35), (None, .37)],
    "hoh": [(17_000, .10), (64_850, .12), (103_350, .22), (197_300, .24), (250_500, .32), (626_350, .35), (None, .37)],
    "mfj": [(23_850, .10), (96_950, .12), (206_700, .22), (394_600, .24), (501_050, .32), (751_600, .35), (None, .37)],
}
TAX_BRACKETS["qss"] = TAX_BRACKETS["mfj"]

IRS_SOURCES = {
    "inflation_adjustments": "https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2025",
    "form_1040": "https://www.irs.gov/forms-pubs/about-form-1040",
}


def get_standard_deduction(filing_status):
    return STANDARD_DEDUCTIONS.get((filing_status or "").lower())


def compute_federal_tax(filing_status, taxable_income):
    status = (filing_status or "").lower()
    if status not in TAX_BRACKETS:
        raise ValueError("A supported filing status is required for the tax estimate.")
    taxable_income = max(float(taxable_income or 0), 0)
    tax = 0.0
    lower = 0.0
    for upper, rate in TAX_BRACKETS[status]:
        if taxable_income <= lower:
            break
        if upper is None:
            tax += (taxable_income - lower) * rate
            break
        tax += (min(taxable_income, upper) - lower) * rate
        lower = upper
    return round(max(tax, 0), 2)


def estimate_tax_and_refund(profile, eic_analysis):
    filing_status = profile.get("filing_status")
    agi = profile.get("agi") if profile.get("agi") is not None else profile.get("earned_income")
    withholding = profile.get("withholding")
    missing = []
    if not filing_status:
        missing.append("filing status")
    if agi is None:
        missing.append("adjusted gross income (AGI)")
    if withholding is None:
        missing.append("federal income tax withheld from W-2s and 1099s")
    if missing:
        return {"tax_year": TAX_YEAR, "status": "incomplete", "available": False, "missing": missing, "warnings": [], "sources": IRS_SOURCES, "disclaimer": "Complete the missing fields before using this limited educational estimate."}

    deduction = get_standard_deduction(filing_status)
    if deduction is None:
        raise ValueError("Unsupported filing status for tax estimate.")
    taxable_income = max(float(agi) - deduction, 0)
    federal_income_tax = compute_federal_tax(filing_status, taxable_income)
    eligibility = eic_analysis["eligibility"]
    eic_estimate = eic_analysis["estimate"]
    eic_amount = float(eic_estimate.get("amount") or 0)
    warnings = []
    if eligibility["status"] == "ineligible":
        eic_amount = 0
    if eligibility["status"] == "incomplete":
        warnings.append("The EIC amount is preliminary because EIC eligibility information is incomplete.")
    if profile.get("self_employed"):
        warnings.append("Self-employment tax and related deductions are not included, so this is not a reliable refund estimate for self-employment income.")
    if float(profile.get("investment_income") or 0) > 0:
        warnings.append("Capital gains and qualified dividends can use different tax rates; this estimator treats taxable income as ordinary income.")
    warnings.extend([
        "This estimate assumes the standard deduction and does not compare itemized deductions.",
        "Child tax credit, education credits, marketplace health-insurance credits, estimated payments, and other taxes or credits are not included.",
        "Additional standard deductions for age or blindness are not included.",
    ])
    net = round(float(withholding) + eic_amount - federal_income_tax, 2)
    return {
        "tax_year": TAX_YEAR, "status": "available", "available": True,
        "reliability": "low" if profile.get("self_employed") or profile.get("investment_income") else "limited",
        "filing_status": filing_status, "agi": round(float(agi), 2),
        "standard_deduction": float(deduction), "taxable_income": round(taxable_income, 2),
        "federal_income_tax": federal_income_tax, "withholding": round(float(withholding), 2),
        "eic_amount": round(eic_amount, 2), "refund_estimate": max(net, 0),
        "balance_due": max(-net, 0), "missing": [], "warnings": warnings,
        "sources": IRS_SOURCES,
        "disclaimer": "Limited educational estimate only. It is not a completed tax return or an IRS refund calculation.",
    }
