"""Interview prep: talk points moved here, opt-in practice partners, and roadmap links that open the right pages."""

import uuid

from app import ai, practice
from app.schemas import JobFit


def _second_member(client):
    """Another user who opts in, so the pool has a real member to show."""
    email = f"member-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/register",
        data={
            "email": email,
            "password": "longpass1",
            "confirm": "longpass1",
            "name": "Tara",
        },
    )
    client.post(
        "/interview/practice",
        data={"role": "Product manager", "years": "5", "opt_in": "yes"},
    )
    client.post("/logout")


def test_jobs_page_no_longer_has_the_talk_points_box(logged_in):
    html = logged_in.get("/jobs").text
    assert 'action="/jobs/paste"' not in html
    assert "Check my fit" not in html


def test_interview_page_has_the_talk_points_box(logged_in):
    html = logged_in.get("/interview").text
    assert 'action="/interview/paste"' in html
    assert "Get talking points" in html


def test_talk_points_are_shown_when_ai_runs(logged_in, monkeypatch):
    fit = {
        "score": 78,
        "why": "Strong overlap.",
        "talking_points": ["Explain your supplier schedule."],
    }
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(ai, "ask", lambda *a, **k: (fit, "ai"))
    html = logged_in.post("/interview/paste", data={"jd": "Product manager role"}).text
    assert "78% fit" in html and "Explain your supplier schedule." in html


def test_talk_points_fall_back_with_a_notice(logged_in, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    html = logged_in.post("/interview/paste", data={"jd": "Any role"}).text
    assert "AI scoring is unavailable" in html
    assert "% fit" not in html  # never show a score when the AI did not run


def test_opting_in_puts_you_in_the_pool(logged_in):
    logged_in.post(
        "/interview/practice",
        data={"role": "Data analyst", "years": "3", "opt_in": "yes"},
    )
    assert "You are in the practice pool." in logged_in.get("/interview").text


def test_pool_shows_samples_labelled_and_never_emails(client):
    _second_member(client)
    client.post("/demo")  # a signed-in viewer with no practice record
    html = client.get("/interview").text
    assert "Sample profile" in html
    assert "Tara" in html
    assert (
        "@"
        not in html.split("Practice with a partner")[1].split("AI mock interview")[0]
    )


def test_requests_are_saved_and_say_scheduling_is_coming_soon(logged_in):
    logged_in.post("/interview/request", data={"partner": "Meera (Product manager)"})
    html = logged_in.get("/interview").text
    assert "Requests saved: Meera (Product manager)" in html
    assert "Scheduling is coming soon" in html


def test_ai_mock_interview_is_only_a_coming_soon_card(logged_in):
    html = logged_in.get("/interview").text
    assert "AI mock interview" in html and "Coming soon" in html
    assert 'action="/interview/mock"' not in html


def test_matching_prefers_same_role_and_similar_years():
    me = {"role": "Product manager", "years": 6}
    assert practice._score(
        me, {"role": "Product manager", "years": 6}
    ) > practice._score(me, {"role": "Data analyst", "years": 2})


def test_roadmap_steps_open_interview_and_jobs(logged_in):
    html = logged_in.get("/").text
    assert 'class="road-link" href="/interview"' in html
    assert 'class="road-link" href="/jobs"' in html


def test_my_site_is_not_in_the_navigation(logged_in):
    html = logged_in.get("/journal").text
    assert 'href="/site"' not in html
    assert 'href="/interview"' in html


def test_talk_points_schema_still_validates_scores():
    assert JobFit.model_validate({"score": 50, "why": "", "talking_points": []})
