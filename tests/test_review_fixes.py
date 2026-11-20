"""Fixes from the judge-style review: demo safety, delete confirmation, page basics, plan size."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import ai, main

APP = Path(__file__).resolve().parent.parent / "app"


def test_demo_refuses_to_overwrite_a_real_member(logged_in):
    logged_in.post("/journal", data={"raw": "Organised a school fundraiser."})
    before = logged_in.get("/journal").text
    r = logged_in.post("/demo", follow_redirects=False)
    assert r.status_code == 303
    after = logged_in.get("/journal").text
    assert "Organised a school fundraiser." in after
    assert "Priya" not in logged_in.get("/").text
    assert before.count("school fundraiser") == after.count("school fundraiser")


def test_demo_reset_button_only_for_demo_accounts(logged_in):
    assert "demo persona" not in logged_in.get("/").text
    visitor = TestClient(main.app)
    visitor.post("/demo")
    assert "Reset demo persona" in visitor.get("/").text


def test_delete_asks_for_confirmation_first(logged_in):
    menu = logged_in.get("/journal").text
    assert 'href="/delete"' in menu
    assert 'action="/delete"' not in menu  # no one-click delete in the menu
    page = logged_in.get("/delete").text
    assert "Delete my data?" in page and 'action="/delete"' in page
    # visiting the confirmation page deletes nothing
    assert logged_in.get("/journal").status_code == 200
    assert "menu at the top right" in logged_in.get("/privacy").text


def test_delete_page_needs_sign_in(client):
    r = client.get("/delete", follow_redirects=False)
    assert r.status_code in (303, 307) and "/login" in r.headers["location"]


def test_demo_footer_does_not_show_the_demo_email(client):
    client.post("/demo")
    html = client.get("/journal").text
    assert "Demo account." in html and "demo.invalid" not in html


def test_pages_have_their_own_titles_and_a_favicon(client):
    for path, word in [
        ("/login", "Log in"),
        ("/register", "Register"),
        ("/contact", "Contact"),
    ]:
        assert f"<title>{word} · hercomeback</title>" in client.get(path).text, path
    html = client.get("/").text
    assert 'rel="icon"' in html and 'name="description"' in html
    assert client.get("/static/favicon.svg").status_code == 200


def test_terracotta_buttons_meet_text_contrast():
    css = (APP / "static" / "style.css").read_text()
    hexv = re.search(r"--terra:(#[0-9A-Fa-f]{6})", css).group(1)
    c = [int(hexv[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    assert 1.05 / (lum + 0.05) >= 4.5


def test_visitor_home_puts_the_demo_before_the_long_text(client):
    html = client.get("/").text
    assert html.index("Try the demo") < html.index("A career break can happen")


def test_study_plan_gets_enough_tokens_for_a_full_reply(logged_in, monkeypatch):
    seen = {}

    def fake_ask(prompt, fallback, **kw):
        seen.update(kw)
        return fallback, "fallback"

    monkeypatch.setattr(ai, "ask", fake_ask)
    logged_in.post("/upskilling/plan")
    assert seen["max_tokens"] >= 2000
