import unittest

from eic.itin_assistant import (
    continue_itin_session,
    is_eic_intent,
    is_itin_intent,
    itin_eic_answer,
    start_itin_session,
)


class ItinAssistantTests(unittest.TestCase):
    def test_itin_intent_detection(self):
        self.assertTrue(is_itin_intent("Help me apply with Form W-7"))
        self.assertTrue(is_itin_intent("I need an ITIN"))
        self.assertFalse(is_itin_intent("Can I get EIC?"))

    def test_start_has_six_step_safe_wizard(self):
        result = start_itin_session()
        self.assertTrue(result["active"])
        self.assertEqual(result["step"], "applicant_type")
        self.assertEqual(result["total_steps"], 6)
        self.assertIn("does not qualify", result["eic_notice"])

    def test_invalid_choice_does_not_advance(self):
        result = start_itin_session()
        again = continue_itin_session(result["session"], "passport number 123")
        self.assertEqual(again["step"], "applicant_type")
        self.assertIn("error", again)

    def test_ssn_eligible_stops_itin_path(self):
        result = start_itin_session()
        result = continue_itin_session(result["session"], "self")
        result = continue_itin_session(result["session"], "eligible")
        self.assertTrue(result["complete"])
        self.assertEqual(result["status"], "ssn_path")

    def test_complete_dependent_caa_checklist(self):
        result = start_itin_session()
        for answer in ("dependent", "not_eligible", "new", "file_return", "yes", "caa"):
            result = continue_itin_session(result["session"], answer)
        self.assertTrue(result["complete"])
        self.assertEqual(result["status"], "checklist_ready")
        self.assertTrue(any("residency" in item.lower() for item in result["checklist"]))
        self.assertIn("9-11 weeks", result["processing_time"])

    def test_itin_and_eic_question_has_direct_warning(self):
        self.assertTrue(is_eic_intent("Can I get EITC with an ITIN?"))
        result = itin_eic_answer()
        self.assertEqual(result["mode"], "itin_eic")
        self.assertIn("does not qualify", result["answer"])


if __name__ == "__main__":
    unittest.main()
