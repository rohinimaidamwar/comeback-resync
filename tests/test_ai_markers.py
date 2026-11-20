"""AI is labelled wherever it produced what the user sees, and never when it did not."""

import json

from app import ai, db

PLAN = {
    "topics": ["Data analysis"],
    "weeks": [
        {"title": "Week 1: Data analysis", "tasks": ["Practise one chart a day."]}
    ],
}


def _fit():
    return {
        "score": 70,
        "why": "Good overlap.",
        "talking_points": ["Explain your project."],
    }


# ---- every AI feature is labelled when AI wrote the result -----------------------------------


def test_journal_page_explains_the_ai_rewrite(logged_in):
    html = logged_in.get("/journal").text
    assert 'class="ai-pill"' in html and "Claude rewrites each entry" in html
    assert "Your own words are always kept" in html


def test_profile_suggestions_are_labelled_only_when_ai_wrote_them(
    logged_in, monkeypatch
):
    text = "I ran a small bakery handling orders staff rota and supplier payments."
    ai_reply = {
        "summary": "Baker",
        "break_statement": "",
        "skills": [
            {
                "name": "Operations",
                "evidence": "handling orders staff rota and supplier payments",
            }
        ],
    }
    monkeypatch.setattr(ai, "ask", lambda *a, **k: (ai_reply, "ai"))
    assert "AI suggestion" in logged_in.post("/profile", data={"text": text}).text
    monkeypatch.setattr(
        ai,
        "ask",
        lambda *a, **k: (
            {"summary": "x", "break_statement": "", "skills": []},
            "fallback",
        ),
    )
    fallback_page = logged_in.post("/profile", data={"text": text}).text
    assert "AI suggestion" not in fallback_page and "AI is unavailable" in fallback_page


def test_job_scores_are_labelled_only_when_ai_wrote_them(logged_in, monkeypatch):
    ai_scores = {"matches": [{"id": 101, "score": 80, "why": "Strong overlap."}]}
    monkeypatch.setattr(ai, "ask", lambda *a, **k: (ai_scores, "ai"))
    html = logged_in.post("/jobs/match", data={"ids": ["101"]}).text
    assert "AI match" in html and "estimates written by AI" in html
    monkeypatch.setattr(
        ai,
        "ask",
        lambda *a, **k: (
            {"matches": [{"id": 101, "score": 40, "why": "x"}]},
            "fallback",
        ),
    )
    html = logged_in.post("/jobs/match", data={"ids": ["101"]}).text
    assert 'class="ai-pill"' not in html and "AI matching is unavailable" in html


def test_study_plan_is_labelled_only_when_ai_wrote_it(logged_in, monkeypatch):
    monkeypatch.setattr(ai, "ask", lambda *a, **k: (PLAN, "ai"))
    logged_in.post("/upskilling/plan")
    assert "AI-generated plan" in logged_in.get("/upskilling").text
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.undo()
    monkeypatch.setattr(ai, "ask", lambda *a, **k: (PLAN, "fallback"))
    logged_in.post("/upskilling/plan")
    assert "AI-generated plan" not in logged_in.get("/upskilling").text


def test_the_ai_flag_is_stored_with_the_plan(logged_in, monkeypatch):
    sid = logged_in.cookies.get("sid")
    monkeypatch.setattr(ai, "ask", lambda *a, **k: (PLAN, "ai"))
    logged_in.post("/upskilling/plan")
    assert (
        json.loads(db.q("select plan from u where sid=?", (sid,))[0]["plan"])["ai"]
        is True
    )
    monkeypatch.setattr(ai, "ask", lambda *a, **k: (PLAN, "fallback"))
    logged_in.post("/upskilling/plan")
    assert (
        json.loads(db.q("select plan from u where sid=?", (sid,))[0]["plan"])["ai"]
        is False
    )


def test_plans_saved_before_the_flag_existed_are_not_labelled(logged_in):
    sid = logged_in.cookies.get("sid")
    old = {
        "topics": ["x"],
        "weeks": [{"title": "Week 1", "tasks": [{"text": "t", "done": False}]}],
    }
    db.q("update u set plan=? where sid=?", (json.dumps(old), sid))
    assert "AI-generated plan" not in logged_in.get("/upskilling").text


def test_talking_points_are_labelled(logged_in, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(ai, "ask", lambda *a, **k: (_fit(), "ai"))
    html = logged_in.post("/interview/paste", data={"jd": "A role"}).text
    assert "70% fit" in html and "AI-generated" in html


# ---- explanations around the app ---------------------------------------------------------------


def test_visitors_see_how_the_app_uses_ai(client):
    html = client.get("/").text
    assert "How hercomeback uses AI" in html
    for feature in [
        "Journal:",
        "Profile:",
        "Jobs:",
        "Learn:",
        "Interview prep:",
        "Comeback Buddy:",
    ]:
        assert feature in html
    assert "Powered by Claude, from Anthropic" in html
    assert "you approve before anything is saved" in html


def test_members_see_what_the_ai_label_means(logged_in):
    assert (
        "marks where AI helps. You review everything before it is saved."
        in logged_in.get("/").text
    )


def test_the_label_always_has_visible_text_not_only_an_icon(logged_in):
    html = logged_in.get("/journal").text
    pill = html.split('class="ai-pill"')[1].split("</span>")[0]
    assert 'aria-hidden="true"' in pill and pill.rstrip().endswith("AI")


def test_pages_without_ai_carry_no_ai_label(logged_in):
    for path in ["/money", "/community", "/privacy"]:
        assert 'class="ai-pill"' not in logged_in.get(path).text, path


# ---- lines from the pitch ----------------------------------------------------------------------------


def test_login_and_register_use_the_pitch_lines(client):
    assert (
        "Talent doesn't expire just because life happened." in client.get("/login").text
    )
    assert (
        "You don't disappear while you're on a break." in client.get("/register").text
    )


def test_unverified_statistics_are_not_shown_in_the_app(client):
    for path in ["/", "/login", "/register", "/money", "/privacy"]:
        html = client.get(path).text
        assert "73%" not in html and "7 million" not in html, path


def test_money_is_not_in_the_menu_on_login_and_register(client):
    for path in ["/login", "/register"]:
        html = client.get(path).text
        assert 'href="/money"' not in html, path
        assert (
            'href="/contact"' in html
            and 'href="/login"' in html
            and 'href="/register"' in html
        )


def test_money_stays_in_the_menu_on_other_public_pages(client):
    for path in ["/", "/contact", "/privacy", "/money"]:
        assert '<a href="/money">Money</a>' in client.get(path).text, path
