"""Runtime configuration, read once from environment variables."""
import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Tiny .env loader for local dev (real env vars win)."""
    p = Path(__file__).resolve().parent.parent / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.split("  #")[0].strip())


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    model: str = os.getenv("MODEL", "claude-haiku-5-5")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///shopbot.db")
    admin_token: str = os.getenv("ADMIN_TOKEN", "change-me")
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")
    max_message_chars: int = int(os.getenv("MAX_MESSAGE_CHARS", "1500"))
    history_window: int = int(os.getenv("HISTORY_WINDOW", "12"))
    max_output_tokens: int = int(os.getenv("MAX_OUTPUT_TOKENS", "450"))
    rate_limit_per_min: int = int(os.getenv("RATE_LIMIT_PER_MIN", "40"))
    # USD per million tokens, used only for the admin cost estimate.
    price_in_per_m: float = float(os.getenv("PRICE_IN_PER_M", "1.0"))
    price_out_per_m: float = float(os.getenv("PRICE_OUT_PER_M", "5.0"))


settings = Settings()
