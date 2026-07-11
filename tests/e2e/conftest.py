import os
import socket
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")

from config import Config  # noqa: E402


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server_url(tmp_path_factory):
    """Runs the real Flask app (not the test client) against a scratch,
    file-based SQLite db, so Playwright drives an actual browser over real
    HTTP — the same code path a real user hits, including CSRF tokens and
    real cookies. File-based (not :memory:) because the dev server thread
    can service multiple connections; an in-memory db would silently
    become "empty" on any connection that isn't the first one."""
    from app import create_app

    instance_dir = tmp_path_factory.mktemp("e2e-instance")

    class E2EConfig(Config):
        TESTING = True
        INSTANCE_DIR = instance_dir
        UPLOAD_DIR = instance_dir / "uploads"
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(instance_dir / "e2e.db")
        WTF_CSRF_ENABLED = True  # exercise the real CSRF flow through the browser
        RATELIMIT_ENABLED = False  # avoid flaky 429s across a whole test session

    app = create_app(E2EConfig)
    port = _free_port()

    server_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, use_reloader=False, threaded=True),
        daemon=True,
    )
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError("E2E server did not start in time")

    yield base_url, app


@pytest.fixture(scope="session")
def base_url(live_server_url):
    return live_server_url[0]


@pytest.fixture(scope="session")
def e2e_app(live_server_url):
    return live_server_url[1]


@pytest.fixture()
def browser_context_args(browser_context_args):
    # Every test gets its own fresh browser context (pytest-playwright's
    # default), so cookies never leak between tests even though the server
    # (and its database) is shared for the whole session.
    return {**browser_context_args, "ignore_https_errors": True}
