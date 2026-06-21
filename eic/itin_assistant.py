from copy import deepcopy

IRS_LINKS = {
    "overview": "https://www.irs.gov/individuals/individual-taxpayer-identification-number",
    "apply": "https://www.irs.gov/individuals/how-do-i-apply-for-an-itin",
    "form_w7": "https://www.irs.gov/forms-pubs/about-form-w-7",
    "acceptance_agents": "https://www.irs.gov/individuals/international-taxpayers/acceptance-agent-program",
    "tac": "https://www.irs.gov/help/let-us-help-you",
}

STEP_ORDER = [
    "applicant_type", "ssn_eligibility", "application_type",
    "federal_tax_purpose", "has_passport", "submission_method",
]

QUESTIONS = {
    "applicant_type": {
        "title": "Who needs the ITIN?",
        "help": "Choose the person whose name will appear on Form W-7.",
        "choices": [
            {"value": "self", "label": "Me"},
            {"value": "spouse", "label": "My spouse"},
            {"value": "dependent", "label": "My child or dependent"},
        ],
    },
    "ssn_eligibility": {
        "title": "Is that person eligible to get a Social Security number?",
        "help": "An ITIN is only for someone who needs a federal tax number and is not eligible for an SSN.",
        "choices": [
            {"value": "not_eligible", "label": "Not eligible for an SSN"},
            {"value": "eligible", "label": "Eligible for an SSN"},
            {"value": "unsure", "label": "Not sure"},
        ],
    },
    "application_type": {
        "title": "What do you need to do?",
        "help": "Renewal uses Form W-7 too, but the supporting situation may differ.",
        "choices": [
            {"value": "new", "label": "Apply for a new ITIN"},
            {"value": "renew", "label": "Renew an expired ITIN"},
        ],
    },
    "federal_tax_purpose": {
        "title": "Why is the ITIN needed?",
        "help": "Most applicants attach a federal tax return. Applying without one requires a documented IRS exception.",
        "choices": [
            {"value": "file_return", "label": "File a federal tax return"},
            {"value": "exception", "label": "Use an IRS exception"},
            {"value": "unsure", "label": "Not sure yet"},
        ],
    },
    "has_passport": {
        "title": "Does the applicant have a current passport?",
        "help": "Do not enter a passport number. This only helps build the document checklist.",
        "choices": [
            {"value": "yes", "label": "Yes"},
            {"value": "no", "label": "No"},
        ],
    },
    "submission_method": {
        "title": "How would you prefer to apply?",
        "help": "In-person options can authenticate most supporting documents and return them at the appointment.",
        "choices": [
            {"value": "tac", "label": "IRS Taxpayer Assistance Center", "description": "Free; appointment required."},
            {"value": "vita", "label": "VITA site with ITIN services", "description": "Free; available at limited locations."},
            {"value": "caa", "label": "Certifying Acceptance Agent", "description": "Professional help; fees may vary."},
            {"value": "mail", "label": "Mail to the IRS", "description": "Use the current IRS address and document rules."},
        ],
    },
}


def is_itin_intent(text):
    normalized = text.lower().replace("-", "")
    return any(term in normalized for term in ("itin", "w7", "individual taxpayer identification"))


def is_eic_intent(text):
    normalized = text.lower()
    return any(term in normalized for term in ("eic", "eitc", "earned income credit", "earned income tax credit"))


def _question_payload(step, session):
    question = deepcopy(QUESTIONS[step])
    return {
        "active": True,
        "complete": False,
        "step": step,
        "step_number": STEP_ORDER.index(step) + 1,
        "total_steps": len(STEP_ORDER),
        "progress": round((STEP_ORDER.index(step) / len(STEP_ORDER)) * 100),
        "question": question,
        "session": session,
        "eic_notice": "An ITIN does not qualify a taxpayer for the Earned Income Credit. EIC requires the valid SSNs described in the EIC rules.",
    }


def start_itin_session():
    session = {"active": True, "step": STEP_ORDER[0], "data": {}}
    return _question_payload(STEP_ORDER[0], session)


def _final_result(session, stopped_for_ssn=False):
    data = session["data"]
    if stopped_for_ssn:
        return {
            "active": False,
            "complete": True,
            "status": "ssn_path",
            "headline": "An ITIN is not the correct path when the applicant is eligible for an SSN.",
            "summary": "Confirm SSN eligibility with the Social Security Administration before submitting Form W-7.",
            "checklist": [
                "Do not submit an ITIN application solely as a substitute for an available SSN.",
                "Review the IRS ITIN eligibility page and Social Security Administration guidance.",
            ],
            "warnings": ["An ITIN does not authorize work, provide immigration status, Social Security benefits, or EIC eligibility."],
            "processing_time": None,
            "links": IRS_LINKS,
            "session": {"active": False, "step": "complete", "data": data},
        }

    applicant = {"self": "taxpayer", "spouse": "spouse", "dependent": "child or dependent"}.get(data.get("applicant_type"), "applicant")
    purpose = data.get("federal_tax_purpose")
    passport = data.get("has_passport") == "yes"
    method = data.get("submission_method")
    checklist = [
        "Complete the current Form W-7 and review every entry before signing.",
        "Provide documents that meet the current W-7 rules for identity and foreign status.",
        "Keep copies of the application package and track any mailed package.",
    ]
    if purpose == "file_return":
        checklist.insert(1, "Attach the completed federal tax return to the W-7 application package unless IRS instructions say otherwise.")
    elif purpose == "exception":
        checklist.insert(1, "Identify the exact IRS exception and include the required exception documentation instead of assuming a tax return is optional.")
    else:
        checklist.insert(1, "Confirm whether a federal tax return must be attached or whether a documented IRS exception applies.")
    if passport:
        checklist.append("Confirm whether the passport and any dependent-residency evidence satisfy the current W-7 instructions.")
    else:
        checklist.append("Use the current W-7 document list to assemble the required combination of acceptable documents.")
    if data.get("applicant_type") == "dependent":
        checklist.append("Check the special U.S. residency-document rules for dependents.")

    method_notes = {
        "tac": "Schedule an appointment at an IRS Taxpayer Assistance Center that provides ITIN document authentication. The service is free, but staff generally review rather than prepare Form W-7.",
        "vita": "Locate a VITA site that specifically offers ITIN services. Availability is limited and document-authentication restrictions can apply.",
        "caa": "Use the official IRS Acceptance Agent list. A CAA can authenticate most documents and may charge a fee; special dependent-document limits apply.",
        "mail": "Use the current IRS ITIN mailing address. Review the risks and exact requirements before mailing original or issuing-agency-certified documents.",
    }
    checklist.append(method_notes.get(method, method_notes["mail"]))

    return {
        "active": False,
        "complete": True,
        "status": "checklist_ready",
        "headline": f"Your ITIN checklist for the {applicant} is ready.",
        "summary": "This checklist organizes the next steps but does not determine eligibility, prepare Form W-7, authenticate documents, or submit an application.",
        "checklist": checklist,
        "warnings": [
            "An ITIN is for federal tax purposes only and does not authorize work or change immigration status.",
            "An ITIN does not qualify the taxpayer for EIC.",
            "Never enter or upload passport numbers, ITINs, SSNs, birth certificates, or other identity documents here.",
        ],
        "processing_time": "The IRS currently says to allow 7 weeks, or 9-11 weeks during January 15-April 30 or when applying from overseas.",
        "links": IRS_LINKS,
        "session": {"active": False, "step": "complete", "data": data},
    }


def continue_itin_session(session, answer):
    if not isinstance(session, dict) or not session.get("active"):
        return start_itin_session()
    step = session.get("step")
    if step not in STEP_ORDER:
        return start_itin_session()
    allowed = {choice["value"] for choice in QUESTIONS[step]["choices"]}
    answer = str(answer or "").strip().lower()
    if answer not in allowed:
        payload = _question_payload(step, session)
        payload["error"] = "Choose one of the listed options so the checklist stays accurate."
        return payload

    data = dict(session.get("data") or {})
    data[step] = answer
    if step == "ssn_eligibility" and answer == "eligible":
        return _final_result({"active": False, "step": "complete", "data": data}, stopped_for_ssn=True)

    index = STEP_ORDER.index(step)
    if index == len(STEP_ORDER) - 1:
        return _final_result({"active": False, "step": "complete", "data": data})
    next_step = STEP_ORDER[index + 1]
    next_session = {"active": True, "step": next_step, "data": data}
    return _question_payload(next_step, next_session)


def itin_eic_answer():
    return {
        "mode": "itin_eic",
        "answer": "An ITIN does not qualify a taxpayer for the Earned Income Credit. EIC requires valid Social Security numbers under the EIC rules.",
        "details": [
            "An ITIN may still be used for other federal tax purposes when the person is not eligible for an SSN.",
            "Do not treat an ITIN as work authorization, immigration status, or Social Security eligibility.",
            "Use the ITIN guide for Form W-7 steps, and review EIC separately using valid-SSN requirements.",
        ],
        "links": IRS_LINKS,
        "disclaimer": "Educational guidance only. Verify current IRS instructions or consult a qualified tax professional.",
    }
