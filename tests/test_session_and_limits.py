"""Step 5: session rotation on login and logout, no password hash in page data, request size limit."""

import uuid

from fastapi.testclient import TestClient

from app import main


def _new_account():
    email = f"sec-{uuid.uuid4().hex[:8]}@example.com"
    return email, {"email": email, "password": "longpass1", "confirm": "longpass1"}


def test_old_cookie_stops_working_after_logout(client):
    _, form = _new_account()
    client.post("/register", data=form)
    old_sid = client.cookies.get("sid")
    assert client.get("/journal").status_code == 200  # logged in

    client.post("/logout")
    # Replay the old cookie, as if it had been stolen before logout.
    replay = TestClient(main.app, follow_redirects=False)
    replay.cookies.set("sid", old_sid)
    assert replay.get("/journal").headers["location"] == "/login"


def test_login_issues_a_new_session_and_old_one_stops_working(client):
    email, form = _new_account()
    client.post("/register", data=form)
    first_sid = client.cookies.get("sid")
    client.post("/logout")

    client.post("/login", data={"email": email, "password": "longpass1"})
    second_sid = client.cookies.get("sid")
    assert second_sid and second_sid != first_sid

    replay = TestClient(main.app, follow_redirects=False)
    replay.cookies.set("sid", first_sid)
    assert replay.get("/journal").headers["location"] == "/login"


def test_session_cookie_flags(client):
    _, form = _new_account()
    r = client.post("/register", data=form)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_current_user_does_not_carry_password_hash(logged_in):
    sid = logged_in.cookies.get("sid")

    class Req:
        cookies = {"sid": sid}

    _, u = main.current(Req())
    assert u is not None
    assert "pw" not in u
    assert "email" in u


def test_oversized_post_is_rejected_early(client):
    r = client.post(
        "/contact",
        content=b"name=a&" + b"x" * (70 * 1024),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 413


def test_normal_post_is_not_affected_by_size_limit(client, monkeypatch):
    monkeypatch.setattr(main, "send_mail", lambda *a: True)
    r = client.post(
        "/contact", data={"name": "Ana", "email": "ana@example.com", "message": "Hi"}
    )
    assert r.status_code == 303
