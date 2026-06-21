TAX_YEAR = 2025
INVESTMENT_INCOME_LIMIT = 11_950
INCOME_LIMITS = {
    0: {"other": 19_104, "mfj": 26_214},
    1: {"other": 50_434, "mfj": 57_554},
    2: {"other": 57_310, "mfj": 64_430},
    3: {"other": 61_555, "mfj": 68_675},
}
MAX_CREDITS = {0: 649, 1: 4_328, 2: 7_152, 3: 8_046}


def _child_bucket(value):
    return min(max(int(value or 0), 0), 3)


def basic_eic_eligibility(profile):
    blockers = []
    missing = []
    warnings = []

    tax_year = int(profile.get("tax_year") or TAX_YEAR)
    filing_status = profile.get("filing_status")
    earned_income = profile.get("earned_income")
    agi = profile.get("agi")
    investment_income = profile.get("investment_income")
    children = _child_bucket(profile.get("num_children"))

    if tax_year != TAX_YEAR:
        blockers.append("This calculator currently supports only tax year 2025.")
    if not filing_status:
        missing.append("filing status")
    elif filing_status == "mfs":
        if profile.get("separated_spouse") is True:
            warnings.append("Married filing separately is being evaluated under the special separated-spouse rule.")
        elif profile.get("separated_spouse") is False:
            blockers.append("Married filing separately requires the special separated-spouse rules to claim EIC.")
        else:
            missing.append("whether you meet the special separated-spouse rules")

    if earned_income is None:
        missing.append("earned income")
    elif earned_income <= 0:
        blockers.append("Earned income must be greater than zero.")
    if agi is None and earned_income is not None:
        agi = earned_income
        warnings.append("AGI was not entered, so earned income is being used as a temporary AGI estimate.")

    if investment_income is None:
        missing.append("investment income")
    elif investment_income > INVESTMENT_INCOME_LIMIT:
        blockers.append(f"Investment income is over the 2025 limit of ${INVESTMENT_INCOME_LIMIT:,.0f}.")
    if profile.get("ssn_valid") is False:
        blockers.append("A valid work-authorized Social Security number is required by the return due date.")
    elif profile.get("ssn_valid") is None:
        missing.append("valid Social Security number confirmation")
    if profile.get("citizen_or_resident_all_year") is False:
        blockers.append("You generally must be a U.S. citizen or resident alien all year.")
    elif profile.get("citizen_or_resident_all_year") is None:
        missing.append("U.S. citizen or resident-alien status")
    if profile.get("foreign_earned_income_form"):
        blockers.append("Filing Form 2555 generally prevents claiming the EIC.")

    if children == 0:
        age = profile.get("taxpayer_age")
        spouse_age = profile.get("spouse_age") if filing_status == "mfj" else None
        if age is None and spouse_age is None:
            missing.append("age (required when claiming EIC without a qualifying child)")
        elif not any(25 <= value < 65 for value in (age, spouse_age) if value is not None):
            blockers.append("Without a qualifying child, you or your spouse on a joint return must be at least 25 but under 65.")
        if profile.get("residency_confirmed") is False:
            blockers.append("Without a qualifying child, your main home must be in the United States for more than half the year.")
        elif profile.get("residency_confirmed") is None:
            missing.append("U.S. home for more than half the year")
        if profile.get("can_be_claimed_as_dependent") is True:
            blockers.append("You cannot claim self-only EIC if another person can claim you as a dependent.")
        elif profile.get("can_be_claimed_as_dependent") is None:
            missing.append("whether another person can claim you as a dependent")
        if profile.get("is_qualifying_child_of_another") is True:
            blockers.append("You cannot claim self-only EIC if you are another person's qualifying child.")
        elif profile.get("is_qualifying_child_of_another") is None:
            missing.append("whether you are another person's qualifying child")
    elif profile.get("qualifying_children_confirmed") is not True:
        missing.append("confirmation that each child meets the relationship, age, residency, and joint-return tests")

    group = "mfj" if filing_status == "mfj" else "other"
    limit = INCOME_LIMITS[children][group]
    for label, value in (("Earned income", earned_income), ("AGI", agi)):
        if value is not None and value >= limit:
            blockers.append(f"{label} must be less than ${limit:,.0f} for this filing status and child count.")

    if blockers:
        status = "ineligible"
    elif missing:
        status = "incomplete"
    else:
        status = "potentially_eligible"

    return {
        "tax_year": tax_year,
        "status": status,
        "eligible": status == "potentially_eligible",
        "blockers": blockers,
        "missing": list(dict.fromkeys(missing)),
        "warnings": warnings,
        "filing_status": filing_status,
        "earned_income": earned_income,
        "agi": agi,
        "num_children": children,
        "income_limit": limit,
        "investment_income_limit": INVESTMENT_INCOME_LIMIT,
        "maximum_credit": MAX_CREDITS[children],
    }
