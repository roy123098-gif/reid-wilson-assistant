from advisor_core import answer_question, load_all_indexes
from eic.itin_assistant import (
    continue_itin_session,
    is_eic_intent,
    is_itin_intent,
    itin_eic_answer,
    start_itin_session,
)
from eic.service import analyze_full_advisory, process_eic_text
from eic.tax_profile import load_tax_profile, update_tax_profile


def print_itin(payload):
    if payload.get("complete"):
        print("\nITIN GUIDE:")
        print(payload["headline"])
        print(payload["summary"])
        for item in payload.get("checklist", []):
            print(f"- {item}")
        for warning in payload.get("warnings", []):
            print(f"Important: {warning}")
        if payload.get("processing_time"):
            print(payload["processing_time"])
        return
    question = payload["question"]
    print(f"\nITIN GUIDE ({payload['step_number']} of {payload['total_steps']}):")
    print(question["title"])
    print(question["help"])
    for choice in question["choices"]:
        print(f"- {choice['value']}: {choice['label']}")


def print_eic_analysis(eic):
    eligibility = eic["eligibility"]
    estimate = eic["estimate"]
    print("\nEIC CHECK:")
    print(eic["explanation"]["headline"])
    if estimate.get("amount") is not None:
        qualifier = "preliminary " if estimate.get("is_preliminary") else ""
        print(f"2025 {qualifier}estimate: ${estimate['amount']:,.0f}")
    for item in eligibility["blockers"]:
        print(f"- Blocker: {item}")
    for item in eligibility["missing"]:
        print(f"- Still needed: {item}")
    print(estimate["note"])


def print_publication_match(answer):
    print("\nPUBLICATION 596 MATCH:")
    print(f"Answer: {answer['answer']}")
    print(f"Section: {answer['section']}")
    print(f"Confidence: {answer['confidence']}")
    print(answer["disclaimer"])


def is_tax_advisory_intent(text):
    normalized = text.lower()
    return any(term in normalized for term in (
        "refund", "tax back", "how much will i get", "how much do i owe",
        "estimate my taxes", "estimate my tax", "taxpayer advisory", "mr. reid", "tax advisor",
    ))


def print_tax_advisory(advisory):
    estimate = advisory["estimate"]
    print("\nTAXPAYER ADVISORY BY MR. REID:")
    print(advisory["headline"])
    if not estimate["available"]:
        for item in estimate["missing"]:
            print(f"- Still needed: {item}")
        return
    print(f"AGI: ${estimate['agi']:,.2f}")
    print(f"Standard deduction: ${estimate['standard_deduction']:,.2f}")
    print(f"Taxable income: ${estimate['taxable_income']:,.2f}")
    print(f"Ordinary federal income tax: ${estimate['federal_income_tax']:,.2f}")
    print(f"Withholding: ${estimate['withholding']:,.2f}")
    print(f"EIC included: ${estimate['eic_amount']:,.2f}")
    for warning in estimate["warnings"]:
        print(f"- Limitation: {warning}")
    print(estimate["disclaimer"])


def ask_question():
    section_index = load_all_indexes()
    profile = load_tax_profile()
    context = None
    itin_state = profile.get("itin_session")
    print("Reid & Wilson Personal Tax Assistant: EIC and ITIN guidance.")
    print("Type exit, quit, or q to stop.\n")

    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        if not query:
            continue
        if query.lower() in {"exit", "quit", "q"}:
            print("Goodbye.")
            break

        if itin_state and itin_state.get("active"):
            itin = continue_itin_session(itin_state, query)
            itin_state = itin["session"]
            profile = update_tax_profile(profile, itin_session=itin_state)
            print_itin(itin)
            continue
        if is_itin_intent(query):
            if is_eic_intent(query):
                response = itin_eic_answer()
                print("\n" + response["answer"])
                for detail in response["details"]:
                    print(f"- {detail}")
                continue
            itin = start_itin_session()
            itin_state = itin["session"]
            profile = update_tax_profile(profile, itin_session=itin_state)
            print_itin(itin)
            continue

        profile, _, messages, eic = process_eic_text(profile, query, persist=True)
        answer = answer_question(query, section_index, context, profile)
        context = answer["context"]
        if messages:
            print("\n" + " ".join(messages))
        print_eic_analysis(eic)
        if is_tax_advisory_intent(query):
            print_tax_advisory(analyze_full_advisory(profile)["tax_advisory"])
        print_publication_match(answer)


if __name__ == "__main__":
    ask_question()
