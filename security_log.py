import logging

from config import Config

security_logger = logging.getLogger("jtead.security")
security_logger.setLevel(logging.INFO)

if not security_logger.handlers:
    Config.INSTANCE_DIR.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(Config.INSTANCE_DIR / "security.log")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    security_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("[security] %(message)s"))
    security_logger.addHandler(console_handler)

    security_logger.propagate = False
