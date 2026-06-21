import unittest
from datetime import date

from eic.goal_planner import goal_type_from_text, is_goal_intent, plan_goal


class GoalPlannerTests(unittest.TestCase):
    def payload(self, **updates):
        data = {
            "goal_type": "car",
            "name": "Reliable car",
            "target_amount": 12_000,
            "saved_amount": 2_000,
            "target_date": "2027-06-20",
            "monthly_contribution": 500,
            "monthly_income": 3_500,
            "monthly_expenses": 2_700,
            "emergency_fund_confirmed": True,
        }
        data.update(updates)
        return data

    def test_goal_math_and_progress(self):
        result = plan_goal(self.payload(), today=date(2026, 6, 20))
        self.assertEqual(result["remaining_amount"], 10_000)
        self.assertEqual(result["months_remaining"], 12)
        self.assertEqual(result["required_monthly"], 833.33)
        self.assertEqual(result["progress_percent"], 16.7)
        self.assertEqual(result["status"], "needs_adjustment")

    def test_on_track_goal(self):
        result = plan_goal(self.payload(monthly_contribution=900), today=date(2026, 6, 20))
        self.assertEqual(result["status"], "needs_adjustment")
        result = plan_goal(self.payload(monthly_contribution=850, monthly_expenses=2_500), today=date(2026, 6, 20))
        self.assertEqual(result["status"], "on_track")

    def test_cash_flow_gap_is_not_hidden(self):
        result = plan_goal(self.payload(monthly_expenses=3_600), today=date(2026, 6, 20))
        self.assertEqual(result["status"], "cash_flow_gap")

    def test_goal_intent_and_type(self):
        self.assertTrue(is_goal_intent("Help me save for a vacation"))
        self.assertEqual(goal_type_from_text("I need a down payment for a house"), "home")


if __name__ == "__main__":
    unittest.main()
