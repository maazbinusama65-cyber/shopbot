"""Vercel entrypoint (auto-detected). Exposes the ASGI app; schema/seed run at import in app.main."""
from app.main import app  # noqa: F401
