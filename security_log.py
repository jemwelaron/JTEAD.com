import logging
import os
from pathlib import Path

from config import Config

security_logger = logging.getLogger("jtead.security")
security_logger.setLevel(logging.INFO)

if not security_logger.handlers:
    # SECURITY_LOG_DIR lets the test suite redirect this away from the real
    # instance directory (this is a module-level singleton, so per-test app
    # config can't reach it — conftest.py sets the env var once, before
    # anything imports this module).
    log_dir = Path(os.environ.get("SECURITY_LOG_DIR") or Config.INSTANCE_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "security.log")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    security_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("[security] %(message)s"))
    security_logger.addHandler(console_handler)

    security_logger.propagate = False
