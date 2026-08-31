"""
Single abstraction point for talking to an LLM.

Every other module in this project calls `get_llm_client(role=...).generate(...)`
or `.generate_json(...)` — never an HTTP library directly. That means switching
from local Ollama to a hosted Groq endpoint (or anything else) later is a
change in this one file, not a rewrite of the pipeline.

Two roles exist, each bound to a different model:
    'worker'    -> fast/cheap model for extraction, summarization,
                   classification, simple drafting
    'reasoning' -> stronger model for business reasoning, design,
                   proposal/outreach writing quality

Clients are cached per role so repeated calls reuse the same instance. Under
12GB RAM both local models can coexist, but only the roles actually used in a
run are ever loaded (Ollama loads a model on first request).

Future option: OpenVINO as an alternative local backend for CPU-optimized
inference. Not implemented here — this file targets Ollama only.

Usage:
    from llm.client import get_llm_client
    llm = get_llm_client(role="worker")
    text = llm.generate("Say hello")
    data = llm.generate_json("Return JSON with a 'greeting' key")
"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Literal

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings

logger = logging.getLogger(__name__)

Role = Literal["worker", "reasoning"]

WORKER_ONLY_WARNING = (
    "Running in worker-only mode — reasoning-tier tasks will use the smaller "
    "model; quality may be lower for problem detection, solution design, and "
    "proposal writing"
)


class LLMClient(ABC):
    @abstractmethod
    def generate(self, prompt: str, system: str | None = None) -> str:
        """Return raw text completion for a prompt."""

    def generate_json(self, prompt: str, system: str | None = None) -> dict[str, Any]:
        """
        Generate a completion and parse it as JSON. Appends an instruction
        to the prompt nudging the model to return only JSON, then strips
        markdown code fences if the model wraps its answer in them anyway
        (small Llama models do this often).
        """
        json_instruction = (
            "\n\nRespond with ONLY valid JSON. No preamble, no explanation, "
            "no markdown code fences — just the raw JSON object."
        )
        raw = self.generate(prompt + json_instruction, system=system)
        return _extract_json(raw)


class OllamaClient(LLMClient):
    """Local Llama model served by Ollama (https://ollama.com)."""

    def __init__(self, host: str | None = None, model: str | None = None, keep_alive: str | None = None):
        self.host = (host or settings.OLLAMA_HOST).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        # Ollama's native control for how long the model stays resident after
        # a call. Conservative default (settings.OLLAMA_KEEP_ALIVE) so idle
        # models release memory instead of lingering on a 12GB machine.
        self.keep_alive = keep_alive or settings.OLLAMA_KEEP_ALIVE

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
    def generate(self, prompt: str, system: str | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
        }
        if system:
            payload["system"] = system

        try:
            resp = requests.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=120,
            )
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {self.host}. Is it running? "
                f"Try `ollama serve` and `ollama pull {self.model}`."
            ) from exc

        if resp.status_code >= 400:
            # Ollama returns {"error": "..."} with, e.g., 404 when a model
            # isn't pulled. Surface that instead of a bare HTTP error so a
            # wrong model tag is immediately diagnosable in the log.
            detail = ""
            try:
                detail = (resp.json().get("error") or "").strip()
            except ValueError:
                detail = resp.text[:300].strip()
            suffix = detail and f" {detail}"
            hint = f" Is it pulled? Try `ollama pull {self.model}`." if resp.status_code == 404 else ""
            raise RuntimeError(
                f"Ollama at {self.host} rejected model {self.model!r} "
                f"(HTTP {resp.status_code}):{suffix}{hint}"
            )

        data = resp.json()
        return data.get("response", "")

    def unload(self) -> None:
        """Immediately releases this model from memory via keep_alive=0.

        Use when you know this role won't be needed again soon (e.g. after a
        reasoning-heavy proposal phase finishes, before worker-only response
        classification) to free RAM for the next role.
        """
        try:
            requests.post(
                f"{self.host}/api/generate",
                json={"model": self.model, "keep_alive": 0},
                timeout=30,
            )
        except requests.RequestException:
            logger.warning("Could not unload %s from Ollama memory", self.model)


class GroqClient(LLMClient):
    """Hosted Llama models via Groq's OpenAI-compatible API."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.GROQ_API_KEY
        self.model = model or settings.GROQ_MODEL
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY is not set in .env")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
    def generate(self, prompt: str, system: str | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": messages, "temperature": 0.2},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _extract_json(raw: str) -> dict[str, Any]:
    """
    Small Llama models frequently wrap JSON in ```json fences or add a
    sentence before/after it. Try a straight parse first, then fall back to
    extracting the first {...} block.
    """
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from LLM output: %s", raw[:300])
    return {}


# Cache of clients keyed by effective role. Only the roles actually used in a
# run get a client (and therefore a loaded model), so worker-only runs never
# touch the reasoning model.
_clients: dict[Role, LLMClient] = {}

_worker_only_warned = False


def _effective_role(role: Role) -> Role:
    """Map the requested role to the one to actually instantiate.

    When REASONING_MODEL_ENABLED=false, reasoning-tier call sites fall back
    to the worker model so the 7B model needn't be pulled at all. Centralized
    here so individual call sites don't need to know about the flag.
    """
    if role == "reasoning" and not settings.REASONING_MODEL_ENABLED:
        return "worker"
    return role


def get_llm_client(role: Role = "reasoning") -> LLMClient:
    """Factory: returns a client bound to the model configured for this role.

    'worker'    -> fast/cheap model for extraction, summarization,
                   classification, simple drafting
    'reasoning' -> stronger model for business reasoning, design,
                   proposal/outreach writing quality

    Cached per role so repeated calls reuse the same client instance. When
    REASONING_MODEL_ENABLED=false, every 'reasoning' request resolves to the
    worker model instead.
    """
    global _worker_only_warned
    effective = _effective_role(role)

    if effective in _clients:
        logger.debug("get_llm_client role=%s -> model=%s (cached)", role, settings.model_for_role(effective))
        return _clients[effective]

    if not settings.REASONING_MODEL_ENABLED and not _worker_only_warned:
        _worker_only_warned = True
        logger.warning(WORKER_ONLY_WARNING)

    settings.validate_for_llm()
    model = settings.model_for_role(effective)

    if settings.LLM_PROVIDER == "ollama":
        client: LLMClient = OllamaClient(model=model)
    elif settings.LLM_PROVIDER == "groq":
        client = GroqClient(model=model)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")

    _clients[effective] = client
    logger.debug("get_llm_client role=%s -> model=%s", role, model)
    return client
