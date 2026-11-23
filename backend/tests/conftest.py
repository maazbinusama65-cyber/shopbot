import os
import tempfile

# Must be set before `app` is imported: each test session gets a fresh SQLite file.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["ADMIN_TOKEN"] = "test-admin"
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

import pytest  # noqa: E402

from app.seed import seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _seed():
    seed()
