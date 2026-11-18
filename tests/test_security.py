"""Escaping of generated pages, rate limiting, and contact form behaviour."""

import pytest

from app import main


def test_generated_portfolio_escapes_model_output(client, logged_in):
    """Model output must never be rendered as HTML."""
    # A published page's content is stored as JSON. Build a page with hostile text.
    from app import db
    import json

    db.q(
        "insert or replace into pg(slug,sid,content,live) values(?,?,?,1)",
        (
            "escape-test",
            "other-sid",
            json.dumps(
                {
                    "headline": "<script>alert(1)</script>",
                    "about": "<img src=x onerror=alert(2)>",
                    "services": ["<b>bold</b>"],
                }
            ),
        ),
    )
    html = client.get("/p/escape-test").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(2)&gt;" in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_login_rate_limit_ignores_spoofed_first_forwarded_entry(client):
    """Only the last X-Forwarded-For entry (added by Caddy) counts. Spoofed entries must not help."""
    for i in range(10):
        client.post(
            "/login",
            data={"email": "x@example.com", "password": "wrongpass"},
            headers={"X-Forwarded-For": f"203.0.113.{i}, 198.51.100.7"},
        )
    blocked = client.post(
        "/login",
        data={"email": "x@example.com", "password": "wrongpass"},
        headers={"X-Forwarded-For": "192.0.2.99, 198.51.100.7"},
    )
    assert "Too many tries" in blocked.text


def test_ip_uses_last_forwarded_entry():
    class Req:
        headers = {"x-forwarded-for": "1.1.1.1, 2.2.2.2"}
        client = None

    assert main.ip(Req()) == "2.2.2.2"


def test_contact_honeypot_sends_nothing(client, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_mail", lambda *a: sent.append(a) or True)
    r = client.post(
        "/contact",
        data={
            "name": "Bot",
            "email": "bot@example.com",
            "message": "buy now",
            "website": "http://spam",
        },
    )
    assert r.headers["location"] == "/contact?sent=1"
    assert sent == []


def test_contact_success_shows_sent(client, monkeypatch):
    monkeypatch.setattr(main, "send_mail", lambda *a: True)
    r = client.post(
        "/contact", data={"name": "Ana", "email": "ana@example.com", "message": "Hi"}
    )
    assert r.headers["location"] == "/contact?sent=1"


def test_contact_mail_failure_is_reported_not_hidden(client, monkeypatch):
    """Regression: the form used to say 'sent' even when delivery failed."""

    def boom(*a):
        raise OSError("smtp down")

    monkeypatch.setattr(main, "send_mail", boom)
    r = client.post(
        "/contact", data={"name": "Ana", "email": "ana@example.com", "message": "Hi"}
    )
    assert r.headers["location"] == "/contact?err=mail"
    page = client.get("/contact?err=mail").text
    assert "could not send your message" in page


def test_contact_unconfigured_smtp_is_reported_as_not_sent(client, monkeypatch):
    monkeypatch.setattr(main, "send_mail", lambda *a: False)
    r = client.post(
        "/contact", data={"name": "Ana", "email": "ana@example.com", "message": "Hi"}
    )
    assert r.headers["location"] == "/contact?err=mail"


def test_contact_rejects_invalid_email(client, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_mail", lambda *a: sent.append(a) or True)
    r = client.post(
        "/contact", data={"name": "Ana", "email": "not-an-email", "message": "Hi"}
    )
    assert r.headers["location"] == "/contact?err=email"
    assert sent == []


def test_contact_rate_limit_per_ip(client, monkeypatch):
    monkeypatch.setattr(main, "send_mail", lambda *a: True)
    locations = [
        client.post(
            "/contact",
            data={"name": "A", "email": "a@example.com", "message": "m"},
            headers={"X-Forwarded-For": "198.51.100.50"},
        ).headers["location"]
        for _ in range(7)
    ]
    assert locations[-1] == "/contact?err=limit"


@pytest.mark.parametrize(
    "path", ["/privacy", "/contact", "/money", "/login", "/register"]
)
def test_public_pages_render(client, path):
    assert client.get(path).status_code == 200


def test_privacy_page_states_no_employer_sharing(client):
    html = client.get("/privacy").text
    assert "Nothing you write here is shared with employers" in html
    assert "Delete my data" in html
