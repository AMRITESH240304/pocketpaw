"""MCP server that exposes Discord operations via discli.

Run as: python -m pocketpaw.mcp.discord_server

This is a stdio-based MCP server that wraps the discli CLI tool,
making Discord operations available to any MCP-capable agent backend
(claude_agent_sdk, codex_cli, google_adk, etc.).
"""

import asyncio
import json
import logging
import shlex
import shutil
import sys

logger = logging.getLogger(__name__)

# Tool definitions exposed via MCP
TOOLS = [
    {
        "name": "discord_send_message",
        "description": "Send a message to a Discord channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name with # (e.g. #general)"},
                "text": {"type": "string", "description": "Message text to send"},
            },
            "required": ["channel", "text"],
        },
    },
    {
        "name": "discord_dm",
        "description": "Send a direct message to a Discord user.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "Discord user ID"},
                "text": {"type": "string", "description": "Message text"},
            },
            "required": ["user_id", "text"],
        },
    },
    {
        "name": "discord_create_thread",
        "description": "Create a thread on a message in a channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name with #"},
                "message_id": {"type": "string", "description": "Message ID to attach thread to"},
                "title": {"type": "string", "description": "Thread title"},
            },
            "required": ["channel", "message_id", "title"],
        },
    },
    {
        "name": "discord_send_thread",
        "description": "Send a message in a thread.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "Thread ID"},
                "text": {"type": "string", "description": "Message text"},
            },
            "required": ["thread_id", "text"],
        },
    },
    {
        "name": "discord_create_poll",
        "description": "Create a poll in a Discord channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name with #"},
                "question": {"type": "string", "description": "Poll question"},
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Poll options (2-10)",
                },
                "multiple": {
                    "type": "boolean",
                    "description": "Allow multiple selections",
                    "default": False,
                },
            },
            "required": ["channel", "question", "options"],
        },
    },
    {
        "name": "discord_add_reaction",
        "description": "Add an emoji reaction to a message.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name with #"},
                "message_id": {"type": "string", "description": "Message ID"},
                "emoji": {"type": "string", "description": "Emoji to react with"},
            },
            "required": ["channel", "message_id", "emoji"],
        },
    },
    {
        "name": "discord_list_messages",
        "description": "List recent messages in a channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name with #"},
                "limit": {"type": "integer", "description": "Max messages", "default": 20},
            },
            "required": ["channel"],
        },
    },
    {
        "name": "discord_search_messages",
        "description": "Search messages in a channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name with #"},
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results", "default": 50},
            },
            "required": ["channel", "query"],
        },
    },
    {
        "name": "discord_list_channels",
        "description": "List channels in a server.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
            },
            "required": ["server"],
        },
    },
    {
        "name": "discord_member_info",
        "description": "Get info about a server member.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
                "username": {"type": "string", "description": "Username to look up"},
            },
            "required": ["server", "username"],
        },
    },
    {
        "name": "discord_list_members",
        "description": "List members of a server.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
                "limit": {"type": "integer", "description": "Max members", "default": 50},
            },
            "required": ["server"],
        },
    },
    {
        "name": "discord_role_list",
        "description": "List roles in a server.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
            },
            "required": ["server"],
        },
    },
    {
        "name": "discord_role_assign",
        "description": "Assign a role to a member.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
                "username": {"type": "string", "description": "Username"},
                "role": {"type": "string", "description": "Role name"},
            },
            "required": ["server", "username", "role"],
        },
    },
    {
        "name": "discord_server_info",
        "description": "Get information about a Discord server.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
            },
            "required": ["server"],
        },
    },
    {
        "name": "discord_send_embed",
        "description": "Send a message with a rich embed to a Discord channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name with # (e.g. #general)"},
                "text": {
                    "type": "string",
                    "description": "Message text (can be empty if embed-only)",
                    "default": "",
                },
                "embed_title": {"type": "string", "description": "Embed title"},
                "embed_desc": {"type": "string", "description": "Embed description"},
                "embed_color": {
                    "type": "string",
                    "description": "Hex color (e.g. ff0000)",
                    "default": "",
                },
                "embed_footer": {"type": "string", "description": "Footer text", "default": ""},
                "embed_image": {"type": "string", "description": "Image URL", "default": ""},
                "embed_thumbnail": {
                    "type": "string",
                    "description": "Thumbnail URL",
                    "default": "",
                },
            },
            "required": ["channel", "embed_title"],
        },
    },
    {
        "name": "discord_channel_edit",
        "description": "Edit a channel's name, topic, slowmode, or NSFW flag.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
                "channel": {"type": "string", "description": "Channel name with #"},
                "name": {"type": "string", "description": "New channel name", "default": ""},
                "topic": {"type": "string", "description": "New channel topic", "default": ""},
                "slowmode": {
                    "type": "integer",
                    "description": "Slowmode seconds (0 to disable)",
                    "default": -1,
                },
                "nsfw": {"type": "boolean", "description": "Set NSFW flag"},
            },
            "required": ["server", "channel"],
        },
    },
    {
        "name": "discord_channel_set_permissions",
        "description": "Set permission overwrites for a role or member on a channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
                "channel": {"type": "string", "description": "Channel name with #"},
                "target": {"type": "string", "description": "Role name or user ID"},
                "target_type": {
                    "type": "string",
                    "description": "'role' or 'member'",
                    "default": "role",
                },
                "allow": {"type": "string", "description": "Comma-separated permissions to allow"},
                "deny": {"type": "string", "description": "Comma-separated permissions to deny"},
            },
            "required": ["server", "channel", "target"],
        },
    },
    {
        "name": "discord_forum_post",
        "description": "Create a post in a forum channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
                "channel": {"type": "string", "description": "Forum channel name with #"},
                "title": {"type": "string", "description": "Post title"},
                "content": {"type": "string", "description": "Post content"},
            },
            "required": ["server", "channel", "title", "content"],
        },
    },
    {
        "name": "discord_thread_archive",
        "description": "Archive a thread.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "Thread ID"},
            },
            "required": ["thread_id"],
        },
    },
    {
        "name": "discord_thread_unarchive",
        "description": "Unarchive a thread.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "Thread ID"},
            },
            "required": ["thread_id"],
        },
    },
    {
        "name": "discord_thread_rename",
        "description": "Rename a thread.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "Thread ID"},
                "name": {"type": "string", "description": "New thread name"},
            },
            "required": ["thread_id", "name"],
        },
    },
    {
        "name": "discord_thread_add_member",
        "description": "Add a member to a thread.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "Thread ID"},
                "user_id": {"type": "string", "description": "User ID to add"},
            },
            "required": ["thread_id", "user_id"],
        },
    },
    {
        "name": "discord_thread_remove_member",
        "description": "Remove a member from a thread.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "Thread ID"},
                "user_id": {"type": "string", "description": "User ID to remove"},
            },
            "required": ["thread_id", "user_id"],
        },
    },
    {
        "name": "discord_member_timeout",
        "description": "Timeout (mute) a member for a specified duration. Use 0 to remove timeout.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
                "user": {"type": "string", "description": "Username or user ID"},
                "seconds": {
                    "type": "integer",
                    "description": "Timeout duration in seconds (0 to remove)",
                },
                "reason": {"type": "string", "description": "Reason for timeout", "default": ""},
            },
            "required": ["server", "user", "seconds"],
        },
    },
    {
        "name": "discord_role_edit",
        "description": "Edit a role's name, color, hoist, or mentionable properties.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
                "role": {"type": "string", "description": "Role name"},
                "name": {"type": "string", "description": "New role name", "default": ""},
                "color": {
                    "type": "string",
                    "description": "Hex color (e.g. ff0000)",
                    "default": "",
                },
                "hoist": {"type": "boolean", "description": "Show role separately in member list"},
                "mentionable": {
                    "type": "boolean",
                    "description": "Allow anyone to mention this role",
                },
            },
            "required": ["server", "role"],
        },
    },
    {
        "name": "discord_reaction_users",
        "description": "List users who reacted with a specific emoji on a message.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name with #"},
                "message_id": {"type": "string", "description": "Message ID"},
                "emoji": {"type": "string", "description": "Emoji to check"},
                "limit": {"type": "integer", "description": "Max users to return", "default": 50},
            },
            "required": ["channel", "message_id", "emoji"],
        },
    },
    {
        "name": "discord_poll_results",
        "description": "Get current results of a poll.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name with #"},
                "message_id": {"type": "string", "description": "Message ID of the poll"},
            },
            "required": ["channel", "message_id"],
        },
    },
    {
        "name": "discord_poll_end",
        "description": "End a poll early.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name with #"},
                "message_id": {"type": "string", "description": "Message ID of the poll"},
            },
            "required": ["channel", "message_id"],
        },
    },
    {
        "name": "discord_webhook_list",
        "description": "List webhooks in a server or channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
                "channel": {
                    "type": "string",
                    "description": "Channel name with # (optional, filters to channel)",
                    "default": "",
                },
            },
            "required": ["server"],
        },
    },
    {
        "name": "discord_webhook_create",
        "description": "Create a webhook in a channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
                "channel": {"type": "string", "description": "Channel name with #"},
                "name": {"type": "string", "description": "Webhook name"},
            },
            "required": ["server", "channel", "name"],
        },
    },
    {
        "name": "discord_webhook_delete",
        "description": "Delete a webhook by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
                "webhook_id": {"type": "string", "description": "Webhook ID to delete"},
            },
            "required": ["server", "webhook_id"],
        },
    },
    {
        "name": "discord_event_list",
        "description": "List scheduled events in a server.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
            },
            "required": ["server"],
        },
    },
    {
        "name": "discord_event_create",
        "description": "Create a scheduled event in a server.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
                "name": {"type": "string", "description": "Event name"},
                "start_time": {"type": "string", "description": "Start time (ISO 8601)"},
                "description": {
                    "type": "string",
                    "description": "Event description",
                    "default": "",
                },
                "location": {
                    "type": "string",
                    "description": "Location (for external events)",
                    "default": "",
                },
                "end_time": {
                    "type": "string",
                    "description": "End time (ISO 8601)",
                    "default": "",
                },
                "channel": {
                    "type": "string",
                    "description": "Voice channel (for voice events)",
                    "default": "",
                },
            },
            "required": ["server", "name", "start_time"],
        },
    },
    {
        "name": "discord_event_delete",
        "description": "Delete a scheduled event.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "Server name"},
                "event_id": {"type": "string", "description": "Event ID to delete"},
            },
            "required": ["server", "event_id"],
        },
    },
    {
        "name": "discord_message_bulk_delete",
        "description": "Bulk delete messages in a channel (up to 100, max 14 days old).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name with #"},
                "count": {
                    "type": "integer",
                    "description": "Number of messages to delete (max 100)",
                },
            },
            "required": ["channel", "count"],
        },
    },
]


# Map tool names to discli command builders
def _build_command(tool_name: str, args: dict) -> str:
    """Convert an MCP tool call into a discli command string."""
    match tool_name:
        case "discord_send_message":
            return f"message send {args['channel']} {shlex.quote(args['text'])}"
        case "discord_dm":
            return f"dm send {args['user_id']} {shlex.quote(args['text'])}"
        case "discord_create_thread":
            return (
                f"thread create {args['channel']} {args['message_id']} {shlex.quote(args['title'])}"
            )
        case "discord_send_thread":
            return f"thread send {args['thread_id']} {shlex.quote(args['text'])}"
        case "discord_create_poll":
            opts = " ".join(shlex.quote(o) for o in args["options"])
            cmd = f"poll create {args['channel']} {shlex.quote(args['question'])} {opts}"
            if args.get("multiple"):
                cmd += " --multiple"
            return cmd
        case "discord_add_reaction":
            return f"reaction add {args['channel']} {args['message_id']} {args['emoji']}"
        case "discord_list_messages":
            limit = args.get("limit", 20)
            return f"message list {args['channel']} --limit {limit}"
        case "discord_search_messages":
            limit = args.get("limit", 50)
            return f"message search {args['channel']} {shlex.quote(args['query'])} --limit {limit}"
        case "discord_list_channels":
            return f"channel list --server {shlex.quote(args['server'])}"
        case "discord_member_info":
            return f"member info {shlex.quote(args['server'])} {args['username']}"
        case "discord_list_members":
            limit = args.get("limit", 50)
            return f"member list {shlex.quote(args['server'])} --limit {limit}"
        case "discord_role_list":
            return f"role list {shlex.quote(args['server'])}"
        case "discord_role_assign":
            return f"role assign {shlex.quote(args['server'])} {args['username']} {args['role']}"
        case "discord_server_info":
            return f"server info {shlex.quote(args['server'])}"
        case "discord_send_embed":
            cmd = f"message send {args['channel']}"
            text = args.get("text", "")
            if text:
                cmd += f" {shlex.quote(text)}"
            else:
                cmd += ' ""'
            cmd += f" --embed-title {shlex.quote(args['embed_title'])}"
            if args.get("embed_desc"):
                cmd += f" --embed-desc {shlex.quote(args['embed_desc'])}"
            if args.get("embed_color"):
                cmd += f" --embed-color {args['embed_color']}"
            if args.get("embed_footer"):
                cmd += f" --embed-footer {shlex.quote(args['embed_footer'])}"
            if args.get("embed_image"):
                cmd += f" --embed-image {shlex.quote(args['embed_image'])}"
            if args.get("embed_thumbnail"):
                cmd += f" --embed-thumbnail {shlex.quote(args['embed_thumbnail'])}"
            return cmd
        case "discord_channel_edit":
            cmd = f"channel edit {shlex.quote(args['server'])} {args['channel']}"
            if args.get("name"):
                cmd += f" --name {shlex.quote(args['name'])}"
            if args.get("topic"):
                cmd += f" --topic {shlex.quote(args['topic'])}"
            if args.get("slowmode", -1) >= 0:
                cmd += f" --slowmode {args['slowmode']}"
            if "nsfw" in args:
                cmd += " --nsfw" if args["nsfw"] else ""
            return cmd
        case "discord_channel_set_permissions":
            cmd = (
                f"channel set-permissions {shlex.quote(args['server'])} {args['channel']}"
                f" {shlex.quote(args['target'])}"
            )
            if args.get("target_type"):
                cmd += f" --target-type {args['target_type']}"
            if args.get("allow"):
                cmd += f" --allow {shlex.quote(args['allow'])}"
            if args.get("deny"):
                cmd += f" --deny {shlex.quote(args['deny'])}"
            return cmd
        case "discord_forum_post":
            return (
                f"channel forum-post {shlex.quote(args['server'])} {args['channel']}"
                f" {shlex.quote(args['title'])} {shlex.quote(args['content'])}"
            )
        case "discord_thread_archive":
            return f"thread archive {args['thread_id']}"
        case "discord_thread_unarchive":
            return f"thread unarchive {args['thread_id']}"
        case "discord_thread_rename":
            return f"thread rename {args['thread_id']} {shlex.quote(args['name'])}"
        case "discord_thread_add_member":
            return f"thread add-member {args['thread_id']} {args['user_id']}"
        case "discord_thread_remove_member":
            return f"thread remove-member {args['thread_id']} {args['user_id']}"
        case "discord_member_timeout":
            cmd = f"member timeout {shlex.quote(args['server'])} {args['user']} {args['seconds']}"
            if args.get("reason"):
                cmd += f" --reason {shlex.quote(args['reason'])}"
            return cmd
        case "discord_role_edit":
            cmd = f"role edit {shlex.quote(args['server'])} {shlex.quote(args['role'])}"
            if args.get("name"):
                cmd += f" --name {shlex.quote(args['name'])}"
            if args.get("color"):
                cmd += f" --color {args['color']}"
            if "hoist" in args:
                cmd += " --hoist" if args["hoist"] else ""
            if "mentionable" in args:
                cmd += " --mentionable" if args["mentionable"] else ""
            return cmd
        case "discord_reaction_users":
            limit = args.get("limit", 50)
            return (
                f"reaction users {args['channel']} {args['message_id']}"
                f" {args['emoji']} --limit {limit}"
            )
        case "discord_poll_results":
            return f"poll results {args['channel']} {args['message_id']}"
        case "discord_poll_end":
            return f"poll end {args['channel']} {args['message_id']}"
        case "discord_webhook_list":
            cmd = f"webhook list {shlex.quote(args['server'])}"
            if args.get("channel"):
                cmd += f" {args['channel']}"
            return cmd
        case "discord_webhook_create":
            return (
                f"webhook create {shlex.quote(args['server'])} {args['channel']}"
                f" {shlex.quote(args['name'])}"
            )
        case "discord_webhook_delete":
            return f"webhook delete {shlex.quote(args['server'])} {args['webhook_id']} --yes"
        case "discord_event_list":
            return f"event list {shlex.quote(args['server'])}"
        case "discord_event_create":
            cmd = (
                f"event create {shlex.quote(args['server'])}"
                f" {shlex.quote(args['name'])} {shlex.quote(args['start_time'])}"
            )
            if args.get("description"):
                cmd += f" --description {shlex.quote(args['description'])}"
            if args.get("location"):
                cmd += f" --location {shlex.quote(args['location'])}"
            if args.get("end_time"):
                cmd += f" --end-time {shlex.quote(args['end_time'])}"
            if args.get("channel"):
                cmd += f" --channel {args['channel']}"
            return cmd
        case "discord_event_delete":
            return f"event delete {shlex.quote(args['server'])} {args['event_id']} --yes"
        case "discord_message_bulk_delete":
            return f"message bulk-delete {args['channel']} {args['count']} --yes"
        case _:
            raise ValueError(f"Unknown tool: {tool_name}")


async def _run_discli(command: str) -> str:
    """Run a discli command and return the output."""
    discli = shutil.which("discli")
    if not discli:
        return json.dumps({"error": "discli not installed"})

    try:
        cmd_args = shlex.split(command)
        proc = await asyncio.create_subprocess_exec(
            discli,
            "--json",
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except TimeoutError:
        proc.kill()
        return json.dumps({"error": f"Command timed out: {command}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

    output = stdout.decode().strip() if stdout else ""
    errors = stderr.decode().strip() if stderr else ""

    if proc.returncode != 0:
        return json.dumps({"error": errors or output or f"Exit code {proc.returncode}"})

    try:
        data = json.loads(output)
        return json.dumps(data, indent=2)
    except json.JSONDecodeError:
        return output or json.dumps({"status": "ok"})


async def _handle_request(request: dict) -> dict:
    """Handle a single JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "pocketpaw-discord", "version": "1.0.0"},
            },
        }

    if method == "notifications/initialized":
        return None  # No response for notifications

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        try:
            command = _build_command(tool_name, arguments)
            result = await _run_discli(command)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": result}],
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


async def _read_stdin(loop: asyncio.AbstractEventLoop) -> bytes:
    """Read a line from stdin in a thread (works on all platforms)."""
    return await loop.run_in_executor(None, sys.stdin.buffer.readline)


async def _read_exact(loop: asyncio.AbstractEventLoop, n: int) -> bytes:
    """Read exactly n bytes from stdin in a thread (works on all platforms)."""
    return await loop.run_in_executor(None, sys.stdin.buffer.read, n)


async def main():
    """Run the MCP server on stdio."""
    loop = asyncio.get_event_loop()

    while True:
        header = await _read_stdin(loop)
        if not header:
            break

        header_str = header.decode().strip()
        if header_str.startswith("Content-Length:"):
            content_length = int(header_str.split(":")[1].strip())
            await _read_stdin(loop)  # empty line
            body = await _read_exact(loop, content_length)
            request = json.loads(body.decode())

            response = await _handle_request(request)
            if response is None:
                continue

            response_bytes = json.dumps(response).encode()
            out = f"Content-Length: {len(response_bytes)}\r\n\r\n".encode() + response_bytes
            sys.stdout.buffer.write(out)
            sys.stdout.buffer.flush()


if __name__ == "__main__":
    asyncio.run(main())
