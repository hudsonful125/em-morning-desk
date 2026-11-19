"""
modules/accounts.py: email + password accounts for the website, using Supabase (free).

Why Supabase? The free website's own database (desk.db) is wiped whenever Streamlit restarts
the app, so accounts kept there would vanish. Supabase is a free online database that keeps
them for good. It also does the hard, security-sensitive part for us: it stores passwords
safely (hashed, never readable, not even by you) and checks them when people sign in.

Each person's drill answers are saved in Supabase too, in a table only they can read.

Setup (one time, ~10 minutes) is in the README under "Accounts with email and password".
When SUPABASE_URL and SUPABASE_KEY are in Streamlit's Secrets, the website asks everyone
to sign in. Without them (e.g. on your Mac), nothing changes.

We talk to Supabase with plain `requests` calls to its web API, so there's nothing new to install.
"""

import os

import requests

TIMEOUT = 15  # seconds to wait for Supabase before giving up
MIN_PASSWORD_LENGTH = 8

# The drill_results columns we save and load (same names as in desk.db, so drill.py and
# stats.py work unchanged).
COLUMNS = ["date", "question_type", "correct", "seconds", "question", "your_answer", "right_answer"]


class AccountError(Exception):
    """Something went wrong talking to Supabase. The message is safe to show on the page."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def settings():
    """(url, key) from Streamlit's Secrets / .env, or None if accounts aren't set up."""
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None
    return url.strip().rstrip("/"), key.strip()


def is_set_up():
    return settings() is not None


# ---------------------------------------------------------------------------
# Talking to Supabase
# ---------------------------------------------------------------------------

def _call(method, path, json=None, params=None, token=None, extra_headers=None):
    """Send one request to Supabase and return its JSON answer (raises AccountError on failure)."""
    url, key = settings()
    headers = {"apikey": key}
    if token:  # a signed-in person's pass, so Supabase knows whose data this is
        headers["Authorization"] = f"Bearer {token}"
    headers.update(extra_headers or {})
    try:
        response = requests.request(method, url + path, json=json, params=params,
                                    headers=headers, timeout=TIMEOUT)
    except requests.RequestException:
        raise AccountError("Couldn't reach the accounts server. Try again in a minute.")
    if response.status_code >= 400:
        raise AccountError(_friendly_error(response), response.status_code)
    return response.json() if response.content else None


def _friendly_error(response):
    """Turn Supabase's error into a sentence a person can act on."""
    try:
        data = response.json()
    except ValueError:
        data = {}
    text = str(data.get("msg") or data.get("error_description") or data.get("message")
               or data.get("error") or "")
    lowered = text.lower()
    if "invalid login" in lowered or "invalid_grant" in lowered:
        return "That email and password don't match. Check them, or create an account first."
    if "already registered" in lowered or "already exists" in lowered:
        return "There's already an account with that email. Sign in instead."
    if "not confirmed" in lowered:
        return "Please confirm your email first (check your inbox), then sign in."
    if "rate limit" in lowered or response.status_code == 429:
        return "Too many tries in a short time. Wait a minute and try again."
    return text or f"The accounts server returned an error ({response.status_code})."


def _session(data):
    """Keep just what we need from Supabase's sign-in answer."""
    return {"access_token": data["access_token"], "refresh_token": data["refresh_token"],
            "email": data["user"]["email"]}


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def check_new_account(email, password, password_again):
    """Return a problem with the sign-up form as a sentence, or None if it looks fine."""
    if "@" not in email or "." not in email.split("@")[-1]:
        return "Please enter a real email address."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Use a password with at least {MIN_PASSWORD_LENGTH} characters."
    if password != password_again:
        return "The two passwords don't match."
    return None


def sign_up(email, password):
    """
    Create an account. Returns a session (signed in straight away), or None when Supabase
    is set to make people confirm their email first.
    """
    data = _call("POST", "/auth/v1/signup", json={"email": email.strip().lower(), "password": password})
    return _session(data) if data and data.get("access_token") else None


def sign_in(email, password):
    """Check an email + password. Returns a session, or raises AccountError."""
    return _session(_call("POST", "/auth/v1/token", params={"grant_type": "password"},
                          json={"email": email.strip().lower(), "password": password}))


def restore(refresh_token):
    """
    Sign someone back in from the refresh token saved when they ticked "Stay signed in".
    Returns a new session (with a new refresh token: the old one stops working), or raises AccountError.
    """
    return _session(_call("POST", "/auth/v1/token", params={"grant_type": "refresh_token"},
                          json={"refresh_token": refresh_token}))


def sign_out(session):
    """End this sign-in on Supabase, so a saved "stay signed in" token can't be used again."""
    try:
        _call("POST", "/auth/v1/logout", params={"scope": "local"}, token=session["access_token"])
    except AccountError:
        pass  # signing out locally still works if Supabase can't be reached


def _refresh(session):
    """A session's pass expires after an hour; swap the refresh token for a new one (in place)."""
    session.update(_session(_call("POST", "/auth/v1/token", params={"grant_type": "refresh_token"},
                                  json={"refresh_token": session["refresh_token"]})))


def _as_user(session, method, path, **kwargs):
    """Make a call as the signed-in person, renewing their pass once if it has expired."""
    try:
        return _call(method, path, token=session["access_token"], **kwargs)
    except AccountError as error:
        if error.status != 401:
            raise
        _refresh(session)
        return _call(method, path, token=session["access_token"], **kwargs)


# ---------------------------------------------------------------------------
# Drill results (each person can only see and add their own, enforced by Supabase)
# ---------------------------------------------------------------------------

def save_result(session, date, result):
    """Save one answered question for the signed-in person. `result` is a dict from drill.py."""
    row = {"date": date, "question_type": result["type"], "correct": int(result["correct"]),
           "seconds": result["seconds"], "question": result["question"],
           "your_answer": result["your_answer"], "right_answer": result["answer"]}
    _as_user(session, "POST", "/rest/v1/drill_results", json=row,
             extra_headers={"Prefer": "return=minimal"})


def load_results(session, since_date=None):
    """The signed-in person's drill rows, oldest first (same shape as db.load_drill_results)."""
    params = {"select": ",".join(COLUMNS), "order": "id.asc"}
    if since_date:
        params["date"] = f"gte.{since_date}"
    return _as_user(session, "GET", "/rest/v1/drill_results", params=params) or []
