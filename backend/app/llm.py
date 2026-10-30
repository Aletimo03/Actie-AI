"""LLM layer: one call shape for every provider, through LiteLLM.

Every agent step asks for a reply that fits a Pydantic schema. The provider's
JSON-schema mode constrains the reply and Pydantic validates it here. A reply
that still doesn't validate is sent back once together with the validation
error; a second failure raises SchemaError, so a node never sees half-parsed
output.

The model is a LiteLLM string read from the environment, so moving from the
local Ollama to Groq is a .env change, not a code change:
    LLM_MODEL=ollama_chat/gemma4:12b     (development, local)
    LLM_MODEL=groq/<model>               (live site, see docs on the provider choice)
"""

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
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


def with_schema(system: str, schema: type[BaseModel]) -> str:
    """The system prompt plus the schema, field descriptions included.

    JSON mode only constrains which tokens the model may produce: Ollama never
    shows the schema to the model, so without this the field descriptions are
    invisible (measured: the facts eval sent the same 6859 prompt tokens before
    and after a description change, and scored the same).
    """
    fields = json.dumps(schema.model_json_schema())
    return f"{system}\n\nReply with JSON matching this schema:\n{fields}"


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
        completion: Callable = litellm.completion,
        num_retries: int = 2,
        timeout: float = 300,  # local models on a laptop: a long prompt can take 2-3 minutes
    ):
        self.model = model
        self.fallbacks = LLM_FALLBACKS if fallbacks is None else fallbacks
        self.reasoning_effort = reasoning_effort
        self.num_ctx = num_ctx
        self.count_tokens = count_tokens
        self.completion = completion
        self.num_retries = num_retries
        self.timeout = timeout
        self.usage = Usage()

    def ask(self, system: str, user: str, schema: type[T]) -> T:
        """One structured answer: the reply parsed into `schema`."""
        messages = [
            {"role": "system", "content": with_schema(system, schema)},
            {"role": "user", "content": user},
        ]
        for _ in range(SCHEMA_RETRIES + 1):
            content = self.complete(messages, schema)
            try:
                return schema.model_validate_json(strip_fences(content))
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
        raise SchemaError(
            f"{schema.__name__}: no valid reply after {SCHEMA_RETRIES + 1} attempts"
        ) from last_error

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
        response = self.completion(
            model=self.model,
            messages=messages,
            response_format=schema,
            temperature=0,  # same input, (nearly) same verdict
            num_retries=self.num_retries,
            timeout=self.timeout,
            **options,
        )
        self.usage.calls += 1
        self.usage.prompt_tokens += response.usage.prompt_tokens
        self.usage.completion_tokens += response.usage.completion_tokens
        return response.choices[0].message.content or ""
