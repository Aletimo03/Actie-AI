import os
from types import SimpleNamespace
from typing import Literal

import litellm
import pytest
from pydantic import BaseModel, Field

from backend.app.llm import (
    LLM,
    RATE_LIMIT_BUDGET,
    PromptTooLong,
    SchemaError,
    retry_after,
    strip_fences,
    with_schema,
)


class Facts(BaseModel):
    domain: str
    uses_biometrics: bool
    risk: Literal["prohibited", "high", "limited", "minimal", "uncertain"]


VALID = '{"domain": "education", "uses_biometrics": true, "risk": "prohibited"}'
INVALID = '{"domain": "education", "uses_biometrics": true, "risk": "banned"}'


class FakeCompletion:
    """Stands in for litellm.completion: returns the given replies in order."""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        content = self.replies.pop(0)
        if isinstance(content, Exception):
            raise content
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
        )


def make_llm(*replies: str, **kwargs) -> tuple[LLM, FakeCompletion]:
    fake = FakeCompletion(*replies)
    return LLM(model="test/model", completion=fake, **kwargs), fake


def test_valid_reply_is_parsed_into_the_schema():
    llm, fake = make_llm(VALID)
    facts = llm.ask("Extract facts.", "A webcam app...", Facts)
    assert facts == Facts(domain="education", uses_biometrics=True, risk="prohibited")
    call = fake.calls[0]
    assert call["model"] == "test/model"
    assert call["response_format"] is Facts
    assert call["temperature"] == 0
    assert [m["role"] for m in call["messages"]] == ["system", "user"]
    assert call["messages"][0]["content"] == with_schema("Extract facts.", Facts)


def test_schema_with_field_descriptions_is_in_the_system_prompt():
    class Described(BaseModel):
        role: str | None = Field(None, description="provider or deployer")

    system = with_schema("Rules.", Described)
    assert system.startswith("Rules.\n\nReply with JSON matching this schema:\n{")
    assert "provider or deployer" in system


def test_invalid_reply_is_retried_once_with_the_error():
    llm, fake = make_llm(INVALID, VALID)
    assert llm.ask("s", "u", Facts).risk == "prohibited"
    retry = fake.calls[1]["messages"]
    assert [m["role"] for m in retry] == ["system", "user", "assistant", "user"]
    assert retry[2]["content"] == INVALID
    assert "risk" in retry[3]["content"]  # the validation error names the bad field


def test_second_invalid_reply_raises():
    llm, _ = make_llm(INVALID, "not json at all")
    with pytest.raises(SchemaError, match="Facts"):
        llm.ask("s", "u", Facts)


def test_usage_is_counted_across_calls():
    llm, _ = make_llm(INVALID, VALID)
    llm.ask("s", "u", Facts)
    assert (llm.usage.calls, llm.usage.prompt_tokens, llm.usage.completion_tokens) == (2, 200, 40)


def test_optional_settings_are_passed_only_when_set():
    llm, fake = make_llm(VALID, VALID, fallbacks=[], reasoning_effort=None)
    llm.ask("s", "u", Facts)
    assert "fallbacks" not in fake.calls[0] and "reasoning_effort" not in fake.calls[0]

    llm, fake = make_llm(VALID, fallbacks=["groq/other"], reasoning_effort="none")
    llm.ask("s", "u", Facts)
    assert fake.calls[0]["fallbacks"] == ["groq/other"]
    assert fake.calls[0]["reasoning_effort"] == "none"


def test_ollama_gets_a_context_window_and_long_prompts_are_refused():
    fake = FakeCompletion(VALID)
    llm = LLM(model="ollama_chat/m", completion=fake, num_ctx=1000, count_tokens=lambda **_: 700)
    llm.ask("s", "u", Facts)
    assert fake.calls[0]["num_ctx"] == 1000

    too_long = LLM(
        model="ollama_chat/m", completion=fake, num_ctx=1000, count_tokens=lambda **_: 800
    )
    with pytest.raises(PromptTooLong, match="800 prompt tokens"):
        too_long.ask("s", "u", Facts)


def test_hosted_models_get_no_ollama_options():
    llm, fake = make_llm(VALID, num_ctx=1000)
    llm.ask("s", "u", Facts)
    assert "num_ctx" not in fake.calls[0]


def limited(wait: str) -> litellm.RateLimitError:
    message = f"Rate limit reached on tokens per minute (TPM). Please try again in {wait}."
    return litellm.RateLimitError(message, llm_provider="groq", model="m")


def test_retry_after_reads_the_providers_wait():
    assert retry_after(limited("7.0275s")) == 7.5275
    assert retry_after(limited("1m2.5s")) == 63.0
    assert retry_after(RuntimeError("no hint")) == 10.0


def test_rate_limits_are_waited_out_then_retried():
    waits = []
    fake = FakeCompletion(limited("7s"), limited("2.5s"), VALID)
    llm = LLM(model="groq/m", completion=fake, sleep=waits.append)
    assert llm.ask("s", "u", Facts).domain == "education"
    assert waits == [7.5, 3.0] and llm.usage.rate_limit_wait == 10.5
    assert llm.usage.calls == 1  # only the answered call counts


def test_rate_limit_waits_stop_at_the_budget():
    fake = FakeCompletion(*[limited("59s")] * 10)
    llm = LLM(model="groq/m", completion=fake, sleep=lambda _: None)
    with pytest.raises(litellm.RateLimitError):
        llm.ask("s", "u", Facts)
    assert len(fake.calls) == RATE_LIMIT_BUDGET // 60 + 1


def test_code_fences_are_stripped():
    assert strip_fences("```json\n" + VALID + "\n```") == VALID
    assert strip_fences(VALID) == VALID
    llm, _ = make_llm("```json\n" + VALID + "\n```")
    assert llm.ask("s", "u", Facts).domain == "education"


live = pytest.mark.skipif(not os.environ.get("RUN_LIVE_LLM"), reason="calls the model")


@live
def test_live_model_returns_the_schema():
    facts = LLM().ask(
        "Extract the facts about the AI system as JSON.",
        "A webcam app that measures students' emotions in class.",
        Facts,
    )
    assert facts.uses_biometrics
