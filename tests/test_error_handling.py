"""Comprehensive tests to boost coverage to 75%+."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import pytest


class TestClientComplete:
    """Complete coverage for greenapi/client.py missing lines."""

    def test_get_certificate_files_with_fallback(self):
        """Test get_certificate_files returns fallback values."""
        from greenapi.client import get_certificate_files, set_certificate_files

        # Test fallback when no certs set
        cert, key = get_certificate_files()
        assert cert == "client.crt"
        assert key == "client.key"

        # Test with custom certs
        set_certificate_files("/path/to/cert.crt", "/path/to/key.key")
        cert, key = get_certificate_files()
        assert cert == "/path/to/cert.crt"
        assert key == "/path/to/key.key"

        # Reset
        set_certificate_files("client.crt", "client.key")

    def test_send_request_cert_with_none_key(self):
        """Test send_request handles cert tuple with None key."""
        from greenapi.client import send_request

        with patch("greenapi.client.requests.request") as mock_req:
            mock_resp = Mock()
            mock_resp.status_code = 200
            mock_resp.text = "success"
            mock_req.return_value = mock_resp

            result = send_request(
                "GET",
                "https://api.test.com/endpoint",
                cert_files=("/path/cert.crt", None),
                use_cert=True,
            )

            assert result == "success"
            # Should pass just cert path, not tuple
            mock_req.assert_called_once()
            call_args = mock_req.call_args
            assert call_args[1]["cert"] == "/path/cert.crt"

    def test_send_request_ssl_error(self):
        """Test send_request handles SSL errors."""
        from greenapi.client import send_request
        import requests

        with patch("greenapi.client.requests.request") as mock_req:
            mock_req.side_effect = requests.exceptions.SSLError("Certificate verify failed")

            result = send_request("GET", "https://api.test.com/endpoint", use_cert=True)

            assert "SSL Certificate Error" in result
            assert "Certificate verify failed" in result

    def test_send_request_general_exception(self):
        """Test send_request handles general exceptions."""
        from greenapi.client import send_request

        with patch("greenapi.client.requests.request") as mock_req:
            mock_req.side_effect = ValueError("Unexpected error")

            result = send_request("GET", "https://api.test.com/endpoint")

            assert "Error:" in result
            assert "Unexpected error" in result

    def test_send_request_http_error(self):
        """Test send_request handles non-200 HTTP responses."""
        from greenapi.client import send_request

        with patch("greenapi.client.requests.request") as mock_req:
            mock_resp = Mock()
            mock_resp.status_code = 404
            mock_resp.text = "Not Found"
            mock_req.return_value = mock_resp

            result = send_request("POST", "https://api.test.com/endpoint", json_body={"test": "data"})

            assert "HTTP 404" in result
            assert "Not Found" in result


class TestApiUrlResolverComplete:
    """Complete coverage for greenapi/api_url_resolver.py."""

    def test_pool_from_instance_id_invalid_format(self):
        """Test pool_from_instance_id with invalid formats."""
        from greenapi.api_url_resolver import pool_from_instance_id

        # Too short
        with pytest.raises(ValueError, match="Invalid idInstance"):
            pool_from_instance_id("123")

        # Non-numeric
        with pytest.raises(ValueError, match="Invalid idInstance"):
            pool_from_instance_id("abcd1234")

        # Empty
        with pytest.raises(ValueError, match="Invalid idInstance"):
            pool_from_instance_id("")

    def test_resolve_api_url_unknown_pool(self):
        """Test resolve_api_url with unknown pool (fallback behavior)."""
        from greenapi.api_url_resolver import resolve_api_url

        # Pool 8888 doesn't match any rules
        result = resolve_api_url("8888123456", prefer_direct=True)
        # Should fall back to default greenapi.com
        assert result == "https://api.greenapi.com"


class TestUpdateCore:
    """Test core update.py logic (version comparison, update checking)."""

    def test_get_current_version_success(self):
        """Test get_current_version reads version.json correctly."""
        from app.update import get_current_version

        version = get_current_version()
        # Should be a valid version string
        assert isinstance(version, str)
        assert len(version.split(".")) >= 3

    def test_get_current_version_missing_file(self):
        """Test get_current_version handles missing version.json."""
        from app.update import get_current_version

        with patch("builtins.open", side_effect=FileNotFoundError):
            version = get_current_version()
            assert version == "0.0.0"

    def test_update_manager_is_newer_version(self):
        """Test _is_newer_version comparison logic."""
        from app.update import UpdateManager

        manager = UpdateManager()

        # Test newer versions
        assert manager._is_newer_version("1.2.3", "1.2.2") is True
        assert manager._is_newer_version("2.0.0", "1.9.9") is True
        assert manager._is_newer_version("1.3.0", "1.2.9") is True
        assert manager._is_newer_version("1.2.10", "1.2.9") is True

        # Test same version
        assert manager._is_newer_version("1.2.3", "1.2.3") is False

        # Test older versions
        assert manager._is_newer_version("1.2.2", "1.2.3") is False
        assert manager._is_newer_version("1.9.9", "2.0.0") is False

        # Test different lengths
        assert manager._is_newer_version("1.2.3.1", "1.2.3") is True
        assert manager._is_newer_version("1.2.3", "1.2.3.1") is False

    def test_update_manager_is_newer_version_invalid(self):
        """Test _is_newer_version with invalid version strings."""
        from app.update import UpdateManager

        manager = UpdateManager()

        # Invalid version strings should return False
        assert manager._is_newer_version("invalid", "1.2.3") is False
        assert manager._is_newer_version("1.2.3", "invalid") is False
        assert manager._is_newer_version("1.x.3", "1.2.3") is False

    def test_update_manager_get_download_url_with_asset(self):
        """Test _get_download_url extracts correct URL from assets."""
        from app.update import UpdateManager

        manager = UpdateManager()

        release_data = {
            "tag_name": "v1.2.3",
            "assets": [
                {"name": "other-file.zip", "browser_download_url": "https://example.com/other.zip"},
                {"name": "greenapi-helper.exe", "browser_download_url": "https://example.com/app.exe"},
            ],
        }

        url = manager._get_download_url(release_data)
        assert url == "https://example.com/app.exe"

    def test_update_manager_get_download_url_fallback(self):
        """Test _get_download_url uses fallback when asset not found."""
        from app.update import UpdateManager

        manager = UpdateManager()

        release_data = {
            "tag_name": "v1.2.3",
            "assets": [{"name": "other.zip", "browser_download_url": "https://example.com/other.zip"}],
        }

        url = manager._get_download_url(release_data)
        expected_url = "https://github.com/Umar-Rehman/greenapi-helper/releases/download/v1.2.3/greenapi-helper.exe"
        assert url == expected_url

    @patch("app.update.urllib.request.urlopen")
    def test_update_manager_perform_update_check_success(self, mock_urlopen):
        """Test _perform_update_check emits signal on new version."""
        from app.update import UpdateManager

        manager = UpdateManager()

        # Mock successful API response
        mock_response = Mock()
        mock_response.read.return_value = json.dumps(
            {
                "tag_name": "v99.0.0",
                "html_url": "https://github.com/repo/releases/tag/v99.0.0",
                "body": "New features!",
                "assets": [{"name": "greenapi-helper.exe", "browser_download_url": "https://example.com/app.exe"}],
            }
        ).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        # Connect signal
        update_info_emitted = []
        manager.update_available.connect(lambda info: update_info_emitted.append(info))

        # Perform check
        manager._perform_update_check()

        # Should emit update_available signal
        assert len(update_info_emitted) == 1
        assert update_info_emitted[0]["version"] == "99.0.0"
        assert "New features!" in update_info_emitted[0]["notes"]

    @patch("app.update.urllib.request.urlopen")
    def test_update_manager_perform_update_check_error(self, mock_urlopen):
        """Test _perform_update_check emits error signal on failure."""
        from app.update import UpdateManager
        import urllib.error

        manager = UpdateManager()

        # Mock network error
        mock_urlopen.side_effect = urllib.error.URLError("Network error")

        # Connect signal
        errors_emitted = []
        manager.update_error.connect(lambda err: errors_emitted.append(err))

        # Perform check
        manager._perform_update_check()

        # Should emit error signal
        assert len(errors_emitted) == 1
        assert "Failed to check for updates" in errors_emitted[0]

    @patch("app.update.urllib.request.urlopen")
    def test_update_manager_perform_update_check_no_version(self, mock_urlopen):
        """Test _perform_update_check handles missing tag_name."""
        from app.update import UpdateManager

        manager = UpdateManager()

        # Mock response without tag_name
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({"html_url": "https://github.com/repo/releases"}).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = mock_response

        # Connect signal
        update_info_emitted = []
        manager.update_available.connect(lambda info: update_info_emitted.append(info))

        # Perform check
        manager._perform_update_check()

        # Should not emit update_available (no version to compare)
        assert len(update_info_emitted) == 0


class TestCredentialsCore:
    """Test core credentials.py logic (excluding OS-specific exports)."""

    def test_credential_manager_init(self):
        """Test CredentialManager initialization."""
        from greenapi.credentials import CredentialManager

        manager = CredentialManager()

        assert manager._cert_context is None
        assert manager._cert_pem is None
        assert manager._temp_cert_file is None
        assert manager._temp_key_file is None
        assert manager._kibana_cookie is None

    def test_credential_manager_set_kibana_cookie(self):
        """Test set_kibana_cookie stores cookie."""
        from greenapi.credentials import CredentialManager

        manager = CredentialManager()
        manager.set_kibana_cookie("test_cookie_value")

        assert manager._kibana_cookie == "test_cookie_value"

    def test_credential_manager_get_kibana_cookie(self):
        """Test get_kibana_cookie retrieves stored cookie."""
        from greenapi.credentials import CredentialManager

        manager = CredentialManager()
        manager.set_kibana_cookie("my_session_cookie")

        cookie = manager.get_kibana_cookie()
        assert cookie == "my_session_cookie"

    def test_credential_manager_get_kibana_cookie_none(self):
        """Test get_kibana_cookie returns None when not set."""
        from greenapi.credentials import CredentialManager

        manager = CredentialManager()
        cookie = manager.get_kibana_cookie()
        assert cookie is None

    def test_credential_manager_get_certificate_files_none(self):
        """Test get_certificate_files returns None when not set."""
        from greenapi.credentials import CredentialManager

        manager = CredentialManager()
        files = manager.get_certificate_files()
        assert files is None

    def test_credential_manager_cleanup(self):
        """Test cleanup removes temp files."""
        from greenapi.credentials import CredentialManager

        manager = CredentialManager()

        # Create mock temp files
        with tempfile.TemporaryDirectory() as temp_dir:
            manager._temp_dir = temp_dir
            manager._temp_cert_file = Path(temp_dir) / "client.crt"
            manager._temp_key_file = Path(temp_dir) / "client.key"

            # Create actual files
            manager._temp_cert_file.write_text("cert")
            manager._temp_key_file.write_text("key")

            assert manager._temp_cert_file.exists()
            assert manager._temp_key_file.exists()

            # Cleanup
            manager.cleanup()

            # Files should be removed (or temp_dir cleaned)
            assert manager._temp_cert_file is None
            assert manager._temp_key_file is None
            assert manager._kibana_cookie is None


class TestUpdateManagerSingleton:
    """Test update manager singleton pattern."""

    def test_get_update_manager_singleton(self):
        """Test get_update_manager returns same instance."""
        from app.update import get_update_manager

        manager1 = get_update_manager()
        manager2 = get_update_manager()

        # Should be the same instance
        assert manager1 is manager2
