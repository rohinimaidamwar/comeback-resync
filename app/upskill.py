"""Study plans for the Upskilling step.

Plans come from the user's goal and profile. Course links only point at provider homepages
that were checked (see data/courses.json), so no course URL is ever generated.
"""

import json
from pathlib import Path

from app import ai_data
from app.schemas import CourseProvider

COURSES = Path(__file__).resolve().parent.parent / "data" / "courses.json"

# Starter topics used when the AI is unavailable. Generic, and none claims any experience.
FALLBACK_TOPICS = {
    "A job": [
        "Digital skills and spreadsheets",
        "Written communication",
        "Presenting your work",
    ],
    "Freelance work": [
        "Client communication",
        "Basic bookkeeping",
        "Writing a short proposal",
    ],
    "My own venture": [
        "Basic business planning",
        "Basic bookkeeping",
        "Marketing basics",
    ],
}


def fallback_plan(goal: str) -> dict:
    topics = FALLBACK_TOPICS.get(goal, FALLBACK_TOPICS["A job"])
    weeks = [
        {
            "title": f"Week {i}: {topic}",
            "tasks": [
                f"Spend 20 minutes a day on {topic.lower()}.",
                "Find one free lesson on one of the sites below and note one idea from it.",
                "Write three sentences on what you learned and how you would use it.",
            ],
        }
        for i, topic in enumerate(topics, start=1)
    ]
    return {"topics": topics, "weeks": weeks}


def prompt(goal: str, stage: str, skills: list) -> str:
    return (
        f"Goal: {goal}. Stage: {stage}. Existing skills: {ai_data.data(skills)}. "
        "Make a study plan of 3 or 4 weeks that builds skills for this goal, on top of the existing skills. "
        'Return JSON {"topics": [str], "weeks": [{"title": str, "tasks": [str]}]} with one week per topic '
        "and 3 short daily tasks per week. Do not name courses, providers, websites or links, "
        "and do not say the user already has any skill."
    )


def clean(d: dict) -> dict:
    """Trim the plan to safe sizes and add the done flag each task needs."""
    return {
        "topics": [str(t)[:60] for t in d["topics"][:4]],
        "weeks": [
            {
                "title": str(w["title"])[:80],
                "tasks": [
                    {"text": str(t)[:160], "done": False} for t in w["tasks"][:4]
                ],
            }
            for w in d["weeks"][:4]
        ],
    }


def providers() -> list[dict]:
    """Only providers whose entry has been verified."""
    entries = json.loads(COURSES.read_text(encoding="utf-8"))
    return [
        CourseProvider.model_validate(e).model_dump()
        for e in entries
        if e.get("verified")
    ]
