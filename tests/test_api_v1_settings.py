# Tests for API v1 settings router.
# Created: 2026-02-20

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pocketpaw.api.v1.settings import _IMMUTABLE_FIELDS, _SAFE_SETTINGS_FIELDS, router


@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


class TestGetSettings:
    """Tests for GET /api/v1/settings."""

    @patch("pocketpaw.config.Settings.load")
    def test_get_settings_returns_dict(self, mock_load, client):
        settings = MagicMock()
        settings.agent_backend = "claude_agent_sdk"
        settings.web_port = 8888
        mock_load.return_value = settings
        resp = client.get("/api/v1/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_backend"] == "claude_agent_sdk"
        assert data["web_port"] == 8888

    @patch("pocketpaw.config.Settings.load")
    def test_get_settings_excludes_security_fields(self, mock_load, client):
        """Security-sensitive fields must not appear in the GET /settings response."""
        settings = MagicMock()
        # Give each sensitive field a non-None value to confirm it isn't leaked.
        settings.file_jail_path = "/home/user"
        settings.tool_profile = "full"
        settings.bypass_permissions = True
        settings.localhost_auth_bypass = True
        settings.a2a_trusted_agents = ["http://evil.example.com"]
        settings.injection_scan_enabled = True
        settings.pii_scan_enabled = False
        settings.tools_allow = ["shell"]
        settings.tools_deny = []
        settings.session_token_ttl_hours = 24
        settings.api_cors_allowed_origins = ["*"]
        settings.api_rate_limit_per_key = 60
        mock_load.return_value = settings
        resp = client.get("/api/v1/settings")
        assert resp.status_code == 200
        data = resp.json()
        security_fields = {
            "file_jail_path",
            "tool_profile",
            "bypass_permissions",
            "localhost_auth_bypass",
            "a2a_trusted_agents",
            "injection_scan_enabled",
            "injection_scan_llm",
            "injection_scan_llm_model",
            "pii_scan_enabled",
            "pii_default_action",
            "pii_type_actions",
            "pii_scan_memory",
            "pii_scan_audit",
            "pii_scan_logs",
            "tools_allow",
            "tools_deny",
            "session_token_ttl_hours",
            "api_cors_allowed_origins",
            "api_rate_limit_per_key",
        }
        for field in security_fields:
            assert field not in data, f"Security field '{field}' must not appear in GET /settings"

    @patch("pocketpaw.config.Settings.load")
    def test_get_settings_excludes_secret_fields(self, mock_load, client):
        """API keys and tokens must not appear in the GET /settings response."""
        settings = MagicMock()
        mock_load.return_value = settings
        resp = client.get("/api/v1/settings")
        assert resp.status_code == 200
        data = resp.json()
        credential_fields = {
            "anthropic_api_key",
            "openai_api_key",
            "telegram_bot_token",
            "discord_bot_token",
            "slack_bot_token",
            "slack_app_token",
            "whatsapp_access_token",
            "whatsapp_verify_token",
            "tavily_api_key",
            "google_api_key",
            "google_oauth_client_secret",
        }
        for field in credential_fields:
            assert field not in data, f"Credential field '{field}' must not appear in GET /settings"

    @patch("pocketpaw.config.Settings.load")
    def test_get_settings_excludes_channel_allowlists(self, mock_load, client):
        """Channel allowlists (phone numbers, guild IDs, user IDs) must not be exposed."""
        settings = MagicMock()
        mock_load.return_value = settings
        resp = client.get("/api/v1/settings")
        assert resp.status_code == 200
        data = resp.json()
        allowlist_fields = {
            "allowed_user_id",
            "discord_allowed_guild_ids",
            "discord_allowed_user_ids",
            "discord_allowed_channel_ids",
            "slack_allowed_channel_ids",
            "whatsapp_allowed_phone_numbers",
        }
        for field in allowlist_fields:
            assert field not in data, f"Allowlist field '{field}' must not appear in GET /settings"

    def test_safe_settings_fields_allowlist_is_explicit(self):
        """_SAFE_SETTINGS_FIELDS must be a nonempty frozenset of strings."""
        assert isinstance(_SAFE_SETTINGS_FIELDS, frozenset)
        assert len(_SAFE_SETTINGS_FIELDS) > 0
        assert all(isinstance(f, str) for f in _SAFE_SETTINGS_FIELDS)

    def test_immutable_fields_not_in_safe_allowlist(self):
        """Every immutable (security-critical) field must be absent from the safe allowlist."""
        overlap = _IMMUTABLE_FIELDS & _SAFE_SETTINGS_FIELDS
        assert not overlap, f"Immutable security fields found in _SAFE_SETTINGS_FIELDS: {overlap}"


class TestUpdateSettings:
    """Tests for PUT /api/v1/settings."""

    @patch("pocketpaw.config.get_settings")
    @patch("pocketpaw.config.Settings.load")
    def test_update_settings(self, mock_load, mock_get_settings, client):
        settings = MagicMock()
        settings.agent_backend = "claude_agent_sdk"
        mock_load.return_value = settings
        resp = client.put(
            "/api/v1/settings",
            json={"settings": {"agent_backend": "openai_agents"}},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        # Verify setattr was called
        assert settings.agent_backend == "openai_agents"
        settings.save.assert_called_once()

    @patch("pocketpaw.config.get_settings")
    @patch("pocketpaw.config.Settings.load")
    def test_update_ignores_private_fields(self, mock_load, mock_get_settings, client):
        settings = MagicMock()
        # hasattr returns True for MagicMock, but the router checks startswith("_")
        mock_load.return_value = settings
        resp = client.put(
            "/api/v1/settings",
            json={"settings": {"_internal": "secret", "agent_backend": "openai_agents"}},
        )
        assert resp.status_code == 200
        # agent_backend should be set, _internal should not
        assert settings.agent_backend == "openai_agents"

    @pytest.mark.parametrize("field", sorted(_IMMUTABLE_FIELDS))
    def test_rejects_immutable_field(self, field, client):
        """PUT /settings must return 403 for every security-critical field."""
        resp = client.put(
            "/api/v1/settings",
            json={"settings": {field: "evil"}},
        )
        assert resp.status_code == 403
        assert field in resp.json()["detail"]

    def test_rejects_multiple_immutable_fields(self, client):
        """All blocked field names appear in the error when several are sent at once."""
        payload = {"file_jail_path": "/", "bypass_permissions": True}
        resp = client.put("/api/v1/settings", json={"settings": payload})
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert "bypass_permissions" in detail
        assert "file_jail_path" in detail

    @patch("pocketpaw.config.get_settings")
    @patch("pocketpaw.config.Settings.load")
    def test_safe_field_still_accepted(self, mock_load, mock_get_settings, client):
        """Non-blocked fields are still written normally."""
        settings = MagicMock()
        settings.agent_backend = "claude_agent_sdk"
        mock_load.return_value = settings
        resp = client.put(
            "/api/v1/settings",
            json={"settings": {"agent_backend": "openai_agents"}},
        )
        assert resp.status_code == 200
        assert settings.agent_backend == "openai_agents"
