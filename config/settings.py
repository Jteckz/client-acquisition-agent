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


class Settings:
    # --- LLM provider ---
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama").lower()

    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

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

    def validate_for_llm(self) -> None:
        if self.LLM_PROVIDER == "groq" and not self.GROQ_API_KEY:
            raise RuntimeError("LLM_PROVIDER=groq but GROQ_API_KEY is missing in .env.")


settings = Settings()
