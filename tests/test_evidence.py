"""Honesty rule: skills are kept only when their evidence is in the user's own words."""

from app import ai, evidence

RESUME = "I ran a small bakery for four years, handling orders, staff rota and supplier payments."
JOURNAL = "Completed an online course in data analysis with Python."


def test_exact_quote_is_supported():
    assert evidence.supported(
        "handling orders, staff rota and supplier payments", [RESUME]
    )


def test_quote_is_case_and_punctuation_insensitive():
    assert evidence.supported("RAN A SMALL BAKERY FOR FOUR YEARS!", [RESUME])


def test_paraphrase_with_one_changed_word_is_supported():
    # 10-word quote, one word changed: 90% of words still match, which is the threshold.
    quote = "ran a small bakery for four years handling orders staff rota and suppliers"
    assert evidence.supported(quote, [RESUME])


def test_fabricated_skill_is_not_supported():
    assert not evidence.supported("fluent in Mandarin and Japanese", [RESUME, JOURNAL])


def test_short_quote_is_not_enough_evidence():
    assert not evidence.supported("bakery", [RESUME])


def test_empty_evidence_is_not_supported():
    assert not evidence.supported("", [RESUME])


def test_evidence_from_journal_counts():
    assert evidence.supported("online course in data analysis", [RESUME, JOURNAL])


def test_evidence_must_come_from_one_source_not_mixed():
    """Words spread across two different sources do not count as one quote."""
    assert not evidence.supported(
        "four years bakery course online analysis", [RESUME, JOURNAL]
    )


def test_keep_supported_splits_kept_and_removed():
    skills = [
        {
            "name": "Budgeting",
            "evidence": "handling orders, staff rota and supplier payments",
        },
        {"name": "Mandarin", "evidence": "fluent in Mandarin and Japanese"},
    ]
    kept, removed = evidence.keep_supported(skills, [RESUME])
    assert [s["name"] for s in kept] == ["Budgeting"]
    assert removed == 1


def test_profile_route_drops_fabricated_skill_and_says_so(logged_in, monkeypatch):
    fake = {
        "summary": "Baker",
        "break_statement": "Career break",
        "skills": [
            {
                "name": "Supplier management",
                "evidence": "handling orders, staff rota and supplier payments",
            },
            {"name": "Mandarin", "evidence": "fluent in Mandarin and Japanese"},
        ],
    }
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(ai, "ask", lambda *a, **k: (fake, "ai"))
    html = logged_in.post("/profile", data={"text": RESUME}).text
    assert 'value="Supplier management"' in html
    assert "Mandarin" not in html
    assert "1 suggested skill(s) were removed" in html


def test_profile_route_keeps_skill_with_quote_from_text(logged_in, monkeypatch):
    fake = {
        "summary": "Baker",
        "break_statement": "",
        "skills": [
            {
                "name": "Operations",
                "evidence": "handling orders, staff rota and supplier payments",
            }
        ],
    }
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(ai, "ask", lambda *a, **k: (fake, "ai"))
    html = logged_in.post("/profile", data={"text": RESUME}).text
    assert 'value="Operations"' in html
    assert "were removed" not in html
