"""Tests for central/cache.py."""
import sys
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, '..')
from central.cache import set_cache, get_cache


class TestCache:
    @pytest.mark.asyncio
    async def test_set_and_get_cache(self):
        """Ensure basic cache set/get works."""
        # Arrange
        mock_redis = MagicMock()
        mock_redis.set.return_value = True

        # Act
        with patch('central.cache.get_redis', return_value=mock_redis):
            await set_cache("test_key", {"data": "value"}, ttl=60)
            result = await get_cache("test_key")

            # Assert
            assert result == {"data": "value"}
            mock_redis.set.assert_called_once()
            mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cache_miss(self):
        """Ensure None is returned on cache miss."""
        # Arrange
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        # Act
        with patch('central.cache.get_redis', return_value=mock_redis):
            result = await get_cache("missing_key")

            # Assert
            assert result is None
