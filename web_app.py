import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from advisor_core import TOPICS, answer_question, load_all_indexes, topic_query
from eic.goal_planner import GOAL_TEMPLATES, goal_type_from_text, is_goal_intent, plan_goal
from eic.itin_assistant import (
    IRS_LINKS,
    continue_itin_session,
    is_eic_intent,
    is_itin_intent,
    itin_eic_answer,
    start_itin_session,
)
from eic.service import analyze_eic, analyze_full_advisory, process_eic_text
from eic.tax_profile import default_tax_profile, load_tax_profile, normalize_profile, update_tax_profile

BASE_DIR = Path(__file__).resolve().parent
HTML_FILE = BASE_DIR / "tax_assistant.html"
PRIVACY_FILE = BASE_DIR / "privacy.html"
TERMS_FILE = BASE_DIR / "terms.html"
ANALYTICS_FILE = BASE_DIR / "analytics.json"
MANIFEST_FILE = BASE_DIR / "manifest.webmanifest"
SERVICE_WORKER_FILE = BASE_DIR / "service-worker.js"
OFFLINE_FILE = BASE_DIR / "offline.html"
ASSETS_DIR = BASE_DIR / "assets"


def env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", os.environ.get("IRS_ASSISTANT_PORT", "8000")))
PUBLIC_MODE = env_flag("PUBLIC_MODE", False)
REQUIRE_HTTPS = env_flag("REQUIRE_HTTPS", PUBLIC_MODE)
ANALYTICS_ENABLED = env_flag("ANALYTICS_ENABLED", not PUBLIC_MODE)
DONATION_URL = os.environ.get("DONATION_URL", "").strip()
BRAND_NAME = os.environ.get("BRAND_NAME", "Reid & Wilson")
ANDROID_PACKAGE_NAME = os.environ.get("ANDROID_PACKAGE_NAME", "com.reidandwilson.taxpayeradvisory")
ANDROID_SHA256_CERT_FINGERPRINT = os.environ.get("ANDROID_SHA256_CERT_FINGERPRINT", "").strip()
SECTION_INDEX = load_all_indexes()

DEFAULT_ALLOWED_ORIGINS = {
    "https://reidandwilson.com",
    "https://www.reidandwilson.com",
    "http://127.0.0.1:8010",
    "http://localhost:8010",
}
ALLOWED_ORIGINS = DEFAULT_ALLOWED_ORIGINS | {
    item.strip().rstrip("/")
    for item in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if item.strip()
}
FRAME_ANCESTORS = " ".join([
    "'self'",
    "https://reidandwilson.com",
    "https://www.reidandwilson.com",
    "https://*.wixsite.com",
    "https://*.wix.com",
])

TEST_PROFILES = {
    "family": {
        "tax_year": 2025,
        "filing_status": "hoh",
        "earned_income": 28000,
        "agi": 28000,
        "num_children": 2,
        "qualifying_children_confirmed": True,
        "investment_income": 0,
        "withholding": 2500,
        "ssn_valid": True,
        "citizen_or_resident_all_year": True,
    },
    "no_children": {
        "tax_year": 2025,
        "filing_status": "single",
        "earned_income": 12000,
        "agi": 12000,
        "num_children": 0,
        "investment_income": 0,
        "withholding": 600,
        "taxpayer_age": 30,
        "ssn_valid": True,
        "citizen_or_resident_all_year": True,
        "residency_confirmed": True,
        "can_be_claimed_as_dependent": False,
        "is_qualifying_child_of_another": False,
    },
    "investment_limit": {
        "tax_year": 2025,
        "filing_status": "single",
        "earned_income": 26000,
        "agi": 26000,
        "num_children": 1,
        "qualifying_children_confirmed": True,
        "investment_income": 12000,
        "withholding": 1800,
        "ssn_valid": True,
        "citizen_or_resident_all_year": True,
    },
}

BUDGET_FIELDS = {
    "housing": "Housing",
    "utilities": "Utilities",
    "food": "Food",
    "transportation": "Transportation",
    "insurance": "Insurance",
    "childcare": "Childcare",
    "debt": "Debt payments",
    "other": "Other spending",
    "savings": "Savings goal",
}


def read_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, json.JSONDecodeError):
        return default


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def record_question(confidence):
    if not ANALYTICS_ENABLED:
        return
    analytics = read_json(ANALYTICS_FILE, {"total_questions": 0, "confidence_counts": {}})
    analytics["total_questions"] = int(analytics.get("total_questions", 0)) + 1
    counts = analytics.setdefault("confidence_counts", {})
    counts[confidence] = int(counts.get(confidence, 0)) + 1
    analytics.pop("questions", None)
    write_json(ANALYTICS_FILE, analytics)


def profile_for_ui(profile):
    data = profile.copy()
    data["income"] = profile.get("earned_income")
    data["dependents"] = profile.get("num_children")
    return data


def profile_updates_from_payload(payload):
    allowed = {
        "tax_year", "filing_status", "earned_income", "agi", "num_children",
        "investment_income", "withholding", "taxpayer_age", "spouse_age", "qualifying_children_confirmed",
        "ssn_valid", "citizen_or_resident_all_year", "residency_confirmed",
        "can_be_claimed_as_dependent", "is_qualifying_child_of_another",
        "foreign_earned_income_form", "self_employed", "separated_spouse", "disabled", "homeless",
    }
    aliases = {"income": "earned_income", "dependents": "num_children"}
    updates = {}
    for key, value in (payload or {}).items():
        field = aliases.get(key, key)
        if field in allowed:
            updates[field] = value
    return updates


def merge_profile(payload_profile, persist=False, test_mode=False):
    base = default_tax_profile() if (PUBLIC_MODE or test_mode) else load_tax_profile()
    updates = profile_updates_from_payload(payload_profile)
    merged = normalize_profile({**base, **updates})
    if persist and not PUBLIC_MODE and not test_mode:
        return update_tax_profile(base, **updates)
    return merged


def _money(value, field_name):
    if value in (None, ""):
        return 0.0
    try:
        number = float(str(value).replace(",", "").replace("$", ""))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a number.") from exc
    if number < 0 or number > 100_000_000:
        raise ValueError(f"{field_name} must be between $0 and $100,000,000.")
    return round(number, 2)


def build_budget(payload):
    income = _money(payload.get("monthly_income"), "Monthly take-home income")
    if income <= 0:
        raise ValueError("Enter monthly take-home income greater than $0.")
    expenses = {
        field: _money(payload.get(field), label)
        for field, label in BUDGET_FIELDS.items()
    }
    spending = sum(value for field, value in expenses.items() if field != "savings")
    savings_goal = expenses["savings"]
    available_after_spending = round(income - spending, 2)
    after_goal = round(available_after_spending - savings_goal, 2)
    expense_ratio = round((spending / income) * 100, 1)

    if available_after_spending < 0:
        status = "over_budget"
        headline = "Your planned spending is higher than your monthly income."
    elif after_goal < 0:
        status = "goal_gap"
        headline = "Your bills fit, but the savings goal needs an adjustment."
    else:
        status = "on_track"
        headline = "Your monthly plan has room after bills and the savings goal."

    suggestions = []
    if expenses["housing"] / income > 0.35:
        suggestions.append("Housing is more than 35% of take-home income; review this category first if you need room.")
    if expenses["debt"] / income > 0.20:
        suggestions.append("Debt payments are more than 20% of take-home income; consider a payoff plan or nonprofit credit counseling.")
    if after_goal < 0:
        suggestions.append(f"Reduce planned spending or the savings goal by at least ${abs(after_goal):,.2f}.")
    if not suggestions:
        suggestions.append("Review the plan each month and move any extra amount toward savings or high-interest debt.")

    return {
        "monthly_income": income,
        "expenses": expenses,
        "total_spending": round(spending, 2),
        "savings_goal": savings_goal,
        "available_after_spending": available_after_spending,
        "remaining_after_goal": after_goal,
        "expense_ratio": expense_ratio,
        "status": status,
        "headline": headline,
        "suggestions": suggestions,
        "disclaimer": "This budget is an educational planning tool, not individualized financial advice.",
    }


def is_tax_advisory_intent(text):
    normalized = text.lower()
    return any(term in normalized for term in (
        "refund", "tax back", "how much will i get", "how much do i owe",
        "estimate my taxes", "estimate my tax", "taxpayer advisory",
        "mr. reid", "tax advisor", "tax advisory",
    ))


def origin_allowed(origin):
    if not origin:
        return False
    origin = origin.rstrip("/")
    if origin in ALLOWED_ORIGINS:
        return True
    host = (urlparse(origin).hostname or "").lower()
    return host.endswith(".wixsite.com") or host.endswith(".wix.com")


class TaxAssistantHandler(BaseHTTPRequestHandler):
    server_version = "ReidWilsonAssistant/1.0"

    def _cors_headers(self):
        origin = self.headers.get("Origin", "")
        if origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin.rstrip("/"))
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _security_headers(self, html_response=False):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), geolocation=(), payment=()")
        if self.headers.get("X-Forwarded-Proto", "").lower() == "https":
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if html_response:
            self.send_header(
                "Content-Security-Policy",
                f"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                f"connect-src 'self'; img-src 'self' data:; frame-ancestors {FRAME_ANCESTORS}",
            )

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self._cors_headers()
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, path):
        if not path.exists():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self._security_headers(html_response=True)
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, content_type, cache_control="public, max-age=86400"):
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        if path == SERVICE_WORKER_FILE:
            self.send_header("Service-Worker-Allowed", "/")
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("Request is too large.")
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def redirect_to_https(self):
        if not REQUIRE_HTTPS:
            return False
        host = self.headers.get("Host", "")
        hostname = host.split(":", 1)[0].lower()
        if hostname in {"127.0.0.1", "localhost", "::1"}:
            return False
        if self.headers.get("X-Forwarded-Proto", "").lower() == "https":
            return False
        self.send_response(308)
        self.send_header("Location", f"https://{host}{self.path}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return True

    def log_message(self, format, *args):
        if not PUBLIC_MODE:
            super().log_message(format, *args)

    def do_OPTIONS(self):
        if self.redirect_to_https():
            return
        self.send_response(204)
        self._cors_headers()
        self._security_headers()
        self.end_headers()

    def do_GET(self):
        if self.redirect_to_https():
            return
        path = unquote(self.path.split("?", 1)[0])
        if path in {"/", "/index.html", "/eic"}:
            self.send_html(HTML_FILE)
            return
        if path == "/manifest.webmanifest":
            self.send_file(MANIFEST_FILE, "application/manifest+json; charset=utf-8")
            return
        if path == "/service-worker.js":
            self.send_file(SERVICE_WORKER_FILE, "text/javascript; charset=utf-8", "no-cache")
            return
        if path == "/offline.html":
            self.send_file(OFFLINE_FILE, "text/html; charset=utf-8", "no-cache")
            return
        if path in {"/assets/icon-192.png", "/assets/icon-512.png"}:
            self.send_file(ASSETS_DIR / Path(path).name, "image/png")
            return
        if path == "/privacy":
            self.send_html(PRIVACY_FILE)
            return
        if path == "/terms":
            self.send_html(TERMS_FILE)
            return
        if path == "/api/health":
            self.send_json({"ok": True, "tax_year": 2025, "sections": len(SECTION_INDEX), "public_mode": PUBLIC_MODE})
            return
        if path == "/.well-known/assetlinks.json":
            links = []
            if ANDROID_SHA256_CERT_FINGERPRINT:
                links.append({
                    "relation": ["delegate_permission/common.handle_all_urls"],
                    "target": {
                        "namespace": "android_app",
                        "package_name": ANDROID_PACKAGE_NAME,
                        "sha256_cert_fingerprints": [ANDROID_SHA256_CERT_FINGERPRINT],
                    },
                })
            self.send_json(links)
            return
        if path == "/api/config":
            self.send_json({
                "brand": BRAND_NAME,
                "tax_year": 2025,
                "public_mode": PUBLIC_MODE,
                "donation_url": DONATION_URL,
                "data_storage": "memory_only" if PUBLIC_MODE else "encrypted_local_profile",
                "services": ["eic", "itin", "tax_advisory", "budget", "goals"],
            })
            return
        if path == "/api/goals/templates":
            self.send_json({"templates": GOAL_TEMPLATES})
            return
        if path == "/api/topics":
            self.send_json({"topics": list(TOPICS.keys())})
            return
        if path == "/api/test":
            self.send_json({"profiles": TEST_PROFILES})
            return
        if path == "/api/itin":
            self.send_json({"itin": start_itin_session(), "links": IRS_LINKS})
            return
        if path == "/api/profile":
            profile = default_tax_profile() if PUBLIC_MODE else load_tax_profile()
            self.send_json({"profile": profile_for_ui(normalize_profile(profile)), "eic": analyze_eic(normalize_profile(profile))})
            return
        if path == "/api/analytics":
            if not ANALYTICS_ENABLED:
                self.send_json({"enabled": False})
            else:
                self.send_json({"enabled": True, **read_json(ANALYTICS_FILE, {"total_questions": 0, "confidence_counts": {}})})
            return
        if path == "/api/security":
            self.send_json({
                "public_mode": PUBLIC_MODE,
                "https_required": REQUIRE_HTTPS,
                "profile_storage": "memory_only" if PUBLIC_MODE else "encrypted_at_rest",
                "question_text_analytics": False if PUBLIC_MODE else ANALYTICS_ENABLED,
            })
            return
        self.send_error(404)

    def do_POST(self):
        if self.redirect_to_https():
            return
        try:
            payload = self.read_body()
            test_mode = bool(payload.get("test_mode"))
            if self.path == "/api/ask":
                query = str(payload.get("query", "")).strip()
                if not query:
                    self.send_json({"error": "Please enter a question."}, 400)
                    return
                profile = merge_profile(payload.get("profile"), persist=True, test_mode=test_mode)
                if is_itin_intent(query):
                    if is_eic_intent(query):
                        response = itin_eic_answer()
                        response.update({"profile": profile_for_ui(profile), "test_mode": test_mode})
                        self.send_json(response)
                        return
                    self.send_json({
                        "mode": "itin",
                        "answer": "I opened the ITIN guide. It will build a Form W-7 preparation checklist without asking for identity-document numbers.",
                        "itin": start_itin_session(),
                        "profile": profile_for_ui(profile),
                        "test_mode": test_mode,
                    })
                    return
                if is_goal_intent(query):
                    goal_type = goal_type_from_text(query)
                    self.send_json({
                        "mode": "goal",
                        "goal_type": goal_type,
                        "answer": "I opened the goal planner. Add the amount, target date, and monthly budget to build a practical savings path.",
                        "profile": profile_for_ui(profile),
                        "test_mode": test_mode,
                    })
                    return
                profile, updates, messages, eic = process_eic_text(
                    profile,
                    query,
                    persist=not PUBLIC_MODE and not test_mode,
                )
                answer = answer_question(query, SECTION_INDEX, payload.get("context"), profile)
                answer.update({
                    "eic": eic,
                    "profile": profile_for_ui(profile),
                    "profile_updates": updates,
                    "profile_messages": messages,
                    "test_mode": test_mode,
                })
                if is_tax_advisory_intent(query):
                    answer["tax_advisory"] = analyze_full_advisory(profile)["tax_advisory"]
                record_question(answer["confidence"])
                self.send_json(answer)
                return
            if self.path == "/api/itin/start":
                self.send_json({"itin": start_itin_session()})
                return
            if self.path == "/api/itin/step":
                self.send_json({
                    "itin": continue_itin_session(payload.get("session"), payload.get("answer")),
                })
                return
            if self.path == "/api/eic":
                profile = merge_profile(payload.get("profile", payload), persist=True, test_mode=test_mode)
                self.send_json({"profile": profile_for_ui(profile), "eic": analyze_eic(profile), "test_mode": test_mode})
                return
            if self.path == "/api/advisory":
                profile = merge_profile(payload.get("profile", payload), persist=True, test_mode=test_mode)
                advisory = analyze_full_advisory(profile)
                self.send_json({
                    "profile": profile_for_ui(profile),
                    "eic": advisory["eic"],
                    "tax_advisory": advisory["tax_advisory"],
                    "test_mode": test_mode,
                })
                return
            if self.path == "/api/budget":
                self.send_json({"budget": build_budget(payload)})
                return
            if self.path == "/api/goals/plan":
                self.send_json({"goal": plan_goal(payload)})
                return
            if self.path == "/api/topic":
                topic = str(payload.get("topic", "")).strip()
                profile = merge_profile(payload.get("profile"), test_mode=test_mode)
                answer = answer_question(topic_query(topic), SECTION_INDEX, None, profile)
                answer.update({"query": topic, "eic": analyze_eic(profile), "profile": profile_for_ui(profile)})
                self.send_json(answer)
                return
            if self.path == "/api/profile":
                profile = merge_profile(payload.get("profile", payload), persist=True, test_mode=test_mode)
                self.send_json({
                    "saved": not PUBLIC_MODE and not test_mode,
                    "session_only": PUBLIC_MODE or test_mode,
                    "profile": profile_for_ui(profile),
                    "eic": analyze_eic(profile),
                })
                return
            self.send_error(404)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)


def run():
    server = ThreadingHTTPServer((HOST, PORT), TaxAssistantHandler)
    print(f"{BRAND_NAME} assistant running at http://{HOST}:{PORT}")
    print(f"Public mode: {'on' if PUBLIC_MODE else 'off'}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
