"""Practice partners for interview prep.

Members opt in and are matched by role and years of experience. The pool shows only a first
name, role and years, never an email address. Sample profiles are fictional and labelled.
"""

import json
from pathlib import Path

from app import db

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "practice_samples.json"


def record(raw) -> dict:
    return json.loads(raw) if raw else {}


def samples() -> list[dict]:
    return json.loads(SAMPLES.read_text(encoding="utf-8"))


def _score(me: dict, other: dict) -> int:
    same_role = (
        2 if (me.get("role") or "").lower() == (other.get("role") or "").lower() else 0
    )
    gap = abs(int(me.get("years") or 0) - int(other.get("years") or 0))
    return same_role + max(0, 3 - gap // 2)


def pool(me_sid: str, me: dict, limit: int = 6) -> list[dict]:
    """Opted-in members (not the signed-in user) plus the labelled samples, best matches first."""
    members = []
    for row in db.q("select sid, name, practice from u where practice is not null"):
        if row["sid"] == me_sid:
            continue  # never list the signed-in user; the sid itself is never shown
        rec = record(row["practice"])
        if rec.get("opt_in"):
            members.append(
                {
                    "name": row["name"] or "Member",
                    "role": rec.get("role", ""),
                    "years": rec.get("years", 0),
                    "sample": False,
                }
            )
    everyone = members + samples()
    everyone.sort(key=lambda p: _score(me, p), reverse=True)
    return everyone[:limit]
