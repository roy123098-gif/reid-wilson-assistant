import unittest

from eic.eic_calculator import load_eic_table, lookup_eic_credit
from eic.eic_eligibility import basic_eic_eligibility
from eic.profile_extraction import extract_profile_updates
from eic.service import analyze_eic


class EicEngineTests(unittest.TestCase):
    def complete_profile(self, **updates):
        profile = {
            "tax_year": 2025,
            "filing_status": "hoh",
            "earned_income": 28_000,
            "agi": 28_000,
            "investment_income": 0,
            "num_children": 2,
            "qualifying_children_confirmed": True,
            "ssn_valid": True,
            "citizen_or_resident_all_year": True,
        }
        profile.update(updates)
        return profile

    def test_complete_publication_table_is_loaded(self):
        self.assertEqual(len(load_eic_table()), 1374)

    def test_publication_example_returns_842(self):
        self.assertEqual(lookup_eic_credit(2455, "single", 1), 842)

    def test_special_income_cutoffs(self):
        self.assertEqual(lookup_eic_credit(26205, "mfj", 0), 1)
        self.assertEqual(lookup_eic_credit(26214, "mfj", 0), 0)
        self.assertEqual(lookup_eic_credit(68660, "mfj", 3), 3)
        self.assertEqual(lookup_eic_credit(68675, "mfj", 3), 0)

    def test_plain_english_profile_extraction(self):
        updates = extract_profile_updates("I made 28,000 and I am 34 with two kids")
        self.assertEqual(updates["earned_income"], 28_000)
        self.assertEqual(updates["taxpayer_age"], 34)
        self.assertEqual(updates["num_children"], 2)

    def test_complete_family_scenario(self):
        result = analyze_eic(self.complete_profile())
        self.assertEqual(result["eligibility"]["status"], "potentially_eligible")
        self.assertEqual(result["estimate"]["amount"], 6167)

    def test_missing_child_tests_are_not_assumed(self):
        result = basic_eic_eligibility(self.complete_profile(qualifying_children_confirmed=None))
        self.assertEqual(result["status"], "incomplete")
        self.assertTrue(any("relationship" in item for item in result["missing"]))

    def test_investment_income_over_limit_blocks_credit(self):
        result = analyze_eic(self.complete_profile(investment_income=12_000))
        self.assertEqual(result["eligibility"]["status"], "ineligible")
        self.assertEqual(result["estimate"]["amount"], 0)


if __name__ == "__main__":
    unittest.main()
