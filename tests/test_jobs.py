"""Sample job postings: labelled as samples, random each visit, and matched only on screen."""

import pathlib
import random

from app import ai, main

SAMPLE_FILE = (
    pathlib.Path(__file__).resolve().parent.parent / "data" / "sample_jobs.json"
)


def test_sample_postings_are_valid_fictional_and_have_no_links():
    pool = main.job_pool()
    assert len(pool) == 12
    assert len({j["id"] for j in pool}) == 12
    text = open(SAMPLE_FILE, encoding="utf-8").read().lower()
    assert "placeholder" not in text
    assert "http" not in text  # no links to real job boards or companies


def test_pick_jobs_gives_five_unique_postings():
    pool = main.job_pool()
    picked = main.pick_jobs(pool, rng=random.Random(1))
    ids = [j["id"] for j in picked]
    assert len(ids) == 5 and len(set(ids)) == 5


def test_pick_jobs_differs_between_selections():
    pool = main.job_pool()
    a = [j["id"] for j in main.pick_jobs(pool, rng=random.Random(1))]
    b = [j["id"] for j in main.pick_jobs(pool, rng=random.Random(2))]
    assert a != b


def test_jobs_page_shows_five_labelled_samples(logged_in):
    html = logged_in.get("/jobs").text
    assert html.count("Sample posting") == 5
    assert "(unverified placeholder)" not in html
    assert "fictional" in html


def test_match_scores_only_the_postings_on_screen(logged_in, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # use the keyword fallback
    html = logged_in.post("/jobs/match", data={"ids": ["101", "102"]}).text
    assert html.count("% fit.") == 2
    assert "Harbor Lane Analytics" in html and "Kestrel Content Co" in html
    assert "Brightwater Insights" not in html


def test_match_without_ids_uses_a_random_selection(logged_in, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    html = logged_in.post("/jobs/match", data={}).text
    assert html.count("Sample posting") == 5


def test_match_route_passes_the_posted_ids_to_the_ai(logged_in, monkeypatch):
    seen = {}

    def fake_ask(prompt, fallback, **kwargs):
        seen["prompt"] = prompt
        return fallback, "fallback"

    monkeypatch.setattr(ai, "ask", fake_ask)
    logged_in.post("/jobs/match", data={"ids": ["103"]})
    assert "Freelance Data Analyst" in seen["prompt"]
    assert "Harbor Lane Analytics" not in seen["prompt"]
