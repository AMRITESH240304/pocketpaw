# Settings router — GET/PUT settings (REST alternative to WS-only).
# Created: 2026-02-20

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from pocketpaw.api.deps import require_scope

# Security-critical fields that MUST NOT be modified via the REST API.
# These fields control file-system boundaries, permission checks, prompt-injection
# scanning, and other safety guardrails.  They can only be changed by editing the
# config file or environment variables directly.
_IMMUTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "file_jail_path",
        "bypass_permissions",
        "trust_level",
        "injection_scan_enabled",
        "guardian_enabled",
        "localhost_auth_bypass",
        "pii_scan_enabled",
    }
)

# Explicit allowlist of settings fields safe to expose via GET /settings.
#
# Security-sensitive fields are intentionally excluded:
#   - file_jail_path          reveals the filesystem boundary (aids path traversal)
#   - tool_profile            reveals which tools are enabled (reveals security posture)
#   - tools_allow / tools_deny  same concern as tool_profile
#   - bypass_permissions      reveals whether permission checks are disabled
#   - localhost_auth_bypass   reveals whether unauthenticated localhost access is allowed
#   - a2a_trusted_agents      reveals trusted identifiers that receive elevated privileges
#   - injection_scan_*        reveals prompt-injection scanning configuration
#   - pii_scan_*              reveals PII-detection configuration
#   - session_token_ttl_hours auth-session configuration
#   - api_cors_allowed_origins CORS configuration
#   - api_rate_limit_per_key  rate-limiting configuration
#   - allowed_user_id         Telegram user allowlist (PII)
#   - *_allowed_*             all channel-specific allowlists (PII / security)
#   - status_api_key          a credential
#   - All fields in SECRET_FIELDS (API keys, bot tokens, OAuth secrets …)
#
# When adding new Settings fields, consciously decide whether they belong here.
_SAFE_SETTINGS_FIELDS: frozenset[str] = frozenset(
    {
        # Agent backend
        "agent_backend",
        "fallback_backends",
        # Claude SDK
        "claude_sdk_provider",
        "claude_sdk_model",
        "claude_sdk_max_turns",
        # OpenAI Agents
        "openai_agents_provider",
        "openai_agents_model",
        "openai_agents_max_turns",
        # Gemini CLI (legacy)
        "gemini_cli_model",
        "gemini_cli_max_turns",
        # Google ADK
        "google_adk_provider",
        "google_adk_model",
        "google_adk_max_turns",
        # Codex CLI
        "codex_cli_model",
        "codex_cli_max_turns",
        # Copilot SDK
        "copilot_sdk_provider",
        "copilot_sdk_model",
        "copilot_sdk_max_turns",
        # Deep Agents
        "deep_agents_model",
        "deep_agents_max_turns",
        # OpenCode
        "opencode_base_url",
        "opencode_model",
        "opencode_max_turns",
        # LiteLLM
        "litellm_api_base",
        "litellm_model",
        "litellm_max_tokens",
        # General LLM
        "llm_provider",
        "ollama_host",
        "ollama_model",
        "openai_compatible_base_url",
        "openai_compatible_model",
        "openai_compatible_max_tokens",
        "openrouter_model",
        "gemini_model",
        "openai_model",
        "anthropic_model",
        # Memory
        "memory_backend",
        "memory_use_inference",
        "vectordb_path",
        "mem0_llm_provider",
        "mem0_llm_model",
        "mem0_embedder_provider",
        "mem0_embedder_model",
        "mem0_vector_store",
        "mem0_ollama_base_url",
        "mem0_auto_learn",
        "file_auto_learn",
        "file_vector_enabled",
        "vector_store",
        "embedding_provider",
        "embedding_model",
        "embedding_base_url",
        # Session compaction
        "compaction_recent_window",
        "compaction_char_budget",
        "compaction_summary_chars",
        "compaction_llm_summarize",
        # Web search
        "web_search_provider",
        "url_extract_provider",
        # Image generation
        "image_model",
        # Smart model routing
        "smart_routing_enabled",
        "model_tier_simple",
        "model_tier_moderate",
        "model_tier_complex",
        # Plan mode
        "plan_mode",
        "plan_mode_tools",
        # Self-audit daemon
        "self_audit_enabled",
        "self_audit_schedule",
        # Health engine
        "health_check_on_startup",
        # User preferences
        "user_display_name",
        "user_avatar_emoji",
        "theme_preference",
        "notifications_enabled",
        "sound_enabled",
        "tool_notifications_enabled",
        "default_workspace_dir",
        # Web server
        "web_host",
        "web_port",
        # A2A public settings
        "a2a_enabled",
        "a2a_agent_name",
        "a2a_agent_description",
        "a2a_agent_version",
        "a2a_task_timeout",
        # Voice / TTS / STT
        "tts_provider",
        "tts_voice",
        "tts_default_voice_elevenlabs",
        "voice_reply_enabled",
        "stt_provider",
        "stt_model",
        # OCR
        "ocr_provider",
        # Sarvam AI (non-key fields)
        "sarvam_tts_model",
        "sarvam_tts_speaker",
        "sarvam_tts_language",
        "sarvam_stt_model",
        # Discord display / behaviour (no allowlists)
        "discord_bot_name",
        "discord_status_type",
        "discord_activity_type",
        "discord_activity_text",
        "discord_conversation_all_channels",
        # WhatsApp mode (no tokens or phone numbers)
        "whatsapp_mode",
        # Webhook
        "webhook_sync_timeout",
        # MCP
        "mcp_client_metadata_url",
        # Identity / multi-user
        "owner_id",
        # Soul protocol
        "soul_enabled",
        "soul_name",
        "soul_archetype",
        "soul_persona",
        "soul_values",
        "soul_ocean",
        "soul_communication",
        "soul_path",
        "soul_auto_save_interval",
        "soul_biorhythm",
        # Notifications
        "notification_channels",
        # Media
        "media_download_dir",
        "media_max_file_size_mb",
        # UX
        "welcome_hint_enabled",
        # Channel autostart (on/off flags only, not allowlists)
        "channel_autostart",
        # Concurrency
        "max_concurrent_conversations",
    }
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Settings"])

# Protects settings read-modify-write from concurrent clients
_settings_lock = asyncio.Lock()


@router.get("/settings", dependencies=[Depends(require_scope("settings:read", "settings:write"))])
async def get_settings():
    """Return safe, non-security-sensitive settings fields.

    Only fields explicitly listed in ``_SAFE_SETTINGS_FIELDS`` are included in
    the response.  Security-sensitive fields (filesystem boundaries, permission
    flags, tool allowlists, injection-scan config, etc.) are intentionally
    omitted to prevent information disclosure (OWASP A01).
    """
    from pathlib import Path

    from pocketpaw.config import Settings

    settings = Settings.load()
    data = {}
    for field_name in _SAFE_SETTINGS_FIELDS:
        val = getattr(settings, field_name, None)
        if isinstance(val, Path):
            val = str(val)
        data[field_name] = val
    return data


@router.put("/settings", dependencies=[Depends(require_scope("settings:write"))])
async def update_settings(request: Request):
    """Update settings fields. Only provided fields are changed."""
    from pocketpaw.config import Settings, get_settings, validate_api_key

    data = await request.json()
    settings_data = data.get("settings", data)

    # Validate API keys — collect warnings but never block save
    warnings = []
    api_key_fields = [
        "anthropic_api_key",
        "openai_api_key",
        "telegram_bot_token",
    ]

    for field in api_key_fields:
        if field in settings_data:
            value = settings_data[field]
            if value:  # Only validate non-empty values
                is_valid, warning = validate_api_key(field, value)
                if not is_valid:
                    warnings.append(warning)

    # Block writes to security-critical fields
    blocked = _IMMUTABLE_FIELDS.intersection(settings_data)
    if blocked:
        raise HTTPException(
            status_code=403,
            detail=f"Field(s) {', '.join(sorted(blocked))} cannot be modified via the API",
        )

    async with _settings_lock:
        settings = Settings.load()
        for key, value in settings_data.items():
            if hasattr(settings, key) and not key.startswith("_"):
                setattr(settings, key, value)
        settings.save()
        get_settings.cache_clear()

    # Sync user_display_name into USER.md so the agent knows the user's name
    if "user_display_name" in settings_data and settings_data["user_display_name"]:
        try:
            from pocketpaw.config import get_config_dir

            user_file = get_config_dir() / "identity" / "USER.md"
            user_file.parent.mkdir(parents=True, exist_ok=True)
            import re as _re

            # Sanitize display name: strip newlines and limit to safe characters
            raw_name = settings_data["user_display_name"]
            display_name = _re.sub(r"[^\w\s\-.,'\u0080-\uffff]", "", raw_name).strip()[:100]
            if not display_name:
                display_name = "User"
            if user_file.exists():
                content = user_file.read_text(encoding="utf-8")
                import re

                updated = re.sub(
                    r"^Name:\s*.*$",
                    f"Name: {display_name}",
                    content,
                    count=1,
                    flags=re.MULTILINE,
                )
                if updated == content and "Name:" not in content:
                    # No Name: line found, prepend it
                    updated = f"# User Profile\nName: {display_name}\n\n{content}"
                user_file.write_text(updated, encoding="utf-8")
            else:
                user_file.write_text(
                    f"# User Profile\nName: {display_name}\n",
                    encoding="utf-8",
                )
            # Invalidate the identity file cache so changes are picked up immediately
            from pocketpaw.bootstrap.default_provider import _identity_file_cache

            cache_key = str(user_file)
            _identity_file_cache.pop(cache_key, None)
            logger.info("Synced user_display_name '%s' to USER.md", display_name)
        except Exception:
            logger.debug("Could not sync user_display_name to USER.md", exc_info=True)

    # Apply runtime side-effects so changes take effect without restart
    try:
        from pocketpaw.dashboard_state import agent_loop

        agent_loop.reset_router()
        logger.info("Agent router reset after settings update")
    except Exception:
        logger.debug("Could not reset agent router", exc_info=True)

    try:
        from pocketpaw.memory import get_memory_manager

        manager = get_memory_manager()
        if hasattr(manager, "reload"):
            await manager.reload()
    except Exception:
        logger.debug("Could not reload memory manager", exc_info=True)

    result: dict = {"status": "ok"}
    if warnings:
        result["warnings"] = warnings
    return result
