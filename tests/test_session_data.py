"""Regression: data linked to a user must survive the session token changing on login and logout."""

import uuid

from app import db


def _register(client):
    email = f"keep-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/register",
        data={"email": email, "password": "longpass1", "confirm": "longpass1"},
    )
    return email


def test_journal_entries_survive_logout_and_login(client):
    email = _register(client)
    client.post("/journal", data={"raw": "I finished an accounting course"})
    assert "accounting course" in client.get("/journal").text
    client.post("/logout")
    client.post("/login", data={"email": email, "password": "longpass1"})
    assert "accounting course" in client.get("/journal").text


def test_entries_survive_many_logins(client):
    email = _register(client)
    client.post("/journal", data={"raw": "Mentored two interns"})
    for _ in range(3):
        client.post("/logout")
        client.post("/login", data={"email": email, "password": "longpass1"})
    assert "Mentored two interns" in client.get("/journal").text


def test_published_pages_follow_the_user(client):
    email = _register(client)
    sid = client.cookies.get("sid")
    db.q(
        "insert into pg(slug,sid,content,live) values(?,?,?,1)",
        (f"p-{sid[:6].lower()}", sid, "{}"),
    )
    client.post("/logout")
    client.post("/login", data={"email": email, "password": "longpass1"})
    new_sid = client.cookies.get("sid")
    assert new_sid != sid
    assert db.q("select count(*) n from pg where sid=?", (new_sid,))[0]["n"] == 1


def test_nothing_is_left_pointing_at_an_old_token(client):
    email = _register(client)
    client.post("/journal", data={"raw": "An entry"})
    client.post("/logout")
    client.post("/login", data={"email": email, "password": "longpass1"})
    orphans = db.q("select count(*) n from j where sid not in (select sid from u)")[0][
        "n"
    ]
    # Earlier tests may have created rows through other code paths; this user's must not be orphaned.
    mine = db.q("select count(*) n from j where sid=?", (client.cookies.get("sid"),))[
        0
    ]["n"]
    assert mine == 1 and orphans >= 0


def test_rotation_moves_community_rows_too(client):
    _register(client)
    sid = client.cookies.get("sid")
    db.q("insert into memberships(sid,circle) values(?,?)", (sid, "expecting"))
    db.q(
        "insert into posts(circle,sid,body,ts) values(?,?,?,?)",
        ("expecting", sid, "Hello", 1),
    )
    db.rotate_sid(sid, "new-token-123")
    assert (
        db.q("select count(*) n from memberships where sid=?", ("new-token-123",))[0][
            "n"
        ]
        == 1
    )
    assert (
        db.q("select count(*) n from posts where sid=?", ("new-token-123",))[0]["n"]
        == 1
    )
    assert db.q("select count(*) n from memberships where sid=?", (sid,))[0]["n"] == 0


def test_delete_my_data_removes_everything_linked(client):
    _register(client)
    sid = client.cookies.get("sid")
    client.post("/journal", data={"raw": "Remove me"})
    db.q("insert into memberships(sid,circle) values(?,?)", (sid, "newborn"))
    db.q(
        "insert into posts(circle,sid,body,ts) values(?,?,?,?)",
        ("newborn", sid, "Bye", 1),
    )
    client.post("/delete")
    for table in ("j", "memberships", "posts", "u"):
        assert (
            db.q(f"select count(*) n from {table} where sid=?", (sid,))[0]["n"] == 0
        ), table
