import os
import sys
import tempfile
from pathlib import Path

# Set these before the app is imported. The app reads them at import time, and load_dotenv()
# does not override variables that are already set. Empty values keep tests away from the
# real Anthropic API and real email, even when .env has real credentials.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DB_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="comeback-test-"), "test.db"
)
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["SMTP_USER"] = ""
os.environ["SMTP_PASS"] = ""
os.environ["COOKIE_SECURE"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402


@pytest.fixture(autouse=True)
def clear_rate_limits():
    main.HITS.clear()
    yield
    main.HITS.clear()


@pytest.fixture
def client():
    return TestClient(main.app, follow_redirects=False)


@pytest.fixture
def logged_in(client):
    """A client with a fresh registered account. Returns the client."""
    import uuid

    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/register",
        data={"email": email, "password": "longpass1", "confirm": "longpass1"},
    )
    return client
