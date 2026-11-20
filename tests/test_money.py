"""Money basics: every card shows an official source link, and unchecked cards say so."""

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "finance.json"


def test_every_card_has_an_https_source_link(client):
    html = client.get("/money").text
    cards = json.loads(DATA.read_text(encoding="utf-8"))
    assert len(cards) == 4
    for card in cards:
        assert card["source_url"].startswith("https://")
        assert f'href="{card["source_url"]}"' in html


def test_unchecked_cards_are_labelled_not_checked(client):
    html = client.get("/money").text
    assert html.count("Not checked yet.") == 2
    assert html.count("Checked against the official source.") == 2


def test_card_text_avoids_unverified_figures():
    text = " ".join(c["answer"] for c in json.loads(DATA.read_text(encoding="utf-8")))
    assert "26 weeks" not in text  # not confirmed against the official text yet
