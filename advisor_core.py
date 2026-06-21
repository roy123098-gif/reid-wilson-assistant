import json
import re
from pathlib import Path

from fuzzy_search import rank_sections

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INDEX_FILE = BASE_DIR / "sentence_index.json"

TOPICS = {
    "Earned Income": ["earned income", "wages", "self-employment", "side job"],
    "Qualifying Child": ["qualifying child", "relationship test", "residency test", "nephew", "niece", "kid"],
    "Filing Requirements": ["filing requirement", "file taxes", "must file", "filing status"],
    "Special Rules": ["tiebreaker", "joint return", "separated", "social security number", "valid SSN"],
    "Examples": ["example", "for example"],
    "Documents": ["documents", "records", "proof", "receipts", "W-2", "1099"],
    "What Changed This Year": ["what's new", "changes", "new for 2025"],
}

DOCUMENT_RULES = [
    (["wages", "job", "worked", "earned income"], ["W-2", "last paystub", "employer name and address"]),
    (["self-employment", "side job", "1099", "gig"], ["1099-NEC or 1099-K", "income log", "business expense receipts"]),
    (["child", "kid", "nephew", "niece", "dependent", "qualifying child"], ["child's SSN", "birth certificate or school record", "proof of relationship"]),
    (["lived", "residency", "stayed", "more than half"], ["school records", "medical records", "lease or shelter letter", "mail showing the child's address"]),
    (["babysitter", "daycare", "child care", "dependent care"], ["daycare receipts", "care provider name/address", "care provider tax ID if available"]),
    (["married", "separated", "filing status"], ["marriage records", "separation records", "proof of separate household if relevant"]),
]

CLARIFY_RULES = [
    (["child", "kid", "nephew", "niece", "dependent"], "Did the child live with you for more than half the year?"),
    (["income", "job", "worked", "wages", "self-employment"], "Was the income from work, self-employment, or another source?"),
    (["married", "separated", "spouse"], "What filing status do you plan to use?"),
    (["babysitter", "daycare", "care"], "Was the child care needed so you could work or look for work?"),
]


def load_sentence_index(index_file=DEFAULT_INDEX_FILE):
    if not Path(index_file).exists():
        raise FileNotFoundError("Could not find sentence_index.json. Run summarize_pub.py first.")
    with open(index_file, "r", encoding="utf-8") as f:
        return json.load(f)


def load_all_indexes():
    indexes = {}
    for path in sorted(BASE_DIR.glob("sentence_index*.json")):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        publication = "IRS Publication 596" if path.name == "sentence_index.json" else path.stem
        for title, item in data.items():
            indexes[f"{publication}: {title}"] = {**item, "publication": publication, "original_title": title}
    return indexes or load_sentence_index()


def confidence_label(score):
    if score >= 10:
        return "High"
    if score >= 5:
        return "Medium"
    return "Low"


def explain_match(result):
    terms = result.get("matched_terms") or []
    if terms:
        return "This section was chosen because it matched: " + ", ".join(terms[:8]) + "."
    return "This section was chosen because it was the closest fuzzy match to the question."


def suggest_documents(query, profile=None):
    text = query.lower()
    if profile:
        text += " " + " ".join(str(value).lower() for value in profile.values())
    docs = []
    for keywords, suggestions in DOCUMENT_RULES:
        if any(keyword.lower() in text for keyword in keywords):
            docs.extend(suggestions)
    if not docs:
        docs = ["photo ID", "Social Security cards", "income documents", "records that support your question"]
    return sorted(set(docs))


def clarification_question(query, result):
    text = f"{query} {result.get('title', '')} {result.get('summary', '')}".lower()
    for keywords, question in CLARIFY_RULES:
        if any(keyword in text for keyword in keywords):
            return question
    return "Can you share the income type, filing status, and whether any child lived with you more than half the year?"


def apply_follow_up_context(query, context):
    if not context:
        return query
    starters = ("what", "why", "how", "does", "do", "is", "are", "that", "it", "this")
    words = query.lower().split()
    if words and words[0] in starters:
        return f"{context.get('title', '')} {context.get('summary', '')} {query}"
    return query


def extract_scenario_facts(query, profile=None):
    text = query.lower()
    facts = {}
    income_match = re.search(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})", query)
    if income_match:
        facts["income"] = income_match.group(1).replace(",", "")
    child_match = re.search(r"(\d+)\s+(kid|kids|child|children|dependent|dependents)", text)
    if child_match:
        facts["children"] = child_match.group(1)
    for status in ["head of household", "single", "married", "separated", "widow"]:
        if status in text:
            facts["filing_status"] = status
            break
    if profile:
        profile_key_map = {
            "filing_status": "filing_status",
            "num_children": "children",
            "dependents": "children",
            "earned_income": "income",
            "income": "income",
            "agi": "agi",
        }
        for profile_key, fact_key in profile_key_map.items():
            if profile.get(profile_key) not in [None, ""] and fact_key not in facts:
                facts[fact_key] = profile[profile_key]
    return facts


def scenario_summary(query, profile=None):
    facts = extract_scenario_facts(query, profile)
    if not facts:
        return None
    pieces = []
    if facts.get("filing_status"):
        pieces.append(f"filing status: {facts['filing_status']}")
    if facts.get("income"):
        pieces.append(f"income mentioned: ${facts['income']}")
    if facts.get("children") or facts.get("dependents"):
        pieces.append(f"dependents/children: {facts.get('children') or facts.get('dependents')}")
    if not pieces:
        return None
    return "Scenario facts I noticed: " + "; ".join(pieces) + ". Use this as a starting point, then verify the exact IRS limits and tests."


def topic_query(topic):
    return " ".join(TOPICS.get(topic, [topic]))


def answer_question(query, section_index=None, context=None, profile=None):
    if section_index is None:
        section_index = load_all_indexes()
    effective_query = apply_follow_up_context(query, context)
    ranked = rank_sections(effective_query, section_index)
    best = ranked[0]
    confidence = confidence_label(best["score"])
    return {
        "query": query,
        "answer": best.get("best_sentence") or best.get("summary"),
        "section": best["title"],
        "summary": best["summary"],
        "score": best["score"],
        "confidence": confidence,
        "why": explain_match(best),
        "matched_terms": best.get("matched_terms", []),
        "documents": suggest_documents(query, profile),
        "clarifying_question": clarification_question(query, best) if confidence != "High" else None,
        "top_matches": ranked[:3],
        "scenario": scenario_summary(query, profile),
        "context": {"title": best["title"], "summary": best["summary"]},
        "disclaimer": "This is educational help based on your IRS publication text, not personalized tax or legal advice.",
    }


