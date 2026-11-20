"""Practice partners for interview prep.

Members choose two things: whether they want to be interviewed and whether they can interview
others. They are matched by role and years of experience. The pool shows only a first name, role,
years and those intents, never an email address. Sample profiles are fictional and labelled.
"""

import json
from pathlib import Path

from app import db

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "practice_samples.json"
SESSION_TYPES = {
    "swap": "30-min swap (both)",
    "interview_me": "Ask them to interview me",
    "i_interview": "Offer to interview them",
}
TOP_MATCH_SCORE = 4  # same role plus close experience
TONES = 5  # avatar colours are CSS classes t0..t4


def record(raw) -> dict:
    return json.loads(raw) if raw else {}


def flags(rec: dict) -> tuple[bool, bool]:
    """(wants to be interviewed, can interview). A record from before the split counts as both."""
    old = bool(rec.get("opt_in", False))
    return bool(rec.get("want_interview", old)), bool(rec.get("can_interview", old))


def requests(rec: dict) -> list[dict]:
    """Saved requests as {key, type, type_label}. Older entries were plain text."""
    out = []
    for r in rec.get("requests", []):
        if isinstance(r, str):
            r = {"key": r, "type": "swap"}
        out.append(
            {**r, "type_label": SESSION_TYPES.get(r.get("type"), SESSION_TYPES["swap"])}
        )
    return out


def samples() -> list[dict]:
    return json.loads(SAMPLES.read_text(encoding="utf-8"))


def _score(me: dict, other: dict) -> int:
    same_role = (
        2 if (me.get("role") or "").lower() == (other.get("role") or "").lower() else 0
    )
    gap = abs(int(me.get("years") or 0) - int(other.get("years") or 0))
    return same_role + max(0, 3 - gap // 2)


def _tags(want: bool, can: bool) -> list[str]:
    if want and can:
        return ["Open to swap"]
    if can:
        return ["Can interview you"]
    if want:
        return ["Looking to practice"]
    return []


def _peer(
    me: dict, name: str, role: str, years: int, want: bool, can: bool, sample: bool
) -> dict:
    score = _score(me, {"role": role, "years": years}) if me.get("role") else 0
    return {
        "key": f"{name} ({role})",
        "name": name,
        "initial": (name[:1] or "?").upper(),
        "tone": f"t{sum(map(ord, name)) % TONES}",
        "role": role,
        "years": years,
        "want": want,
        "can": can,
        "tags": _tags(want, can),
        "sample": sample,
        "score": score,
        "top": score >= TOP_MATCH_SCORE,
    }


def pool(me_sid: str, me: dict, limit: int = 8) -> list[dict]:
    """Opted-in members (not the signed-in user) plus the labelled samples, best matches first."""
    peers = []
    for row in db.q("select sid, name, practice from u where practice is not null"):
        if row["sid"] == me_sid:
            continue  # never list the signed-in user; the sid itself is never shown
        rec = record(row["practice"])
        want, can = flags(rec)
        if want or can:
            peers.append(
                _peer(
                    me,
                    row["name"] or "Member",
                    rec.get("role", ""),
                    int(rec.get("years") or 0),
                    want,
                    can,
                    False,
                )
            )
    for s in samples():
        peers.append(
            _peer(
                me,
                s["name"],
                s["role"],
                s["years"],
                s["want_interview"],
                s["can_interview"],
                True,
            )
        )
    peers.sort(key=lambda p: p["score"], reverse=True)
    return peers[:limit]
