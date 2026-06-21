import calendar
import math
import re
from datetime import date, datetime

GOAL_TEMPLATES = {
    "car": {
        "label": "Car",
        "default_name": "Reliable car fund",
        "planning_items": [
            "Include sales tax, registration, insurance, inspection, and immediate maintenance in the target.",
            "Compare the total cost of buying, financing, insurance, fuel, and repairs before choosing a vehicle.",
        ],
    },
    "vacation": {
        "label": "Vacation",
        "default_name": "Vacation fund",
        "planning_items": [
            "Include transportation, lodging, food, activities, tips, and a small travel buffer.",
            "A cash-funded trip avoids carrying vacation costs as high-interest debt afterward.",
        ],
    },
    "home": {
        "label": "Home",
        "default_name": "Home purchase fund",
        "planning_items": [
            "Plan separately for down payment, closing costs, moving, inspections, and initial repairs.",
            "A savings target is not a mortgage-affordability decision; compare the future payment with the full household budget.",
        ],
    },
    "emergency": {
        "label": "Emergency fund",
        "default_name": "Emergency cushion",
        "planning_items": [
            "Base the target on essential expenses and the risks your household actually faces.",
            "Keep emergency savings accessible and separate from routine spending.",
        ],
    },
    "custom": {
        "label": "Custom goal",
        "default_name": "Savings goal",
        "planning_items": [
            "Define exactly what the target must cover before choosing the amount.",
            "Review the target whenever the expected cost or timeline changes.",
        ],
    },
}


def _amount(value, label):
    if value in (None, ""):
        return 0.0
    try:
        result = float(str(value).replace(",", "").replace("$", ""))
    except ValueError as exc:
        raise ValueError(f"{label} must be a number.") from exc
    if result < 0 or result > 100_000_000:
        raise ValueError(f"{label} must be between $0 and $100,000,000.")
    return round(result, 2)


def _date(value, label):
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a valid date.") from exc


def _add_months(start, months):
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def plan_goal(payload, today=None):
    today = today or date.today()
    goal_type = str(payload.get("goal_type") or "custom").lower()
    if goal_type not in GOAL_TEMPLATES:
        raise ValueError("Choose car, vacation, home, emergency, or custom goal.")
    name = str(payload.get("name") or GOAL_TEMPLATES[goal_type]["default_name"]).strip()[:80]
    target = _amount(payload.get("target_amount"), "Target amount")
    saved = _amount(payload.get("saved_amount"), "Amount already saved")
    planned = _amount(payload.get("monthly_contribution"), "Planned monthly contribution")
    income = _amount(payload.get("monthly_income"), "Monthly take-home income")
    expenses = _amount(payload.get("monthly_expenses"), "Monthly expenses")
    target_date = _date(payload.get("target_date"), "Target date")
    if target <= 0:
        raise ValueError("Target amount must be greater than $0.")
    if target_date <= today:
        raise ValueError("Target date must be in the future.")

    gap = max(target - saved, 0)
    days_remaining = (target_date - today).days
    months_remaining = max(1, math.ceil(days_remaining / 30.4375))
    required_monthly = round(gap / months_remaining, 2)
    available_cash = round(income - expenses, 2)

    if gap == 0:
        status = "complete"
        headline = "Goal funded."
    elif available_cash <= 0:
        status = "cash_flow_gap"
        headline = "The monthly budget needs attention before funding this goal."
    elif planned <= 0:
        status = "contribution_needed"
        headline = "Choose a monthly contribution to create a completion plan."
    elif planned + 0.01 < required_monthly:
        status = "needs_adjustment"
        headline = "The current contribution will not reach the target by the selected date."
    elif planned > available_cash:
        status = "needs_adjustment"
        headline = "The planned contribution is higher than the available monthly cash."
    else:
        status = "on_track"
        headline = "The contribution is on track for the selected target date."

    projected_months = math.ceil(gap / planned) if gap > 0 and planned > 0 else None
    projected_date = _add_months(today, projected_months).isoformat() if projected_months is not None else None
    progress = min(round((saved / target) * 100, 1), 100)
    milestone_targets = [25, 50, 75, 100]
    next_percent = next((value for value in milestone_targets if value > progress), 100)
    next_milestone_amount = round(target * next_percent / 100, 2)

    suggestions = [
        "Pay essential bills and required minimum debt payments before making the goal contribution.",
        "Schedule the contribution shortly after payday so it is separated before discretionary spending.",
        "Review progress monthly and change the amount or date when income or expenses change.",
    ] + GOAL_TEMPLATES[goal_type]["planning_items"]
    if required_monthly > max(available_cash, 0):
        suggestions.insert(0, "The selected date requires more than the current available cash. Reduce the target, extend the date, lower expenses, or increase income.")
    if goal_type != "emergency" and not payload.get("emergency_fund_confirmed"):
        suggestions.append("Consider building an emergency cushion alongside this goal so an unexpected expense does not erase progress.")

    return {
        "goal_type": goal_type,
        "goal_label": GOAL_TEMPLATES[goal_type]["label"],
        "name": name,
        "target_amount": target,
        "saved_amount": saved,
        "remaining_amount": round(gap, 2),
        "target_date": target_date.isoformat(),
        "months_remaining": months_remaining,
        "required_monthly": required_monthly,
        "planned_monthly": planned,
        "monthly_income": income,
        "monthly_expenses": expenses,
        "available_monthly_cash": available_cash,
        "projected_months": projected_months,
        "projected_date": projected_date,
        "progress_percent": progress,
        "next_milestone_percent": next_percent,
        "next_milestone_amount": next_milestone_amount,
        "status": status,
        "headline": headline,
        "suggestions": suggestions,
        "assumptions": [
            "No investment return or interest is assumed.",
            "Income and expenses are assumed to remain unchanged.",
            "This is an educational savings plan, not investment, lending, or mortgage advice.",
        ],
    }


def goal_type_from_text(text):
    normalized = text.lower()
    if re.search(r"\b(car|vehicle|auto)\b", normalized):
        return "car"
    if re.search(r"\b(vacation|trip|travel)\b", normalized):
        return "vacation"
    if re.search(r"\b(home|house|down payment)\b", normalized):
        return "home"
    if re.search(r"\b(emergency|rainy day)\b", normalized):
        return "emergency"
    return "custom"


def is_goal_intent(text):
    normalized = text.lower()
    return any(term in normalized for term in (
        "saving for", "save for", "savings goal", "financial goal",
        "buy a car", "buy a house", "down payment", "vacation fund",
        "emergency fund", "goal planner", "show my goal",
    ))
