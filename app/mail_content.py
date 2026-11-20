"""Content of the team email from the contact form: a plain-text part and a branded HTML part.

Visitor text is escaped before it goes into the HTML, so nothing a visitor types can add markup.
"""

import html
import os
import re
from datetime import datetime, timezone

MOCHA = "#8A6A4F"
INK = "#3A3128"
MUTED = "#7D6F62"
CREAM = "#FBF6EE"
SAND = "#F0E6D6"


def _line(s: str, limit: int) -> str:
    """One line, no control characters (stops header injection)."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", s).strip()[:limit]


def build(name: str, email: str, message: str, when: datetime | None = None):
    """Return (subject, plain_text, html_text)."""
    name = _line(name, 100) or "Someone"
    email = _line(email, 200)
    when = (when or datetime.now(timezone.utc)).strftime("%d %b %Y, %H:%M UTC")
    body = message.strip()[:3000]

    subject = f"New message from {name} | hercomeback"
    text = (
        "New message from the hercomeback contact form\n\n"
        f"Name: {name}\n"
        f"Email: {email}\n"
        f"Received: {when}\n\n"
        f"{body}\n\n"
        "Reply to this email to answer the sender directly.\n"
    )

    e_name = html.escape(name)
    e_email = html.escape(email)
    e_when = html.escape(when)
    e_body = html.escape(body).replace("\n", "<br>")
    e_subject = html.escape("Re: your message to hercomeback")
    page = f"""<!doctype html><html><body style="margin:0;background:{CREAM};font-family:Helvetica,Arial,sans-serif;color:{INK}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CREAM};padding:24px 12px"><tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:18px;overflow:hidden;border:1px solid {SAND}">
<tr><td style="background:{SAND};padding:22px 26px">
<div style="font-family:Georgia,serif;font-style:italic;font-size:24px;color:{MOCHA}">hercomeback</div>
<div style="font-size:13px;color:{MUTED};margin-top:4px">New message from the contact form</div>
</td></tr>
<tr><td style="padding:24px 26px 8px">
<div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:{MUTED}">From</div>
<div style="font-size:18px;font-weight:700;margin-top:2px">{e_name}</div>
<div style="font-size:15px;margin-top:4px"><a href="mailto:{e_email}" style="color:{MOCHA};text-decoration:none">{e_email}</a></div>
<div style="font-size:13px;color:{MUTED};margin-top:4px">Received {e_when}</div>
</td></tr>
<tr><td style="padding:14px 26px 22px">
<div style="background:{CREAM};border-radius:14px;padding:18px 18px;font-size:15px;line-height:1.6">{e_body}</div>
</td></tr>
<tr><td align="center" style="padding:0 26px 26px">
<a href="mailto:{e_email}?subject={e_subject}" style="display:inline-block;background:{MOCHA};color:#ffffff;text-decoration:none;border-radius:999px;padding:12px 26px;font-weight:600;font-size:15px">Reply to {e_name}</a>
</td></tr>
<tr><td style="background:{SAND};padding:14px 26px;font-size:12px;color:{MUTED}">
Sent from the hercomeback contact form. Nothing here is shared with employers.
</td></tr>
</table></td></tr></table></body></html>"""
    return subject, text, page


APP_URL = os.getenv("APP_URL", "https://hercomeback.work")


def welcome(name: str):
    """Return (subject, plain_text, html_text) for the welcome email to a new member."""
    first = _line(name, 40).split(" ")[0] if name else ""
    greet = f"Hi {first}," if first else "Hi there,"
    e_greet = html.escape(greet[:-1]) + ","
    subject = "Welcome to hercomeback"
    text = (
        f"{greet}\n\n"
        "Welcome to hercomeback. Here is a simple way to start:\n\n"
        "1. Log a small win in your break journal.\n"
        "2. Build your profile from your own words.\n"
        "3. Follow your roadmap back to work.\n\n"
        f"Open the app: {APP_URL}\n\n"
        "You can log out or delete your data at any time from the footer of the app.\n\n"
        "The hercomeback team\n"
        "General information, not legal, tax or medical advice."
    )
    page = f"""<!doctype html><html><body style="margin:0;background:{CREAM};font-family:Helvetica,Arial,sans-serif;color:{INK}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CREAM};padding:24px 12px"><tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:18px;overflow:hidden;border:1px solid {SAND}">
<tr><td style="background:{SAND};padding:22px 26px">
<div style="font-family:Georgia,serif;font-style:italic;font-size:24px;color:{MOCHA}">hercomeback</div>
</td></tr>
<tr><td style="padding:26px 26px 8px">
<div style="font-family:Georgia,serif;font-size:24px;color:{INK}">{e_greet}</div>
<p style="font-size:15px;line-height:1.6;margin:12px 0 0">Welcome. A career break is a chapter, not a gap. Here is a simple way to start:</p>
</td></tr>
<tr><td style="padding:12px 26px 6px;font-size:15px;line-height:1.7">
<div><b style="color:{MOCHA}">1.</b> Log a small win in your break journal.</div>
<div><b style="color:{MOCHA}">2.</b> Build your profile from your own words.</div>
<div><b style="color:{MOCHA}">3.</b> Follow your roadmap back to work.</div>
</td></tr>
<tr><td align="center" style="padding:18px 26px 26px">
<a href="{html.escape(APP_URL)}" style="display:inline-block;background:{MOCHA};color:#ffffff;text-decoration:none;border-radius:999px;padding:12px 26px;font-weight:600;font-size:15px">Open hercomeback</a>
</td></tr>
<tr><td style="background:{SAND};padding:14px 26px;font-size:12px;color:{MUTED};line-height:1.5">
You received this because you created an account at hercomeback. General information, not legal, tax or medical advice.
</td></tr>
</table></td></tr></table></body></html>"""
    return subject, text, page
