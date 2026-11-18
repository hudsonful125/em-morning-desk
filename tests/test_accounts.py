"""Tests for email + password accounts (modules/accounts.py), with a fake Supabase: nothing is sent."""

import pytest

from modules import accounts


class FakeResponse:
    def __init__(self, status, data):
        self.status_code, self._data = status, data
        self.content = b"x" if data is not None else b""

    def json(self):
        return self._data


class FakeSupabase:
    """Pretends to be Supabase: remembers accounts and rows, and checks tokens."""

    def __init__(self):
        self.users, self.rows, self.calls = {}, [], []
        self.valid_tokens = set()

    def login(self, email):
        token = f"token-{email}-{len(self.valid_tokens)}"
        self.valid_tokens.add(token)
        return FakeResponse(200, {"access_token": token, "refresh_token": "r-" + email,
                                  "user": {"email": email}})

    def __call__(self, method, url, json=None, params=None, headers=None, timeout=None):
        self.calls.append((method, url, headers))
        assert headers["apikey"] == "test-key" and timeout
        path = url.replace("https://x.supabase.co", "")
        if path == "/auth/v1/signup":
            if json["email"] in self.users:
                return FakeResponse(422, {"msg": "User already registered"})
            self.users[json["email"]] = json["password"]
            return self.login(json["email"])
        if path == "/auth/v1/token" and params["grant_type"] == "password":
            if self.users.get(json["email"]) != json["password"]:
                return FakeResponse(400, {"error": "invalid_grant", "error_description": "Invalid login credentials"})
            return self.login(json["email"])
        if path == "/auth/v1/token":  # refresh
            return self.login(json["refresh_token"][2:])
        token = headers.get("Authorization", "")[7:]
        if token not in self.valid_tokens:
            return FakeResponse(401, {"message": "JWT expired"})
        email = token.split("-")[1]
        if method == "POST":
            self.rows.append(dict(json, owner=email))
            return FakeResponse(201, None)
        mine = [{k: r[k] for k in accounts.COLUMNS} for r in self.rows if r["owner"] == email]
        if "date" in params:
            mine = [r for r in mine if r["date"] >= params["date"][4:]]
        return FakeResponse(200, mine)


@pytest.fixture
def supabase(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co/")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    fake = FakeSupabase()
    monkeypatch.setattr(accounts.requests, "request", fake)
    return fake


RESULT = {"type": "bps", "correct": True, "seconds": 2.5, "question": "Q?", "your_answer": "5", "answer": 5.0}


def test_not_set_up_without_secrets(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    assert not accounts.is_set_up()


def test_check_new_account():
    assert accounts.check_new_account("me@school.edu", "longenough", "longenough") is None
    assert "real email" in accounts.check_new_account("nope", "longenough", "longenough")
    assert "at least 8" in accounts.check_new_account("me@school.edu", "short", "short")
    assert "don't match" in accounts.check_new_account("me@school.edu", "longenough", "different1")


def test_sign_up_then_sign_in(supabase):
    session = accounts.sign_up(" Maya@School.edu ", "password123")
    assert session["email"] == "maya@school.edu"
    assert accounts.sign_in("maya@school.edu", "password123")["email"] == "maya@school.edu"
    with pytest.raises(accounts.AccountError, match="don't match"):
        accounts.sign_in("maya@school.edu", "wrong-password")
    with pytest.raises(accounts.AccountError, match="already an account"):
        accounts.sign_up("maya@school.edu", "password123")


def test_scores_are_per_account(supabase):
    maya = accounts.sign_up("maya@school.edu", "password123")
    sam = accounts.sign_up("sam@school.edu", "password123")
    accounts.save_result(maya, "2026-11-17", RESULT)
    accounts.save_result(maya, "2026-11-18", dict(RESULT, correct=False))
    assert [r["correct"] for r in accounts.load_results(maya)] == [1, 0]
    assert len(accounts.load_results(maya, since_date="2026-11-18")) == 1
    assert accounts.load_results(sam) == []


def test_expired_pass_is_renewed(supabase):
    session = accounts.sign_up("maya@school.edu", "password123")
    supabase.valid_tokens.clear()  # pretend an hour went by
    accounts.save_result(session, "2026-11-18", RESULT)
    assert len(supabase.rows) == 1 and session["access_token"] in supabase.valid_tokens
