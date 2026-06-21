import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from .secure_store import EncryptedStoreError, get_or_create_key, read_encrypted_json, remove_plaintext_file, write_encrypted_json

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / ".tax_data"
PROFILE_FILE = DATA_DIR / "user_tax_profile.enc"
LEGACY_PROFILE_FILE = DATA_DIR / "user_tax_profile.json"

FILING_STATUSES = {"single", "hoh", "mfj", "mfs", "qss"}
DEFAULT_ITIN_SESSION = {"active": False, "step": "start", "data": {}}

DEFAULT_PROFILE = {
    "tax_year": 2025,
    "filing_status": None,
    "earned_income": None,
    "agi": None,
    "num_children": 0,
    "children": [],
    "qualifying_children_confirmed": None,
    "investment_income": 0,
    "withholding": None,
    "taxpayer_age": None,
    "spouse_age": None,
    "ssn_valid": None,
    "citizen_or_resident_all_year": None,
    "residency_confirmed": None,
    "can_be_claimed_as_dependent": None,
    "is_qualifying_child_of_another": None,
    "foreign_earned_income_form": False,
    "self_employed": False,
    "separated_spouse": None,
    "disabled": False,
    "homeless": False,
    "itin_session": deepcopy(DEFAULT_ITIN_SESSION),
    "last_updated": None,
}

NUMERIC_FIELDS = {"earned_income", "agi", "investment_income", "withholding"}
INTEGER_FIELDS = {"tax_year", "num_children", "taxpayer_age", "spouse_age"}
BOOLEAN_FIELDS = {"foreign_earned_income_form", "self_employed", "disabled", "homeless"}
OPTIONAL_BOOLEAN_FIELDS = {
    "qualifying_children_confirmed", "ssn_valid", "citizen_or_resident_all_year",
    "residency_confirmed", "can_be_claimed_as_dependent",
    "is_qualifying_child_of_another", "separated_spouse",
}
ITIN_DATA_FIELDS = {
    "applicant_type", "ssn_eligibility", "application_type",
    "federal_tax_purpose", "has_passport", "submission_method",
}


def ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_tax_profile():
    return deepcopy(DEFAULT_PROFILE)


def _normalize_bool(value, optional=False):
    if optional and value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "1", "on"}:
            return True
        if normalized in {"false", "no", "n", "0", "off"}:
            return False
    return bool(value)


def normalize_filing_status(value):
    if value in (None, ""):
        return None
    status = str(value).strip().lower().replace(" ", "_")
    aliases = {
        "head_of_household": "hoh",
        "married_filing_jointly": "mfj",
        "married_filing_separately": "mfs",
        "qualifying_surviving_spouse": "qss",
        "surviving_spouse": "qss",
    }
    status = aliases.get(status, status)
    if status not in FILING_STATUSES:
        raise ValueError(f"Unknown filing status: {value}")
    return status


def normalize_itin_session(value):
    if not isinstance(value, dict):
        return deepcopy(DEFAULT_ITIN_SESSION)
    data = value.get("data") if isinstance(value.get("data"), dict) else {}
    return {
        "active": bool(value.get("active")),
        "step": str(value.get("step") or "start"),
        "data": {key: data[key] for key in ITIN_DATA_FIELDS if key in data},
    }


def normalize_profile(profile):
    cleaned = default_tax_profile()
    cleaned.update(profile or {})
    cleaned["filing_status"] = normalize_filing_status(cleaned.get("filing_status"))
    for field in NUMERIC_FIELDS:
        value = cleaned.get(field)
        cleaned[field] = None if value in (None, "") else float(str(value).replace(",", ""))
    for field in INTEGER_FIELDS:
        value = cleaned.get(field)
        cleaned[field] = None if value in (None, "") else int(value)
    cleaned["tax_year"] = cleaned.get("tax_year") or 2025
    cleaned["num_children"] = max(0, cleaned.get("num_children") or 0)
    for field in BOOLEAN_FIELDS:
        cleaned[field] = _normalize_bool(cleaned.get(field))
    for field in OPTIONAL_BOOLEAN_FIELDS:
        cleaned[field] = _normalize_bool(cleaned.get(field), optional=True)
    if not isinstance(cleaned.get("children"), list):
        cleaned["children"] = []
    cleaned["itin_session"] = normalize_itin_session(cleaned.get("itin_session"))
    return cleaned


def load_tax_profile():
    ensure_data_dir()
    key = get_or_create_key(DATA_DIR)
    if PROFILE_FILE.exists():
        return normalize_profile(read_encrypted_json(PROFILE_FILE, key))
    if LEGACY_PROFILE_FILE.exists():
        try:
            with open(LEGACY_PROFILE_FILE, "r", encoding="utf-8") as file:
                profile = normalize_profile(json.load(file))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise EncryptedStoreError("The legacy plaintext tax profile could not be migrated.") from exc
        saved = save_tax_profile(profile)
        remove_plaintext_file(LEGACY_PROFILE_FILE)
        return saved
    return save_tax_profile(default_tax_profile())


def save_tax_profile(profile):
    ensure_data_dir()
    profile = normalize_profile(profile)
    profile["last_updated"] = _now_iso()
    write_encrypted_json(PROFILE_FILE, profile, get_or_create_key(DATA_DIR))
    return profile


def update_tax_profile(profile=None, **updates):
    profile = load_tax_profile() if profile is None else profile
    unknown = sorted(set(updates) - set(DEFAULT_PROFILE))
    if unknown:
        raise KeyError(f"Unknown tax profile field(s): {', '.join(unknown)}")
    merged = profile.copy()
    merged.update(updates)
    return save_tax_profile(merged)


def reset_tax_profile():
    return save_tax_profile(default_tax_profile())
