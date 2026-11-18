"""Honesty behaviour of the profile builder, and the content checker."""

import importlib.util
import json
from pathlib import Path

from app import ai

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_content.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_content", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fallback_profile_never_invents_skills(logged_in, monkeypatch):
    """With the AI unavailable, the draft must not contain skills the user did not provide."""
    monkeypatch.setattr(
        ai,
        "ask",
        lambda *a, **k: (
            {"summary": "x", "break_statement": "", "skills": []},
            "fallback",
        ),
    )
    html = logged_in.post(
        "/profile", data={"text": "Ran a bakery for four years."}
    ).text
    assert "AI is unavailable" in html
    assert "Communication" not in html


def test_hand_typed_skills_are_saved(logged_in):
    logged_in.post(
        "/profile/save",
        data={
            "summary": "Baker",
            "brk": "Career break",
            "extra": "Budgeting, Team leadership",
        },
    )
    html = logged_in.get("/profile").text
    assert "Budgeting" in html and "Team leadership" in html


def test_demo_works_without_an_account(client):
    r = client.post("/demo")
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert "sid" in r.cookies
    home = client.get("/").text
    assert "Priya" in client.get("/profile").text or "Signed in as demo-" in home


def test_register_login_logout_cycle(client):
    import uuid

    email = f"cycle-{uuid.uuid4().hex[:8]}@example.com"
    assert (
        client.post(
            "/register",
            data={"email": email, "password": "longpass1", "confirm": "longpass1"},
        ).status_code
        == 303
    )
    client.post("/logout")
    bad = client.post("/login", data={"email": email, "password": "wrongpass"})
    assert "wrong" in bad.text
    good = client.post("/login", data={"email": email, "password": "longpass1"})
    assert good.status_code == 303


def test_checker_fails_on_unverified_placeholders(tmp_path):
    checker = _load_checker()
    (tmp_path / "finance.json").write_text(
        json.dumps(
            [
                {
                    "title": "EPF",
                    "answer": "TODO",
                    "source_url": "TODO",
                    "verified": False,
                }
            ]
        )
    )
    problems = checker.check_all(tmp_path)
    assert any("verified is false" in p for p in problems)
    assert any("https://" in p for p in problems)
    assert checker.main(["x", str(tmp_path)]) == 1


def test_checker_fails_when_source_url_missing(tmp_path):
    checker = _load_checker()
    (tmp_path / "jobs.json").write_text(
        json.dumps([{"title": "Role", "verified": True}])
    )
    problems = checker.check_all(tmp_path)
    assert any("source_url" in p for p in problems)


def test_checker_passes_when_verified_with_https_source(tmp_path):
    checker = _load_checker()
    (tmp_path / "finance.json").write_text(
        json.dumps(
            [
                {
                    "title": "EPF",
                    "answer": "Checked",
                    "source_url": "https://www.epfindia.gov.in/",
                    "verified": True,
                }
            ]
        )
    )
    assert checker.check_all(tmp_path) == []
    assert checker.main(["x", str(tmp_path)]) == 0


def test_checker_passes_on_repo_data_only_when_verified():
    """The shipped data is still placeholder content, so the checker must fail on it."""
    checker = _load_checker()
    assert checker.main(["x", str(SCRIPT.parent.parent / "data")]) == 1
