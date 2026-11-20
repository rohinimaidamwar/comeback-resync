"""Contact-form email: branded HTML with escaped visitor text, a plain-text part, and no header injection."""

from datetime import datetime, timezone

from app import mail_content

WHEN = datetime(2026, 11, 20, 10, 30, tzinfo=timezone.utc)


def test_subject_names_the_sender_and_the_brand():
    subject, _, _ = mail_content.build("Ana", "ana@example.com", "Hi", WHEN)
    assert subject == "New message from Ana | hercomeback"


def test_visitor_html_is_escaped():
    _, _, page = mail_content.build(
        "<b>Eve</b>", "eve@example.com", "<script>alert(1)</script>", WHEN
    )
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "&lt;b&gt;Eve&lt;/b&gt;" in page


def test_newlines_become_line_breaks_in_html_only():
    _, text, page = mail_content.build(
        "Ana", "ana@example.com", "line one\nline two", WHEN
    )
    assert "line one<br>line two" in page
    assert "line one\nline two" in text


def test_header_injection_is_stripped():
    subject, text, _ = mail_content.build(
        "Ana\r\nBcc: spy@example.com", "ana@example.com", "Hi", WHEN
    )
    assert (
        "\r" not in subject and "\n" not in subject
    )  # one header line, so no extra headers


def test_both_parts_carry_the_sender_and_date():
    _, text, page = mail_content.build("Ana", "ana@example.com", "Hi", WHEN)
    for part in (text, page):
        assert "ana@example.com" in part
        assert "20 Nov 2026, 10:30 UTC" in part


def test_reply_button_points_back_to_the_sender():
    _, _, page = mail_content.build("Ana", "ana@example.com", "Hi", WHEN)
    assert (
        'href="mailto:ana@example.com?subject=Re: your message to hercomeback"' in page
        or "mailto:ana@example.com?subject=Re%3A" in page
        or "mailto:ana@example.com?subject=Re:" in page
    )


def test_send_mail_builds_both_parts_without_error(monkeypatch):
    """Regression: send_mail must be able to build the email (this import was missing)."""
    from app import main

    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)
    assert (
        main.send_mail("Ana", "ana@example.com", "Hi") is False
    )  # not configured: saved locally, reported as not sent


def test_welcome_mail_greets_by_first_name_and_links_the_app():
    subject, text, page = mail_content.welcome("Ananya Rao")
    assert subject == "Welcome to hercomeback"
    assert text.startswith("Hi Ananya,")
    assert "https://hercomeback.work" in text and "https://hercomeback.work" in page


def test_welcome_mail_without_a_name_is_still_friendly():
    _, text, _ = mail_content.welcome("")
    assert text.startswith("Hi there,")


def test_welcome_mail_escapes_the_name(monkeypatch):
    _, _, page = mail_content.welcome("<img src=x onerror=alert(1)>")
    assert "<img src=x" not in page


def test_sign_up_schedules_a_welcome_email(client, monkeypatch):
    from app import main

    sent = []
    monkeypatch.setattr(
        main, "send_welcome", lambda to, name: sent.append((to, name)) or True
    )
    client.post(
        "/register",
        data={
            "email": "newmember@example.com",
            "password": "longpass1",
            "confirm": "longpass1",
            "name": "Ananya",
        },
    )
    assert sent == [("newmember@example.com", "Ananya")]


def test_demo_accounts_get_no_welcome_email(client, monkeypatch):
    from app import main

    sent = []
    monkeypatch.setattr(main, "send_welcome", lambda to, name: sent.append(to) or True)
    client.post("/demo")
    assert sent == []


def test_welcome_is_skipped_without_smtp_and_does_not_write_outbox(
    monkeypatch, tmp_path
):
    from app import main

    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main.send_welcome("x@example.com", "Ana") is False
    assert not (tmp_path / "db" / "outbox.txt").exists()


def test_sign_up_still_works_when_the_welcome_send_fails(client, monkeypatch):
    """Real failure path: SMTP is configured but the connection fails. Sign-up must still succeed."""
    from app import main

    monkeypatch.setenv("SMTP_USER", "hello@hercomeback.work")
    monkeypatch.setenv("SMTP_PASS", "not-a-real-password")

    def broken(*args, **kwargs):
        raise OSError("smtp down")

    monkeypatch.setattr(main.smtplib, "SMTP_SSL", broken)
    r = client.post(
        "/register",
        data={
            "email": "fails@example.com",
            "password": "longpass1",
            "confirm": "longpass1",
        },
    )
    assert r.status_code == 303
    assert main.send_welcome("fails@example.com", "Ana") is False
