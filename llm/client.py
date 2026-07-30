"""
Single abstraction point for talking to a Llama model.

Every other module in this project calls `get_llm_client().generate(...)` or
`.generate_json(...)` — never an HTTP library directly. That means switching
from local Ollama to a hosted Groq endpoint (or anything else) later is a
change in this one file, not a rewrite of the pipeline.

Usage:
    from llm.client import get_llm_client
    llm = get_llm_client()
    text = llm.generate("Say hello")
    data = llm.generate_json("Return JSON with a 'greeting' key")
"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings

logger = logging.getLogger(__name__)


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

    def __init__(self, host: str | None = None, model: str | None = None):
        self.host = (host or settings.OLLAMA_HOST).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
    def generate(self, prompt: str, system: str | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        try:
            resp = requests.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {self.host}. Is it running? "
                f"Try `ollama serve` and `ollama pull {self.model}`."
            ) from exc

        data = resp.json()
        return data.get("response", "")


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


_client_singleton: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Factory: returns the configured LLM client based on settings.LLM_PROVIDER."""
    global _client_singleton
    if _client_singleton is not None:
        return _client_singleton

    settings.validate_for_llm()
    if settings.LLM_PROVIDER == "ollama":
        _client_singleton = OllamaClient()
    elif settings.LLM_PROVIDER == "groq":
        _client_singleton = GroqClient()
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")

    return _client_singleton
