"""A career break has many causes: stages beyond pregnancy, welcoming wording, and the photo credit."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app import ai, community, db, main

NEW_STAGES = {
    "childcare": "I'm raising or educating my children",
    "caregiving": "I'm caring for a parent or family member",
    "health": "I'm on a health or recovery break",
    "relocating": "I'm relocating or studying",
    "earlycareer": "I'm early in my career, starting again",
}


def _signup(stage):
    c = TestClient(main.app, follow_redirects=False)
    email = f"inc-{uuid.uuid4().hex[:8]}@example.com"
    c.post(
        "/register",
        data={
            "email": email,
            "password": "longpass1",
            "confirm": "longpass1",
            "stage": stage,
        },
    )
    return c, email


def _stage_of(email):
    return db.q("select stage from u where email=?", (email,))[0]["stage"]


# ---- stages ----------------------------------------------------------------------------------


def test_every_stage_key_fits_the_form_field_limit():
    assert all(
        len(k) <= 20 for k in main.STAGES
    )  # the stage field accepts at most 20 characters


def test_pregnancy_stages_are_still_there_alongside_the_new_ones():
    assert {"expecting", "newborn", "planning"} <= set(main.STAGES)
    assert set(NEW_STAGES) <= set(main.STAGES)


def test_register_dropdown_offers_every_reason_for_a_break(client):
    html = client.get("/register").text
    for label in [
        "I'm expecting",
        "I have a newborn",
        "I'm planning my return",
        *NEW_STAGES.values(),
    ]:
        assert label.replace("'", "&#39;") in html, label


@pytest.mark.parametrize("stage", list(NEW_STAGES))
def test_each_new_stage_can_be_chosen_at_sign_up(stage):
    _, email = _signup(stage)
    assert _stage_of(email) == stage


def test_unknown_stage_still_falls_back_to_planning():
    _, email = _signup("not-a-stage")
    assert _stage_of(email) == "planning"


def test_stage_can_be_changed_to_a_new_one_from_the_home_page(logged_in):
    sid = logged_in.cookies.get("sid")
    logged_in.post("/stage", data={"stage": "caregiving", "goal": "A job"})
    assert db.q("select stage from u where sid=?", (sid,))[0]["stage"] == "caregiving"
    html = logged_in.get("/").text
    assert 'value="caregiving" selected' in html


# ---- what the stage changes --------------------------------------------------------------------


@pytest.mark.parametrize(
    "stage, circle",
    [
        ("expecting", "expecting"),
        ("newborn", "newborn"),
        ("caregiving", "returning"),
        ("childcare", "returning"),
        ("health", "returning"),
        ("planning", "returning"),
    ],
)
def test_each_stage_gets_a_suggested_circle(stage, circle):
    c, _ = _signup(stage)
    cards = community.circle_cards(c.cookies.get("sid"), stage)
    assert [x["slug"] for x in cards if x["suggested"]] == [circle]


def test_the_study_plan_prompt_uses_the_full_stage_label(logged_in, monkeypatch):
    seen = {}

    def fake(prompt, fallback, **kw):
        seen["p"] = prompt
        return fallback, "fallback"

    monkeypatch.setattr(ai, "ask", fake)
    logged_in.post("/stage", data={"stage": "caregiving", "goal": "A job"})
    logged_in.post("/upskilling/plan")
    assert "caring for a parent or family member" in seen["p"]


def test_the_chat_profile_tool_reports_the_stage_label():
    u = {"prof": {"summary": "s"}, "goal": "A job", "stage": "health", "sid": "x"}
    out = main._ask_tools(u)["get_profile"]()
    assert out["stage"] == "I'm on a health or recovery break"


# ---- wording ------------------------------------------------------------------------------------


def test_register_page_welcomes_every_kind_of_break_and_has_no_stale_text(client):
    html = client.get("/register").text
    assert (
        "caring for family" in html
        and "children's education" in html
        and "health" in html
    )
    assert "SQLite" not in html and "local" not in html.lower().split("<main>")[1]


def test_login_page_has_no_stale_local_database_text(client):
    html = client.get("/login").text
    assert "SQLite" not in html and "Welcome back" in html


def test_home_page_for_visitors_is_not_only_about_pregnancy(client):
    html = client.get("/").text
    assert "caring for family" in html and "a profile and a plan" in html


def test_community_welcomes_everyone_coming_back(logged_in):
    html = logged_in.get("/community").text
    assert "welcomes everyone coming back from a break, for any reason" in html
    assert "after any kind of break" in html


def test_a_sample_story_is_about_caring_for_a_parent(logged_in):
    assert "care for my mother" in logged_in.get("/community").text


def test_roadmap_networking_step_is_not_pregnancy_specific(logged_in):
    assert "whatever the reason for your break" in logged_in.get("/").text


# ---- photo credit ----------------------------------------------------------------------------------


def test_credit_appears_on_the_page_that_uses_the_photo(client):
    html = client.get("/").text
    assert 'src="/static/img/hero-group.jpg"' in html
    assert "Photo: Karola G on Pexels (free licence)." in html


@pytest.mark.parametrize(
    "path", ["/money", "/privacy", "/contact", "/login", "/register"]
)
def test_credit_is_not_shown_on_pages_without_the_photo(client, path):
    assert "Photo:" not in client.get(path).text


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/journal",
        "/profile",
        "/jobs",
        "/community",
        "/upskilling",
        "/interview",
        "/ask",
    ],
)
def test_credit_is_not_shown_on_signed_in_pages(logged_in, path):
    html = logged_in.get(path).text
    assert "hero-group.jpg" not in html  # the photo is not on these pages
    assert "Photo: Karola G" not in html


def test_the_shared_footer_has_no_photo_credit():
    from pathlib import Path

    base = (
        Path(__file__).resolve().parent.parent / "app" / "templates" / "base.html"
    ).read_text()
    assert "Karola" not in base and 'class="credit"' not in base
