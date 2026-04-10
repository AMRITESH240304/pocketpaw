"""Auth domain — re-exports for backward compatibility."""

from ee.cloud.auth.core import (  # noqa: F401
    current_active_user,
    current_optional_user,
    fastapi_users,
    get_jwt_strategy,
    get_user_manager,
    get_user_db,
    cookie_backend,
    bearer_backend,
    UserRead,
    UserCreate,
    UserManager,
    seed_admin,
    seed_workspace,
    SECRET,
    TOKEN_LIFETIME,
)
from ee.cloud.auth.router import router  # noqa: F401
