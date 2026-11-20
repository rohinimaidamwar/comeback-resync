"""Community: circles to join and leave, member-only boards, privacy rules, and sample stories."""

import re
import uuid

from fastapi.testclient import TestClient

from app import community, db, main


def _user(name=""):
    c = TestClient(main.app, follow_redirects=False)
    email = f"comm-{uuid.uuid4().hex[:8]}@example.com"
    c.post(
        "/register",
        data={
            "email": email,
            "password": "longpass1",
            "confirm": "longpass1",
            "name": name,
        },
    )
    return c, email


def _count(slug):
    return community.counts().get(slug, 0)


def _post(c, slug, body):
    return c.post(f"/community/{slug}/post", data={"body": body})


def _location(r):
    return r.headers["location"]


# ---- access --------------------------------------------------------------------------------


def test_community_needs_sign_in():
    anon = TestClient(main.app, follow_redirects=False)
    assert anon.get("/community").headers["location"] == "/login"
    assert anon.get("/community/expecting").headers["location"] == "/login"
    assert (
        anon.post("/community/join", data={"circle": "expecting"}).headers["location"]
        == "/login"
    )


def test_page_lists_the_three_circles_with_join_buttons(logged_in):
    html = logged_in.get("/community").text
    for name in ["Expecting", "Newborn phase", "Returning soon"]:
        assert name in html
    assert html.count("Join circle") == 3


# ---- join and leave ------------------------------------------------------------------------


def test_joining_counts_the_member_and_unlocks_the_board(logged_in):
    before = _count("expecting")
    r = logged_in.post("/community/join", data={"circle": "expecting"})
    assert _location(r) == "/community?msg=joined"
    assert _count("expecting") == before + 1
    html = logged_in.get("/community?msg=joined").text
    assert "You joined the circle." in html
    assert 'href="/community/expecting"' in html and "Leave" in html


def test_joining_twice_does_not_double_count(logged_in):
    before = _count("newborn")
    for _ in range(3):
        logged_in.post("/community/join", data={"circle": "newborn"})
    assert _count("newborn") == before + 1


def test_unknown_circles_are_ignored(logged_in):
    r = logged_in.post("/community/join", data={"circle": "hackers"})
    assert _location(r) == "/community"
    assert (
        db.q("select count(*) n from memberships where circle='hackers'")[0]["n"] == 0
    )


def test_leaving_removes_membership_and_locks_the_board(logged_in):
    logged_in.post("/community/join", data={"circle": "returning"})
    before = _count("returning")
    r = logged_in.post("/community/leave", data={"circle": "returning"})
    assert _location(r) == "/community?msg=left"
    assert _count("returning") == before - 1
    assert _location(logged_in.get("/community/returning")) == "/community?msg=join"


def test_circle_matching_your_stage_is_suggested(client):
    client.post("/demo")  # the demo account is at the "expecting" stage
    html = client.get("/community").text
    expecting = html.split('class="circle')[1:]
    block = next(b for b in expecting if "Expecting" in b.split("</article>")[0])
    assert "Suggested for you" in block.split("</article>")[0]
    assert html.count("Suggested for you") == 1


def test_a_circle_with_no_members_invites_the_first_one(logged_in):
    db.q("delete from memberships where circle='returning'")
    assert "be the first to join" in logged_in.get("/community").text


# ---- stories -------------------------------------------------------------------------------


def test_five_sample_stories_are_labelled_and_expandable(logged_in):
    html = logged_in.get("/community").text
    assert html.count('<details class="story"') == 5
    assert html.count("Sample story") == 5
    assert "fictional sample stories" in html


def test_story_filter_bar_is_hidden_until_javascript_runs(logged_in):
    html = logged_in.get("/community").text
    assert 'role="group" aria-label="Filter stories" hidden' in html
    for label in ["All stories", "Expecting", "Newborn phase", "Returning soon"]:
        assert label in html
    assert 'data-circle="expecting"' in html and 'data-circle="returning"' in html


def test_sample_file_is_well_formed():
    data = community.samples()
    assert len(data["stories"]) == 5 and all(s["sample"] for s in data["stories"])
    assert all(s["circle"] in community.CIRCLES for s in data["stories"])
    assert all(p["circle"] in community.CIRCLES and p["sample"] for p in data["posts"])
    assert not any("@" in s["body"] for s in data["stories"] + data["posts"])


# ---- boards --------------------------------------------------------------------------------


def test_non_members_cannot_open_a_board(logged_in):
    assert _location(logged_in.get("/community/expecting")) == "/community?msg=join"
    assert (
        "Join this circle to read and post."
        in logged_in.get("/community?msg=join").text
    )


def test_board_shows_only_its_own_labelled_sample_posts(logged_in):
    logged_in.post("/community/join", data={"circle": "expecting"})
    html = logged_in.get("/community/expecting").text
    assert "handover template" in html and "Sample</span>" in html
    assert (
        "Voice notes while the baby naps" not in html
    )  # that sample belongs to another circle


def test_a_member_can_post_and_sees_it_with_their_first_name():
    c, _ = _user("Ananya")
    c.post("/community/join", data={"circle": "newborn"})
    assert (
        _location(_post(c, "newborn", "Finished my first online lesson today"))
        == "/community/newborn?msg=posted"
    )
    html = c.get("/community/newborn").text
    assert "Finished my first online lesson today" in html and "Ananya" in html


def test_posts_by_people_without_a_name_show_as_member():
    c, _ = _user("")
    c.post("/community/join", data={"circle": "newborn"})
    _post(c, "newborn", "A quiet hello")
    assert "A quiet hello" in c.get("/community/newborn").text


def test_non_members_cannot_post():
    c, _ = _user("Zed")
    r = _post(c, "expecting", "Sneaky post")
    assert _location(r) == "/community?msg=join"
    assert db.q("select count(*) n from posts where body='Sneaky post'")[0]["n"] == 0


def test_empty_posts_are_refused(logged_in):
    logged_in.post("/community/join", data={"circle": "expecting"})
    assert (
        _location(_post(logged_in, "expecting", "   "))
        == "/community/expecting?msg=empty"
    )


def test_contact_details_and_links_are_refused(logged_in):
    logged_in.post("/community/join", data={"circle": "expecting"})
    for body, why in [
        ("Mail me at someone@example.com", "contact"),
        ("Call 98765 43210 please", "contact"),
        ("My number is +91 98765-43210", "contact"),
        ("See https://example.com", "links"),
        ("Visit www.example.com", "links"),
    ]:
        assert (
            _location(_post(logged_in, "expecting", body))
            == f"/community/expecting?msg={why}"
        ), body
    html = logged_in.get("/community/expecting").text
    assert "someone@example.com" not in html and "98765" not in html


def test_ordinary_numbers_are_still_allowed(logged_in):
    logged_in.post("/community/join", data={"circle": "expecting"})
    assert (
        _location(
            _post(logged_in, "expecting", "I studied 5 days for 20 minutes in 2026")
        )
        == "/community/expecting?msg=posted"
    )


def test_long_posts_are_trimmed_and_huge_ones_refused(logged_in):
    logged_in.post("/community/join", data={"circle": "expecting"})
    _post(logged_in, "expecting", "x" * 800)
    sid = logged_in.cookies.get("sid")
    assert (
        len(db.q("select body from posts where sid=?", (sid,))[0]["body"])
        == community.MAX_POST
    )
    assert _post(logged_in, "expecting", "y" * 1500).status_code == 422


def test_posting_is_rate_limited(logged_in):
    logged_in.post("/community/join", data={"circle": "expecting"})
    results = [_location(_post(logged_in, "expecting", f"Note {i}")) for i in range(8)]
    assert results[5].endswith("msg=posted") and results[6].endswith("msg=toofast")


def test_posts_are_escaped(logged_in):
    logged_in.post("/community/join", data={"circle": "expecting"})
    _post(logged_in, "expecting", "<script>alert(1)</script> hello")
    html = logged_in.get("/community/expecting").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_only_the_author_can_delete_a_post():
    a, _ = _user("Ana")
    b, _ = _user("Bea")
    for c in (a, b):
        c.post("/community/join", data={"circle": "newborn"})
    _post(a, "newborn", "A note from Ana")
    pid = db.q("select id from posts where body=?", ("A note from Ana",))[0]["id"]
    assert (
        "Delete"
        not in b.get("/community/newborn")
        .text.split("A note from Ana")[1]
        .split("</article>")[0]
    )
    b.post("/community/newborn/post/delete", data={"post_id": str(pid)})
    assert (
        db.q("select count(*) n from posts where id=?", (pid,))[0]["n"] == 1
    )  # Bea cannot delete it
    assert (
        "Delete"
        in a.get("/community/newborn")
        .text.split("A note from Ana")[1]
        .split("</article>")[0]
    )
    a.post("/community/newborn/post/delete", data={"post_id": str(pid)})
    assert db.q("select count(*) n from posts where id=?", (pid,))[0]["n"] == 0


def test_members_see_each_others_posts_but_outsiders_do_not():
    a, _ = _user("Ana")
    b, _ = _user("Bea")
    outsider, _ = _user("Cy")
    for c in (a, b):
        c.post("/community/join", data={"circle": "returning"})
    _post(a, "returning", "A note for the circle")
    assert "A note for the circle" in b.get("/community/returning").text
    assert _location(outsider.get("/community/returning")) == "/community?msg=join"


def test_boards_never_expose_session_tokens(logged_in):
    logged_in.post("/community/join", data={"circle": "expecting"})
    _post(logged_in, "expecting", "Hello")
    sid = logged_in.cookies.get("sid")
    assert sid not in logged_in.get("/community/expecting").text
    assert sid not in logged_in.get("/community").text


def test_membership_and_posts_survive_logout_and_login():
    c, email = _user("Ana")
    c.post("/community/join", data={"circle": "newborn"})
    _post(c, "newborn", "I will still be here")
    c.post("/logout")
    c.post("/login", data={"email": email, "password": "longpass1"})
    html = c.get("/community/newborn").text
    assert (
        "I will still be here" in html and "Delete" in html
    )  # still recognised as the author


def test_deleting_my_data_removes_my_posts_and_membership():
    c, _ = _user("Ana")
    sid = c.cookies.get("sid")
    c.post("/community/join", data={"circle": "newborn"})
    _post(c, "newborn", "Remove me with my data")
    c.post("/delete")
    assert db.q("select count(*) n from posts where sid=?", (sid,))[0]["n"] == 0
    assert db.q("select count(*) n from memberships where sid=?", (sid,))[0]["n"] == 0


# ---- page quality ----------------------------------------------------------------------------


def test_pages_use_one_external_script_and_no_inline_handlers(logged_in):
    logged_in.post("/community/join", data={"circle": "expecting"})
    for path in ["/community", "/community/expecting"]:
        html = logged_in.get(path).text
        assert (
            html.count("<script") == 1
            and '<script src="/static/community.js" defer></script>' in html
        )
        assert "onclick=" not in html and "style=" not in html


def test_post_box_has_a_label_and_a_character_counter(logged_in):
    logged_in.post("/community/join", data={"circle": "expecting"})
    html = logged_in.get("/community/expecting").text
    assert re.search(r'<label for="post-body">', html) and 'maxlength="500"' in html
    assert "500 characters left" in html and 'aria-live="polite"' in html


def test_community_script_is_served(client):
    r = client.get("/static/community.js")
    assert r.status_code == 200 and "innerHTML" not in r.text


def test_problem_with_classifies_posts():
    assert community.problem_with("") == "empty"
    assert community.problem_with("hello there") is None
    assert community.problem_with("me@x.com") == "contact"
    assert community.problem_with("http://x.com") == "links"


def test_privacy_page_mentions_community_posts(client):
    html = client.get("/privacy").text
    assert "community circles you join" in html and "first name only" in html
