# Backward compat — delegates to shared/db.py
from ee.cloud.shared.db import init_cloud_db, close_cloud_db, get_client  # noqa: F401
