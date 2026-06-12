"""Tests for central/cache.py."""
import sys
import os
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

# Add the repo root to the path so "central" is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from central.cache import set_latest, get_latest, get_server_status


class TestCache:
    @pytest.mark.asyncio
    async def test_set_and_get_latest(self):
        """Ensure basic cache set/get works."""
        # Arrange
        mock_redis = AsyncMock()
        mock_redis.get.return_value = '{"data": "value"}'

        # Act
        with patch('central.cache.get_redis', return_value=mock_redis):
            await set_latest("test_server", {"data": "value"})
            result = await get_latest("test_server")

            # Assert
            assert result == {"data": "value"}
            mock_redis.setex.assert_called_once()
            mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_server_status_miss(self):
        """Ensure None is returned on cache miss."""
        # Arrange
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        # Act
        with patch('central.cache.get_redis', return_value=mock_redis):
            result = await get_server_status("missing_server")

            # Assert
            assert result is None
