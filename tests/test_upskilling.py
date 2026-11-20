"""Upskilling: study plan from the goal and profile, tick-off tasks, and verified course providers only."""

import json
from pathlib import Path

from app import ai, upskill

COURSES = Path(__file__).resolve().parent.parent / "data" / "courses.json"


def _plan_from(client):
    html = client.get("/upskilling").text
    return html


def test_upskilling_needs_sign_in(client):
    assert client.get("/upskilling").headers["location"] == "/login"


def test_no_profile_shows_a_notice(logged_in):
    html = logged_in.get("/upskilling").text
    assert "Save your profile first" in html


def test_fallback_plan_is_created_without_api_key(logged_in, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    html = logged_in.post("/upskilling/plan").text
    assert "Week 1:" in html and "starter plan" in html
    assert "Update my plan" in html


def test_ai_plan_is_saved_and_shown(logged_in, monkeypatch):
    plan = {
        "topics": ["Data analysis"],
        "weeks": [
            {"title": "Week 1: Data analysis", "tasks": ["Practise one chart a day."]}
        ],
    }
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(ai, "ask", lambda *a, **k: (plan, "ai"))
    html = logged_in.post("/upskilling/plan").text
    assert "Practise one chart a day." in html
    assert "starter plan" not in html


def test_prompt_forbids_naming_courses_or_links():
    text = upskill.prompt("A job", "planning", ["Excel"])
    assert "Do not name courses" in text and "links" in text


def test_tasks_can_be_ticked_and_unticked(logged_in, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    logged_in.post("/upskilling/plan")
    logged_in.post("/upskilling/toggle", data={"week": "0", "task": "0"})
    assert 'class="done"' in logged_in.get("/upskilling").text
    logged_in.post("/upskilling/toggle", data={"week": "0", "task": "0"})
    assert 'class="done"' not in logged_in.get("/upskilling").text


def test_stale_toggle_is_ignored(logged_in, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    logged_in.post("/upskilling/plan")
    r = logged_in.post("/upskilling/toggle", data={"week": "99", "task": "99"})
    assert r.status_code == 303


def test_plan_is_trimmed_to_safe_sizes():
    raw = {
        "topics": ["t"] * 9,
        "weeks": [{"title": "w", "tasks": ["x"] * 9} for _ in range(9)],
    }
    cleaned = upskill.clean(raw)
    assert len(cleaned["topics"]) == 4 and len(cleaned["weeks"]) == 4
    assert len(cleaned["weeks"][0]["tasks"]) == 4
    assert cleaned["weeks"][0]["tasks"][0] == {"text": "x", "done": False}


def test_only_verified_providers_are_shown():
    entries = json.loads(COURSES.read_text(encoding="utf-8"))
    shown = upskill.providers()
    assert len(shown) == len([e for e in entries if e.get("verified")])
    for p in shown:
        assert p["url"].startswith("https://")


def test_provider_links_point_at_homepages_in_the_page(logged_in, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    html = logged_in.get("/upskilling").text
    for name in ["NPTEL", "SWAYAM", "Coursera", "edX"]:
        assert name in html
    assert "https://nptel.ac.in/" in html


def test_learn_is_in_navigation_and_roadmap_step_two(logged_in):
    html = logged_in.get("/journal").text
    assert 'href="/upskilling"' in html
    home = logged_in.get("/").text
    assert 'class="road-link" href="/upskilling"' in home
