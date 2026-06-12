"""Tests for central/poller.py."""
import sys
import os
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

# Add the repo root to the path so "central" is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from central.poller import poll_all


@pytest.mark.asyncio
async def test_poll_all_gathers_results():
    """Ensure poll_all calls _poll_server for each server concurrently."""
    # Arrange
    mock_server = {"label": "test", "host": "127.0.0.1", "port": 9100, "secret": "***"}
    with patch('central.poller._servers', [mock_server]):
        with patch('central.poller._poll_server', new_callable=AsyncMock) as mock_poll:
            mock_poll.return_value = {"status": "ok"}

            # Act
            await poll_all()

            # Assert
            assert mock_poll.call_count == 1


@pytest.mark.asyncio
async def test_poll_all_handles_exceptions():
    """Ensure poll_all doesn't crash if one server fails."""
    # Arrange
    mock_server = {"label": "test", "host": "127.0.0.1", "port": 9100, "secret": "***"}
    with patch('central.poller._servers', [mock_server]):
        with patch('central.poller._poll_server', side_effect=Exception("fail")):
            # Act - should not raise
            await poll_all()

            # Assert
            # poll_all returns None, but _poll_server was called
            pass
