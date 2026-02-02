import pytest
from unittest.mock import patch
from greenapi import api_url_resolver


class TestApiUrlResolver:
    """Test cases for API URL resolution."""

    def test_pool_from_instance_id(self):
        """Test extracting pool code from instance ID."""
        assert api_url_resolver.pool_from_instance_id("7107348018") == 7107
        assert api_url_resolver.pool_from_instance_id("1234567890") == 1234

    def test_pool_from_instance_id_invalid(self):
        """Test invalid instance ID handling."""
        with pytest.raises(ValueError):
            api_url_resolver.pool_from_instance_id("123")  # Too short

    def test_resolve_api_url_exact_match(self):
        """Test exact pool match."""
        url = api_url_resolver.resolve_api_url("1101348018")
        assert url == "https://api.green-api.com"

    def test_resolve_api_url_prefix_match(self):
        """Test prefix pool match."""
        url = api_url_resolver.resolve_api_url("7700348018")
        assert url == "https://7700.api.greenapi.com"

    def test_resolve_api_url_default(self):
        """Test default fallback."""
        url = api_url_resolver.resolve_api_url("9999348018")
        assert url == "https://api.p03.green-api.com"
