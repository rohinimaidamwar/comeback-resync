"""Interview prep: tabs, practice preferences, peer grid, request flow, and talk points."""

import json
import uuid

from app import ai, db, practice


def _member(client, **prefs):
    """Another user who sets practice preferences, so the pool has a real member."""
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
    client.post("/interview/practice", data=prefs)
    client.post("/logout")
    return email


def _html(client, tab=None):
    return client.get("/interview" + (f"?tab={tab}" if tab else "")).text


# ---- tabs ----------------------------------------------------------------------------------


def test_three_tabs_with_peer_practice_active_by_default(logged_in):
    html = _html(logged_in)
    for label in ["Peer practice", "JD talking points", "AI mock interview"]:
        assert label in html
    assert (
        'id="tab-peer" href="/interview?tab=peer" aria-controls="panel-peer" aria-selected="true"'
        in html
    )
    assert 'id="panel-talk" role="tabpanel" aria-labelledby="tab-talk" hidden' in html
    assert 'id="panel-peer" role="tabpanel" aria-labelledby="tab-peer">' in html


def test_tab_query_selects_the_panel(logged_in):
    html = _html(logged_in, "talk")
    assert 'aria-controls="panel-talk" aria-selected="true"' in html
    assert 'id="panel-peer" role="tabpanel" aria-labelledby="tab-peer" hidden' in html


def test_unknown_tab_falls_back_to_peer_practice(logged_in):
    assert 'aria-controls="panel-peer" aria-selected="true"' in _html(
        logged_in, "nonsense"
    )


def test_peer_tab_shows_how_many_peers(logged_in):
    assert "6 peers" in _html(logged_in)  # six labelled sample profiles


def test_ai_tab_is_only_a_coming_soon_card(logged_in):
    html = _html(logged_in, "ai")
    assert "AI mock interview" in html and "Coming soon" in html
    assert 'action="/interview/mock"' not in html


def test_page_has_one_external_script_and_no_inline_script_or_handlers(logged_in):
    html = _html(logged_in)
    assert html.count("<script") == 1
    assert '<script src="/static/interview.js" defer></script>' in html
    assert "onclick=" not in html and "style=" not in html  # blocked by the CSP anyway


def test_interview_script_is_served(client):
    r = client.get("/static/interview.js")
    assert r.status_code == 200 and "request-dialog" in r.text


# ---- practice preferences --------------------------------------------------------------------


def test_two_consent_toggles_and_privacy_note(logged_in):
    html = _html(logged_in)
    assert 'name="want_interview"' in html and "I want to be interviewed" in html
    assert 'name="can_interview"' in html and "I can take interviews" in html
    assert "never your email" in html


def test_saving_either_intent_shows_active_status(logged_in):
    assert "Active in practice pool" not in _html(logged_in)
    logged_in.post(
        "/interview/practice",
        data={"role": "Data analyst", "years": "3", "want_interview": "yes"},
    )
    html = _html(logged_in)
    assert "Active in practice pool" in html
    assert 'name="want_interview" value="yes" checked' in html
    assert 'name="can_interview" value="yes" checked' not in html


def test_turning_both_off_leaves_the_pool(logged_in):
    logged_in.post(
        "/interview/practice",
        data={"role": "Data analyst", "years": "3", "can_interview": "yes"},
    )
    logged_in.post("/interview/practice", data={"role": "Data analyst", "years": "3"})
    assert "Active in practice pool" not in _html(logged_in)


def test_records_from_before_the_split_count_as_both_intents():
    assert practice.flags({"opt_in": True}) == (True, True)
    assert practice.flags({}) == (False, False)
    assert practice.flags({"want_interview": True, "can_interview": False}) == (
        True,
        False,
    )


def test_years_must_be_in_range(logged_in):
    r = logged_in.post("/interview/practice", data={"role": "x", "years": "99"})
    assert r.status_code == 422


# ---- peer grid ---------------------------------------------------------------------------------


def test_sample_peers_are_labelled_and_show_intent_tags(logged_in):
    html = _html(logged_in)
    assert html.count("Sample profile") == 6
    for tag in ["Open to swap", "Can interview you", "Looking to practice"]:
        assert tag in html
    assert 'data-can="1"' in html and 'data-want="1"' in html


def test_filter_bar_is_hidden_until_javascript_shows_it(logged_in):
    html = _html(logged_in)
    assert 'role="group" aria-label="Filter peers" hidden' in html
    for label in [
        "All peers",
        "Best matches for you",
        "Can interview me",
        "Wants to practice",
    ]:
        assert label in html


def test_top_match_needs_a_similar_role_and_experience(logged_in):
    assert "Top match" not in _html(logged_in)  # no role saved yet
    logged_in.post(
        "/interview/practice",
        data={"role": "Product manager", "years": "6", "want_interview": "yes"},
    )
    html = _html(logged_in)
    assert html.count("Top match") >= 1
    meera = html.split("Meera")[1].split("</article>")[0]
    assert "Top match" in meera


def test_matching_prefers_same_role_and_similar_years():
    me = {"role": "Product manager", "years": 6}
    assert practice._score(
        me, {"role": "Product manager", "years": 6}
    ) > practice._score(me, {"role": "Data analyst", "years": 2})


def test_real_members_appear_without_email_and_never_yourself(client):
    email = _member(client, role="Data analyst", years="5", can_interview="yes")
    client.post("/demo")
    html = _html(client)
    assert "Tara" in html and "Member" in html
    assert email not in html


def test_you_do_not_appear_in_your_own_pool(client):
    email = f"zelda-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/register",
        data={
            "email": email,
            "password": "longpass1",
            "confirm": "longpass1",
            "name": "Zelda",
        },
    )
    client.post(
        "/interview/practice",
        data={"role": "Archivist", "years": "4", "can_interview": "yes"},
    )
    mine = client.cookies.get("sid")
    rec = practice.record(
        db.q("select practice from u where sid=?", (mine,))[0]["practice"]
    )
    assert "Zelda (Archivist)" not in {p["key"] for p in practice.pool(mine, rec)}
    # ...but another signed-in user does see her.
    assert "Zelda (Archivist)" in {p["key"] for p in practice.pool("someone-else", {})}


# ---- request flow --------------------------------------------------------------------------------


def test_request_dialog_offers_the_three_session_types(logged_in):
    html = _html(logged_in)
    assert 'id="request-dialog"' in html
    for label in [
        "30-min swap (both)",
        "Ask them to interview me",
        "Offer to interview them",
    ]:
        assert label in html


def test_request_is_saved_with_its_session_type_and_card_shows_requested(logged_in):
    logged_in.post(
        "/interview/request",
        data={"partner": "Meera (Product manager)", "session": "interview_me"},
    )
    html = _html(logged_in)
    assert "Requested ✓" in html
    assert "Your pending requests (1)" in html
    assert "Meera (Product manager) · Ask them to interview me" in html
    assert "Scheduling is coming soon" in html


def test_the_same_person_cannot_be_requested_twice(logged_in):
    for _ in range(3):
        logged_in.post(
            "/interview/request",
            data={"partner": "Meera (Product manager)", "session": "swap"},
        )
    assert "Your pending requests (1)" in _html(logged_in)


def test_unknown_partners_and_session_types_are_handled(logged_in):
    logged_in.post(
        "/interview/request", data={"partner": "Nobody (Wizard)", "session": "swap"}
    )
    assert "pending requests" not in _html(logged_in)
    logged_in.post(
        "/interview/request",
        data={"partner": "Asha (Customer success lead)", "session": "hack"},
    )
    assert "Asha (Customer success lead) · 30-min swap (both)" in _html(logged_in)


def test_a_request_can_be_removed(logged_in):
    logged_in.post(
        "/interview/request",
        data={"partner": "Meera (Product manager)", "session": "swap"},
    )
    logged_in.post(
        "/interview/request/remove", data={"partner": "Meera (Product manager)"}
    )
    html = _html(logged_in)
    assert "pending requests" not in html and "Requested ✓" not in html


def test_old_text_only_requests_still_display():
    rec = {"requests": ["Meera (Product manager)"]}
    assert practice.requests(rec)[0]["type_label"] == "30-min swap (both)"


def test_requests_belong_to_the_signed_in_user(client):
    other = _member(client)  # a second account exists
    client.post("/demo")
    mine = client.cookies.get("sid")
    client.post(
        "/interview/request",
        data={"partner": "Meera (Product manager)", "session": "swap"},
    )
    mine_rec = practice.record(
        db.q("select practice from u where sid=?", (mine,))[0]["practice"]
    )
    other_rec = practice.record(
        db.q("select practice from u where email=?", (other,))[0]["practice"]
    )
    assert [r["key"] for r in practice.requests(mine_rec)] == [
        "Meera (Product manager)"
    ]
    assert practice.requests(other_rec) == []


# ---- talking points -------------------------------------------------------------------------------


def test_jobs_page_no_longer_has_the_talk_points_box(logged_in):
    html = logged_in.get("/jobs").text
    assert 'action="/jobs/paste"' not in html and "Check my fit" not in html


def test_talk_points_form_lives_in_its_own_tab(logged_in):
    html = _html(logged_in, "talk")
    assert 'action="/interview/paste"' in html and "Get talking points" in html


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
    assert (
        'aria-controls="panel-talk" aria-selected="true"' in html
    )  # stays on the talk tab


def test_talk_points_fall_back_with_a_notice(logged_in, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    html = logged_in.post("/interview/paste", data={"jd": "Any role"}).text
    assert "AI scoring is unavailable" in html and "% fit" not in html


# ---- roadmap and navigation ------------------------------------------------------------------------


def test_roadmap_steps_open_interview_and_jobs(logged_in):
    html = logged_in.get("/").text
    assert (
        'class="road-link" href="/interview"' in html
        and 'class="road-link" href="/jobs"' in html
    )


def test_my_site_is_not_in_the_navigation(logged_in):
    html = logged_in.get("/journal").text
    assert 'href="/site"' not in html and 'href="/interview"' in html


def test_practice_record_round_trips_as_json(logged_in):
    logged_in.post(
        "/interview/practice",
        data={"role": "UX researcher", "years": "5", "can_interview": "yes"},
    )
    sid = logged_in.cookies.get("sid")
    rec = json.loads(db.q("select practice from u where sid=?", (sid,))[0]["practice"])
    assert (
        rec["role"] == "UX researcher"
        and rec["can_interview"] is True
        and rec["want_interview"] is False
    )
    assert "opt_in" not in rec
