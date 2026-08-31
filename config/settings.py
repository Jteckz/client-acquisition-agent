"""
Central configuration for the client acquisition agent.

Everything that varies between machines / environments (API keys, model
choice, file paths) lives here and nowhere else. Every other module should
import `settings` from this file rather than reading os.environ directly.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _first_set_env(*names: str, default: str) -> str:
    """Return the first env var in `names` that is set and non-empty.

    Used for role->model resolution so that a deployment that only defines
    the legacy single-model var (OLLAMA_MODEL / GROQ_MODEL) still works: the
    new role-specific vars win when set, otherwise the legacy var is used,
    otherwise the built-in default applies.
    """
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


class Settings:
    # --- LLM provider ---
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama").lower()

    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    # Legacy single-model setting. Kept for backward compatibility: when the
    # role-specific vars below are unset, BOTH roles resolve to this model so
    # an existing single-model deployment upgrades without breaking.
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

    # Role -> model mapping (dual-model setup). Worker is the fast/cheap
    # model (extraction, summarization, classification); reasoning is the
    # stronger model (business reasoning, design, proposal/outreach writing).
    OLLAMA_WORKER_MODEL: str = _first_set_env(
        "OLLAMA_WORKER_MODEL", "OLLAMA_MODEL", default="qwen2.5:3b-instruct"
    )
    OLLAMA_REASONING_MODEL: str = _first_set_env(
        "OLLAMA_REASONING_MODEL", "OLLAMA_MODEL", default="qwen2.5:7b-instruct"
    )
    # How long Ollama keeps a model resident after a call with no further
    # requests. Conservative default given 12GB RAM + HDD swap cost.
    OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "5m")

    # Phased rollout: when false, every reasoning-tier call site uses the
    # worker model instead, so the 7B model never needs to be pulled.
    REASONING_MODEL_ENABLED: bool = os.getenv("REASONING_MODEL_ENABLED", "true").lower() == "true"

    # Follow-up drafting escalates from the worker model to the reasoning
    # model when a lead's stored opportunity/qualification score exceeds this.
    FOLLOWUP_ESCALATION_SCORE: int = int(os.getenv("FOLLOWUP_ESCALATION_SCORE", "90"))

    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    # Hosted (Groq) role -> model mapping, for parity when LLM_PROVIDER=groq.
    GROQ_WORKER_MODEL: str = _first_set_env(
        "GROQ_WORKER_MODEL", "GROQ_MODEL", default="llama-3.1-8b-instant"
    )
    GROQ_REASONING_MODEL: str = _first_set_env(
        "GROQ_REASONING_MODEL", "GROQ_MODEL", default="llama-3.3-70b-versatile"
    )

    # --- Storage ---
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "leads.db"))

    # --- HTTP behaviour ---
    REQUEST_TIMEOUT_SECONDS: int = 15
    # Nominatim's usage policy requires a real identifying User-Agent —
    # replace the contact with your own before heavy use.
    USER_AGENT: str = os.getenv(
        "HTTP_USER_AGENT",
        "ClientAcquisitionAgent/0.1 (research bot; contact: you@example.com)",
    )

    # --- Discovery defaults (OpenStreetMap: no API key required) ---
    DEFAULT_SEARCH_RADIUS_METERS: int = 5000
    MAX_RESULTS_PER_SEARCH: int = 20

    # --- V2: Proposal engine ---
    MIN_QUALIFICATION_SCORE_FOR_PROPOSAL: int = int(os.getenv("MIN_QUALIFICATION_SCORE_FOR_PROPOSAL", "40"))
    PROPOSALS_OUTPUT_DIR: str = os.getenv("PROPOSALS_OUTPUT_DIR", str(PROJECT_ROOT / "data" / "proposals"))

    # --- V3: Outreach / CRM ---
    FOLLOWUP_AFTER_DAYS: int = int(os.getenv("FOLLOWUP_AFTER_DAYS", "7"))
    MIN_SAMPLE_SIZE_FOR_INSIGHTS: int = int(os.getenv("MIN_SAMPLE_SIZE_FOR_INSIGHTS", "5"))

    def validate_for_llm(self) -> None:
        if self.LLM_PROVIDER == "groq" and not self.GROQ_API_KEY:
            raise RuntimeError("LLM_PROVIDER=groq but GROQ_API_KEY is missing in .env.")

    def model_for_role(self, role: str) -> str:
        """Resolve the configured model name for a role.

        role is one of "worker" / "reasoning". Falls back to the legacy
        single-model setting when the role-specific vars are unset (see
        _first_set_env).
        """
        if self.LLM_PROVIDER == "groq":
            return (
                self.GROQ_WORKER_MODEL if role == "worker" else self.GROQ_REASONING_MODEL
            )
        return (
            self.OLLAMA_WORKER_MODEL if role == "worker" else self.OLLAMA_REASONING_MODEL
        )


settings = Settings()
