"""Central configuration, read once from environment variables (and an optional .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

# provider -> (OpenAI-compatible base URL, default model, API-key env var)
# Every provider below speaks the OpenAI "chat completions + tool calling" protocol,
# so one client class covers all of them. Models change often: override with LLM_MODEL.
PROVIDER_PRESETS: dict[str, tuple[str, str, str]] = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.5-flash", "GEMINI_API_KEY"),
    "openai": ("https://api.openai.com/v1/", "gpt-4o-mini", "OPENAI_API_KEY"),
    # GPT-OSS 20B is available on Groq's developer tier and supports tool calling.
    # Llama 3.3 70B was retired for developer-tier accounts in August 2026.
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-20b", "GROQ_API_KEY"),
    "anthropic": ("https://api.anthropic.com/v1/", "claude-sonnet-4-6", "ANTHROPIC_API_KEY"),
    "ollama": ("http://localhost:11434/v1", "llama3.1", "OLLAMA_API_KEY"),
}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_temperature: float | None
    llm_timeout_s: int
    max_upload_mb: int
    max_files_per_session: int
    max_rows_per_file: int
    session_ttl_minutes: int
    max_agent_steps: int
    sql_row_limit: int
    sql_timeout_s: int
    history_turns: int
    log_level: str
    app_username: str
    app_password: str
    auth_enabled: bool
    allow_signup: bool
    auth_cookie_secure: bool
    auth_db_path: Path
    session_secret: str
    sample_dir: Path
    static_dir: Path

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        base_url, model, key_env = PROVIDER_PRESETS.get(provider, PROVIDER_PRESETS["openai"])
        api_key = os.getenv("LLM_API_KEY") or os.getenv(key_env, "")
        if provider == "ollama" and not api_key:
            api_key = "ollama"  # Ollama ignores the key but the SDK requires one
        temp = os.getenv("LLM_TEMPERATURE")
        return cls(
            llm_provider=provider,
            llm_api_key=api_key,
            llm_base_url=os.getenv("LLM_BASE_URL", base_url),
            llm_model=os.getenv("LLM_MODEL", model),
            llm_temperature=float(temp) if temp else None,
            llm_timeout_s=_int("LLM_TIMEOUT_S", 90),
            max_upload_mb=_int("MAX_UPLOAD_MB", 25),
            max_files_per_session=_int("MAX_FILES_PER_SESSION", 10),
            max_rows_per_file=_int("MAX_ROWS_PER_FILE", 1_000_000),
            session_ttl_minutes=_int("SESSION_TTL_MINUTES", 120),
            max_agent_steps=_int("MAX_AGENT_STEPS", 2),
            sql_row_limit=_int("SQL_ROW_LIMIT", 500),
            sql_timeout_s=_int("SQL_TIMEOUT_S", 10),
            history_turns=_int("HISTORY_TURNS", 10),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            app_username=os.getenv("APP_USERNAME", ""),
            app_password=os.getenv("APP_PASSWORD", ""),
            auth_enabled=os.getenv("AUTH_ENABLED", "false").lower() in {"1", "true", "yes"},
            allow_signup=os.getenv("ALLOW_SIGNUP", "false").lower() in {"1", "true", "yes"},
            auth_cookie_secure=os.getenv("AUTH_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"},
            auth_db_path=Path(os.getenv("AUTH_DB_PATH", BASE_DIR / "data" / "auth.db")),
            session_secret=os.getenv("SESSION_SECRET", os.urandom(32).hex()),
            sample_dir=Path(os.getenv("SAMPLE_DIR", BASE_DIR / "data" / "sample")),
            static_dir=BASE_DIR / "static",
        )
