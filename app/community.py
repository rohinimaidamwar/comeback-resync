"""Community circles: join and leave, a short discussion board for each circle, and sample stories.

Circles are private to their members. Posts show a first name only. Contact details and links
are not allowed, so nobody shares an email address or phone number by accident.
"""

import json
import re
import time
from pathlib import Path

from app import db

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "community_samples.json"

CIRCLES = {
    "expecting": (
        "Expecting",
        "Plan your leave and hand over work without losing ground.",
    ),
    "newborn": ("Newborn phase", "Tiny five-minute wins while sleep is short."),
    "returning": (
        "Returning soon",
        "Get ready to walk back in: profile, jobs and interviews.",
    ),
}
STAGE_TO_CIRCLE = {
    "expecting": "expecting",
    "newborn": "newborn",
    "planning": "returning",
}
MAX_POST = 500

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE = re.compile(r"(?:\+?\d[\s().-]?){7,}")
LINK = re.compile(r"https?://|www\.", re.IGNORECASE)

MESSAGES = {
    "joined": "You joined the circle.",
    "left": "You left the circle.",
    "posted": "Posted.",
    "deleted": "Post deleted.",
    "empty": "Write something first.",
    "contact": "Please don't share email addresses or phone numbers here.",
    "links": "Links aren't allowed in circles yet.",
    "toofast": "You have posted a lot just now. Please wait a few minutes.",
    "join": "Join this circle to read and post.",
}


def samples() -> dict:
    return json.loads(SAMPLES.read_text(encoding="utf-8"))


def problem_with(body: str):
    """The reason a post is refused, or None if it is fine."""
    if not body.strip():
        return "empty"
    if EMAIL.search(body) or PHONE.search(body):
        return "contact"
    if LINK.search(body):
        return "links"
    return None


def counts() -> dict:
    rows = db.q("select circle, count(*) n from memberships group by circle")
    return {r["circle"]: r["n"] for r in rows}


def joined(sid: str) -> set:
    return {
        r["circle"] for r in db.q("select circle from memberships where sid=?", (sid,))
    }


def join(sid: str, slug: str) -> bool:
    if slug not in CIRCLES:
        return False
    db.q("insert or ignore into memberships(sid, circle) values(?, ?)", (sid, slug))
    return True


def leave(sid: str, slug: str) -> bool:
    if slug not in CIRCLES:
        return False
    db.q("delete from memberships where sid=? and circle=?", (sid, slug))
    return True


def circle_cards(sid: str, stage: str) -> list[dict]:
    mine, n, suggested = joined(sid), counts(), STAGE_TO_CIRCLE.get(stage)
    return [
        {
            "slug": slug,
            "name": name,
            "about": about,
            "members": n.get(slug, 0),
            "joined": slug in mine,
            "suggested": slug == suggested,
        }
        for slug, (name, about) in CIRCLES.items()
    ]


def posts(slug: str, sid: str) -> list[dict]:
    """Real posts first (newest first), then the labelled samples. Never exposes anyone's token."""
    rows = db.q(
        "select p.id, p.sid, p.body, p.ts, u.name from posts p join u on u.sid = p.sid "
        "where p.circle=? order by p.id desc limit 50",
        (slug,),
    )
    real = [
        {
            "id": r["id"],
            "name": r["name"] or "Member",
            "body": r["body"],
            "when": time.strftime("%d %b", time.localtime(r["ts"])),
            "mine": r["sid"] == sid,
            "sample": False,
        }
        for r in rows
    ]
    fake = [
        {
            "id": None,
            "name": p["name"],
            "body": p["body"],
            "when": "",
            "mine": False,
            "sample": True,
        }
        for p in samples()["posts"]
        if p["circle"] == slug
    ]
    return real + fake


def add_post(sid: str, slug: str, body: str) -> None:
    db.q(
        "insert into posts(circle, sid, body, ts) values(?, ?, ?, ?)",
        (slug, sid, body.strip()[:MAX_POST], int(time.time())),
    )


def delete_post(sid: str, post_id: int) -> None:
    """Only the author can delete a post."""
    db.q("delete from posts where id=? and sid=?", (post_id, sid))
