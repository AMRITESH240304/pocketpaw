# Tests for Telegram Adapter
# Created: 2026-02-04

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from telegram.constants import ChatAction

from pocketclaw.bus.events import OutboundMessage, Channel
from pocketclaw.bus.adapters.telegram_adapter import TelegramAdapter


@pytest.fixture
def telegram_adapter():
    """Create a TelegramAdapter instance with mocked bot."""
    adapter = TelegramAdapter(token="test_token", allowed_user_id=12345)

    # Clear any leftover buffers from previous tests
    adapter._buffers.clear()

    # Mock the application and bot
    adapter.app = MagicMock()
    adapter.app.bot = MagicMock()
    adapter.app.bot.send_chat_action = AsyncMock()
    adapter.app.bot.send_message = AsyncMock()
    adapter.app.bot.edit_message_text = AsyncMock()

    return adapter


@pytest.mark.asyncio
async def test_typing_indicator_on_stream_start(telegram_adapter):
    """Test that typing indicator is sent when starting a stream."""
    # Setup mock for send_message to return a message with id
    mock_message = MagicMock()
    mock_message.message_id = 123
    telegram_adapter.app.bot.send_message.return_value = mock_message

    # Create a stream chunk message
    message = OutboundMessage(
        channel=Channel.TELEGRAM,
        chat_id="12345",
        content="Hello",
        is_stream_chunk=True
    )

    # Handle the stream chunk
    await telegram_adapter._handle_stream_chunk(message)

    # Verify typing indicator was sent
    telegram_adapter.app.bot.send_chat_action.assert_called_once_with(
        chat_id="12345",
        action=ChatAction.TYPING
    )

    # Verify initial message was sent
    telegram_adapter.app.bot.send_message.assert_called_once_with(
        chat_id="12345",
        text="🧠 ..."
    )


@pytest.mark.asyncio
async def test_typing_indicator_on_message_receive(telegram_adapter):
    """Test that typing indicator is sent when receiving a user message."""
    # Create mock update and context
    mock_update = MagicMock()
    mock_update.effective_user.id = 12345
    mock_update.effective_user.username = "testuser"
    mock_update.effective_chat.id = 67890
    mock_update.message.text = "Hello bot"

    mock_context = MagicMock()

    # Mock the _publish_inbound method
    telegram_adapter._publish_inbound = AsyncMock()

    # Handle the message
    await telegram_adapter._handle_message(mock_update, mock_context)

    # Verify typing indicator was sent
    telegram_adapter.app.bot.send_chat_action.assert_called_once_with(
        chat_id=67890,
        action=ChatAction.TYPING
    )

    # Verify message was published
    telegram_adapter._publish_inbound.assert_called_once()


@pytest.mark.asyncio
async def test_no_typing_indicator_on_subsequent_chunks(telegram_adapter):
    """Test that typing indicator is only sent on first chunk, not subsequent ones."""
    # Setup mock for send_message
    mock_message = MagicMock()
    mock_message.message_id = 123
    telegram_adapter.app.bot.send_message.return_value = mock_message

    chat_id = "12345"

    # First chunk
    message1 = OutboundMessage(
        channel=Channel.TELEGRAM,
        chat_id=chat_id,
        content="Hello",
        is_stream_chunk=True
    )
    await telegram_adapter._handle_stream_chunk(message1)

    # Second chunk
    message2 = OutboundMessage(
        channel=Channel.TELEGRAM,
        chat_id=chat_id,
        content=" world",
        is_stream_chunk=True
    )
    await telegram_adapter._handle_stream_chunk(message2)

    # Typing indicator should only be called once (on first chunk)
    assert telegram_adapter.app.bot.send_chat_action.call_count == 1

    # Clean up buffer
    await telegram_adapter._flush_stream_buffer(chat_id)


@pytest.mark.asyncio
async def test_unauthorized_user_no_typing_indicator(telegram_adapter):
    """Test that unauthorized users don't trigger typing indicator."""
    # Create mock update with unauthorized user
    mock_update = MagicMock()
    mock_update.effective_user.id = 99999  # Different from allowed_user_id
    mock_update.effective_chat.id = 67890
    mock_update.message.text = "Hello"

    mock_context = MagicMock()

    # Handle the message
    await telegram_adapter._handle_message(mock_update, mock_context)

    # Verify typing indicator was NOT sent
    telegram_adapter.app.bot.send_chat_action.assert_not_called()
