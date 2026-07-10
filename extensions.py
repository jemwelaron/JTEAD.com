from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_wtf import CSRFProtect

csrf = CSRFProtect()
limiter = Limiter(get_remote_address, default_limits=[])
login_manager = LoginManager()
