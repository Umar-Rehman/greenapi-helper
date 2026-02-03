from unittest.mock import patch, MagicMock
from greenapi import client


class TestClient:
    """Test cases for the Green API client."""

    def test_build_url(self):
        """Test URL building."""
        url = client._build_url("https://api.example.com", "12345", "test")
        assert url == "https://api.example.com/waInstance12345/test"

    @patch("greenapi.client.requests.request")
    def test_send_request_success(self, mock_request):
        """Test successful request sending."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"success": true}'
        mock_request.return_value = mock_response

        result = client.send_request("GET", "https://example.com")
        assert result == '{"success": true}'

    @patch("greenapi.client.requests.request")
    def test_send_request_error(self, mock_request):
        """Test request error handling."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"
        mock_request.return_value = mock_response

        result = client.send_request("GET", "https://example.com")
        assert result == "HTTP 500: Server Error"

    def test_make_api_call(self):
        """Test API call construction."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = '{"result": "ok"}'
            result = client.make_api_call(
                "https://api.example.com",
                "12345",
                "token123",
                "getStateInstance",
                "GET",
            )
            mock_send.assert_called_once()
            assert result == '{"result": "ok"}'

    def test_get_instance_state(self):
        """Test get instance state function."""
        with patch("greenapi.client.make_api_call") as mock_call:
            mock_call.return_value = '{"stateInstance": "authorized"}'
            result = client.get_instance_state("https://api.example.com", "12345", "token123")
            assert result == '{"stateInstance": "authorized"}'

    def test_certificate_files_cache(self):
        """Test that get_certificate_files uses lru_cache correctly."""
        # Clear any existing cache
        client.get_certificate_files.cache_clear()
        
        # First call should execute
        result1 = client.get_certificate_files()
        assert result1 == ("client.crt", "client.key")
        
        # Second call should return cached result
        result2 = client.get_certificate_files()
        assert result2 == result1
        
        # Verify cache_info shows hits
        cache_info = client.get_certificate_files.cache_info()
        assert cache_info.hits >= 1
        assert cache_info.misses >= 1
        
        # Setting new certificates should clear cache
        client.set_certificate_files("new.crt", "new.key")
        result3 = client.get_certificate_files()
        assert result3 == ("new.crt", "new.key")
        
        # Reset for other tests
        client._fallback_cert_files = None
        client.get_certificate_files.cache_clear()
