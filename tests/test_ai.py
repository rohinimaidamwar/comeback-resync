"""AI layer: schema validation, one retry on bad output, graceful fallback. Anthropic is mocked."""

import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app import ai
from app.schemas import JobFit, JobMatches, JournalLine, Profile, SiteCopy


class Demo(BaseModel):
    summary: str
    skills: list[str]


GOOD = json.dumps({"summary": "Bakery owner.", "skills": ["Budgeting"]})


def _reply(text):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


class FakeClient:
    """Returns the queued replies in order. An Exception in the queue is raised instead."""

    calls = 0
    queue: list = []

    def __init__(self, *args, **kwargs):
        pass

    @property
    def messages(self):
        return self

    def create(self, **kwargs):
        FakeClient.calls += 1
        item = FakeClient.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def fake_api(monkeypatch):
    FakeClient.calls = 0
    FakeClient.queue = []
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(ai, "Anthropic", FakeClient)
    return FakeClient


def test_no_key_returns_fallback_without_calling_api(monkeypatch, fake_api):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    data, source = ai.ask("p", {"summary": "fb", "skills": []}, schema=Demo)
    assert (data, source) == ({"summary": "fb", "skills": []}, "fallback")
    assert fake_api.calls == 0


def test_valid_json_returns_validated_ai_result(fake_api):
    fake_api.queue = [_reply(GOOD)]
    data, source = ai.ask("p", {}, schema=Demo)
    assert source == "ai" and data == {
        "summary": "Bakery owner.",
        "skills": ["Budgeting"],
    }
    assert fake_api.calls == 1


def test_code_fenced_json_is_accepted(fake_api):
    fake_api.queue = [_reply("```json\n" + GOOD + "\n```")]
    _, source = ai.ask("p", {}, schema=Demo)
    assert source == "ai"


def test_bad_json_is_retried_once_then_succeeds(fake_api):
    fake_api.queue = [_reply("not json"), _reply(GOOD)]
    _, source = ai.ask("p", {}, schema=Demo)
    assert source == "ai" and fake_api.calls == 2


def test_bad_json_twice_falls_back(fake_api):
    fake_api.queue = [_reply("not json"), _reply("still not json")]
    data, source = ai.ask("p", {"summary": "fb", "skills": []}, schema=Demo)
    assert (data, source) == ({"summary": "fb", "skills": []}, "fallback")
    assert fake_api.calls == 2


def test_missing_required_field_counts_as_bad_output(fake_api):
    fake_api.queue = [_reply('{"other": 1}'), _reply('{"other": 2}')]
    _, source = ai.ask("p", {}, schema=Demo)
    assert source == "fallback" and fake_api.calls == 2


@pytest.mark.parametrize(
    "bad",
    [
        {"summary": 123, "skills": []},  # wrong type for summary
        {"summary": "ok", "skills": "Budgeting"},  # skills must be a list, not a string
        {"summary": "ok", "skills": [{"x": 1}]},  # list items must be strings
    ],
)
def test_wrong_types_are_rejected_not_passed_to_pages(fake_api, bad):
    """Regression: a wrong type used to reach the page and cause a 500 error."""
    fake_api.queue = [_reply(json.dumps(bad)), _reply(json.dumps(bad))]
    data, source = ai.ask("p", {"summary": "fb", "skills": []}, schema=Demo)
    assert source == "fallback" and data["summary"] == "fb"


def test_api_error_falls_back_without_retry(fake_api):
    fake_api.queue = [RuntimeError("boom")]
    data, source = ai.ask("p", {"summary": "fb", "skills": []}, schema=Demo)
    assert source == "fallback" and fake_api.calls == 1


def test_non_text_blocks_are_ignored(fake_api):
    """Newer models can return a thinking block before the text block."""
    reply = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="..."),
            SimpleNamespace(type="text", text=GOOD),
        ],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    fake_api.queue = [reply]
    _, source = ai.ask("p", {}, schema=Demo)
    assert source == "ai"


def test_usage_log_has_no_prompt_text(fake_api, capsys):
    fake_api.queue = [_reply(GOOD)]
    ai.ask("SECRET RESUME TEXT", {}, schema=Demo)
    out = capsys.readouterr().out
    assert "AI usage" in out and "SECRET RESUME TEXT" not in out


def test_schemas_accept_the_shapes_the_prompts_ask_for():
    assert Profile.model_validate(
        {
            "summary": "s",
            "break_statement": "b",
            "skills": [{"name": "n", "evidence": "e"}],
        }
    )
    assert JobMatches.model_validate({"matches": [{"id": 1, "score": 80, "why": "w"}]})
    assert JobFit.model_validate({"score": 70, "why": "w", "talking_points": ["t"]})
    assert SiteCopy.model_validate({"headline": "h", "about": "a", "services": ["s"]})
    assert JournalLine.model_validate({"line": "l"})


def test_scores_must_be_in_range():
    with pytest.raises(Exception):
        JobFit.model_validate({"score": 150, "why": "w", "talking_points": []})
