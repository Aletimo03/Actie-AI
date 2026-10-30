"""LLM layer: one call shape for every provider, through LiteLLM.

Every agent step asks for a reply that fits a Pydantic schema. The provider's
JSON-schema mode constrains the reply and Pydantic validates it here. A reply
that still doesn't validate is sent back once together with the validation
error; a second failure raises SchemaError, so a node never sees half-parsed
output.

In development, LLM_CACHE_DIR keeps every validated reply on disk under a
hash of the exact request (model, messages, schema, settings): an identical
request is answered from the file for 0 tokens, any change to the prompt,
schema or model is a new request. Off by default, and never on the live
site, where it would store users' descriptions.

The model is a LiteLLM string read from the environment, so moving from the
local Ollama to Groq is a .env change, not a code change:
    LLM_MODEL=ollama_chat/gemma4:12b     (development, local)
    LLM_MODEL=groq/<model>               (live site, see docs on the provider choice)
"""

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

import litellm
from pydantic import BaseModel, ValidationError

LLM_MODEL = os.environ.get("LLM_MODEL", "ollama_chat/gemma4:12b")
LLM_FALLBACKS = [m for m in os.environ.get("LLM_FALLBACKS", "").split(",") if m]
# "none" turns off the hidden reasoning of thinking models: measured on qwen3.5:9b,
# 115 s and 1549 output tokens with it, 1.5 s and 23 tokens without, same JSON.
LLM_REASONING_EFFORT = os.environ.get("LLM_REASONING_EFFORT") or None
# Ollama's context window. Its default (4096) silently drops the start of longer prompts:
# measured, a 13.9k-token prompt at num_ctx=2048 was read as 1027 tokens, with no error.
LLM_NUM_CTX = int(os.environ.get("LLM_NUM_CTX") or 0) or None
PROMPT_SHARE = 0.75  # of the window; the rest is for the reply and tokenizer differences
# Free tiers limit tokens per minute (Groq: 8000), and LiteLLM's own retries come back
# before the window frees up. On a 429 we wait as long as the provider asks, up to this.
RATE_LIMIT_BUDGET = 180  # seconds of waiting per call before giving up
RETRY_IN = re.compile(r"try again in (?:(\d+)m)?([\d.]+)s")
# Free tiers also cap tokens per day (Groq: 200k), mostly spent re-running the same evals.
LLM_CACHE_DIR = os.environ.get("LLM_CACHE_DIR") or None
SCHEMA_RETRIES = 1  # network errors are retried by LiteLLM itself (num_retries)

T = TypeVar("T", bound=BaseModel)
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


class SchemaError(RuntimeError):
    """The model did not produce a reply matching the schema."""


class PromptTooLong(RuntimeError):
    """The prompt would not fit the model's context window and would be cut silently."""


class StructuredLLM(Protocol):
    """What the agent depends on: the real LLM below, or a fake in tests."""

    def ask(self, system: str, user: str, schema: type[T]) -> T: ...


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    rate_limit_wait: float = 0.0  # seconds spent waiting for the provider's rate limit
    cache_hits: int = 0  # replies read from LLM_CACHE_DIR instead of the API


def with_schema(system: str, schema: type[BaseModel]) -> str:
    """The system prompt plus the schema, field descriptions included.

    JSON mode only constrains which tokens the model may produce: Ollama never
    shows the schema to the model, so without this the field descriptions are
    invisible (measured: the facts eval sent the same 6859 prompt tokens before
    and after a description change, and scored the same).
    """
    fields = json.dumps(schema.model_json_schema())
    return f"{system}\n\nReply with JSON matching this schema:\n{fields}"


def retry_after(error: Exception) -> float:
    """Seconds the provider asked us to wait ("try again in 1m2.5s"), plus a margin."""
    match = RETRY_IN.search(str(error))
    if not match:
        return 10.0
    minutes, seconds = match.groups()
    return int(minutes or 0) * 60 + float(seconds) + 0.5


def strip_fences(text: str) -> str:
    """Some models wrap JSON in ```json fences even in JSON mode."""
    return FENCE.sub("", text.strip())


class LLM:
    def __init__(
        self,
        model: str = LLM_MODEL,
        fallbacks: list[str] | None = None,
        reasoning_effort: str | None = LLM_REASONING_EFFORT,
        num_ctx: int | None = LLM_NUM_CTX,
        count_tokens: Callable = litellm.token_counter,
        sleep: Callable[[float], None] = time.sleep,
        completion: Callable = litellm.completion,
        num_retries: int = 2,
        timeout: float = 300,  # local models on a laptop: a long prompt can take 2-3 minutes
        cache_dir: str | Path | None = LLM_CACHE_DIR,
    ):
        self.model = model
        self.fallbacks = LLM_FALLBACKS if fallbacks is None else fallbacks
        self.reasoning_effort = reasoning_effort
        self.num_ctx = num_ctx
        self.count_tokens = count_tokens
        self.sleep = sleep
        self.completion = completion
        self.num_retries = num_retries
        self.timeout = timeout
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.usage = Usage()

    def ask(self, system: str, user: str, schema: type[T]) -> T:
        """One structured answer: the reply parsed into `schema`."""
        messages = [
            {"role": "system", "content": with_schema(system, schema)},
            {"role": "user", "content": user},
        ]
        cached = self.cache_path(messages, schema)
        if cached and cached.exists():
            self.usage.cache_hits += 1
            return schema.model_validate_json(cached.read_text(encoding="utf-8"))
        for _ in range(SCHEMA_RETRIES + 1):
            content = self.complete(messages, schema)
            try:
                reply = schema.model_validate_json(strip_fences(content))
            except ValidationError as error:
                last_error = error
                messages += [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": f"That reply does not match the schema:\n{error}\n"
                        "Reply again with the corrected JSON only.",
                    },
                ]
                continue
            if cached:  # only replies that passed the schema, so a bad one never sticks
                cached.parent.mkdir(parents=True, exist_ok=True)
                temporary = cached.with_suffix(".tmp")
                temporary.write_text(reply.model_dump_json(), encoding="utf-8")
                temporary.replace(cached)  # atomic: a crash never leaves half a file
            return reply
        raise SchemaError(
            f"{schema.__name__}: no valid reply after {SCHEMA_RETRIES + 1} attempts"
        ) from last_error

    def cache_path(self, messages: list[dict], schema: type[BaseModel]) -> Path | None:
        """The file for this exact request, or None when caching is off."""
        if not self.cache_dir:
            return None
        request = {
            "model": self.model,
            "messages": messages,
            "schema": schema.model_json_schema(),
            "reasoning_effort": self.reasoning_effort,
            "num_ctx": self.num_ctx,
        }
        key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        return self.cache_dir / f"{key}.json"

    def complete(self, messages: list[dict], schema: type[BaseModel]) -> str:
        options = {}
        if self.num_ctx and self.model.startswith("ollama"):
            tokens = self.count_tokens(model=self.model, messages=messages)
            if tokens > self.num_ctx * PROMPT_SHARE:
                raise PromptTooLong(
                    f"about {tokens} prompt tokens for a {self.num_ctx}-token window: "
                    "raise LLM_NUM_CTX or send less text"
                )
            options["num_ctx"] = self.num_ctx
        if self.fallbacks:
            options["fallbacks"] = self.fallbacks
        if self.reasoning_effort:
            options["reasoning_effort"] = self.reasoning_effort
        waited = 0.0
        while True:
            try:
                response = self.completion(
                    model=self.model,
                    messages=messages,
                    response_format=schema,
                    temperature=0,  # same input, (nearly) same verdict
                    num_retries=self.num_retries,
                    timeout=self.timeout,
                    **options,
                )
                break
            except litellm.RateLimitError as error:
                wait = retry_after(error)
                if waited + wait > RATE_LIMIT_BUDGET:
                    raise
                self.usage.rate_limit_wait += wait
                waited += wait
                self.sleep(wait)
        self.usage.calls += 1
        self.usage.prompt_tokens += response.usage.prompt_tokens
        self.usage.completion_tokens += response.usage.completion_tokens
        return response.choices[0].message.content or ""
