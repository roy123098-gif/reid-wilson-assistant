import unittest

from eic.profile_extraction import extract_profile_updates
from eic.service import analyze_full_advisory
from eic.tax_estimator import compute_federal_tax, get_standard_deduction


class TaxAdvisorTests(unittest.TestCase):
    def complete_family_profile(self, **updates):
        profile = {
            "tax_year": 2025,
            "filing_status": "hoh",
            "earned_income": 28_000,
            "agi": 28_000,
            "withholding": 2_500,
            "investment_income": 0,
            "num_children": 2,
            "qualifying_children_confirmed": True,
            "ssn_valid": True,
            "citizen_or_resident_all_year": True,
            "self_employed": False,
        }
        profile.update(updates)
        return profile

    def test_2025_standard_deductions(self):
        self.assertEqual(get_standard_deduction("single"), 15_000)
        self.assertEqual(get_standard_deduction("hoh"), 22_500)
        self.assertEqual(get_standard_deduction("mfj"), 30_000)

    def test_tax_schedule_boundaries(self):
        self.assertEqual(compute_federal_tax("single", 11_925), 1_192.50)
        self.assertEqual(compute_federal_tax("single", 48_475), 5_578.50)
        self.assertEqual(compute_federal_tax("hoh", 64_850), 7_442.00)
        self.assertEqual(compute_federal_tax("mfj", 96_950), 11_157.00)

    def test_family_refund_uses_withholding_tax_and_eic(self):
        advisory = analyze_full_advisory(self.complete_family_profile())["tax_advisory"]
        estimate = advisory["estimate"]
        self.assertTrue(estimate["available"])
        self.assertEqual(estimate["taxable_income"], 5_500)
        self.assertEqual(estimate["federal_income_tax"], 550)
        self.assertEqual(estimate["eic_amount"], 6_167)
        self.assertEqual(estimate["refund_estimate"], 8_117)

    def test_missing_withholding_blocks_refund_number(self):
        advisory = analyze_full_advisory(self.complete_family_profile(withholding=None))["tax_advisory"]
        self.assertFalse(advisory["estimate"]["available"])
        self.assertTrue(any("withheld" in item for item in advisory["estimate"]["missing"]))

    def test_self_employment_has_strong_limitation(self):
        advisory = analyze_full_advisory(self.complete_family_profile(self_employed=True))["tax_advisory"]
        self.assertEqual(advisory["estimate"]["reliability"], "low")
        self.assertTrue(any("Self-employment tax" in item for item in advisory["estimate"]["warnings"]))

    def test_withholding_extraction(self):
        updates = extract_profile_updates("My federal tax withheld was $2,500")
        self.assertEqual(updates["withholding"], 2_500)
        self.assertNotIn("earned_income", updates)


if __name__ == "__main__":
    unittest.main()
