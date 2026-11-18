"""Step 3: stage and goal at sign-up, and skill tags on journal entries."""

import uuid

from app import ai, db
from app.schemas import JournalLine


def _register(client, stage="planning", goal="A job"):
    email = f"onb-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/register",
        data={
            "email": email,
            "password": "longpass1",
            "confirm": "longpass1",
            "stage": stage,
            "goal": goal,
        },
    )
    return email


def _stage_of(email):
    return db.q("select stage, goal from u where email=?", (email,))[0]


def test_register_page_offers_stage_and_goal(client):
    html = client.get("/register").text
    assert 'name="stage"' in html and "expecting" in html and "I have a newborn" in html
    assert 'name="goal"' in html and "Freelance work" in html


def test_sign_up_saves_chosen_stage_and_goal(client):
    email = _register(client, stage="expecting", goal="Freelance work")
    assert _stage_of(email) == {"stage": "expecting", "goal": "Freelance work"}


def test_invalid_stage_and_goal_fall_back_to_defaults(client):
    email = _register(client, stage="returned-somehow", goal="Win the lottery")
    assert _stage_of(email) == {"stage": "planning", "goal": "A job"}


def test_home_shows_cards_for_chosen_stage(logged_in):
    # Fresh accounts default to "planning", whose first card is Profile.
    html = logged_in.get("/").text
    assert 'href="/profile"' in html


def test_journal_entry_stores_and_shows_skill_tags(logged_in, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        ai,
        "ask",
        lambda *a, **k: (
            {
                "line": "Managed supplier payments for a bakery.",
                "skills": ["Supplier management", "Budgeting"],
            },
            "ai",
        ),
    )
    logged_in.post("/journal", data={"raw": "I paid the suppliers every week"})
    html = logged_in.get("/journal").text
    assert "Skills: Supplier management, Budgeting" in html


def test_journal_fallback_has_no_invented_tags(logged_in, monkeypatch):
    monkeypatch.setattr(
        ai, "ask", lambda *a, **k: ({"line": "raw text", "skills": []}, "fallback")
    )
    logged_in.post("/journal", data={"raw": "Took a short course"})
    assert "Skills:" not in logged_in.get("/journal").text


def test_journal_line_schema_accepts_tags_and_defaults_to_none():
    assert JournalLine.model_validate({"line": "l", "skills": ["a"]}).skills == ["a"]
    assert JournalLine.model_validate({"line": "l"}).skills == []
