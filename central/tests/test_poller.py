"""Tests for central/poller.py."""
import sys
import os
import asyncio
from unittest.mock import MagicMock, patch
import pytest

# Add the repo root to the path so "central" is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from central.poller import poll_all


@pytest.mark.asyncio
async def test_poll_all_gathers_results():
    """Ensure poll_all gathers results from all servers concurrently."""
    # Arrange
    mock_server = {"label": "test", "host": "127.0.0.1", "port": 9100, "secret": "test"}
    with patch('central.poller.load_servers', return_value=[mock_server]):
        with patch('central.poller._poll_server', new_callable=MagicMock) as mock_poll:
            mock_poll.return_value = {"status": "ok"}

            # Act
            result = await poll_all()

            # Assert
            assert mock_poll.call_count == 1
            assert result == [{"status": "ok"}]


@pytest.mark.asyncio
async def test_poll_all_handles_exceptions():
    """Ensure poll_all doesn't crash if one server fails."""
    # Arrange
    mock_server = {"label": "test", "host": "127.0.0.1", "port": 9100, "secret": "test"}
    with patch('central.poller.load_servers', return_value=[mock_server]):
        with patch('central.poller._poll_server', side_effect=Exception("fail")):
            # Act
            result = await poll_all()

            # Assert
            assert len(result) == 1
            assert isinstance(result[0], Exception)
