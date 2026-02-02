from unittest.mock import patch, MagicMock
from greenapi import credentials


class TestCredentialManager:
    """Test cases for credential manager."""

    def test_init(self):
        """Test credential manager initialization."""
        mgr = credentials.CredentialManager()
        assert mgr._cert_pem is None
        assert mgr._kibana_cookie is None

    def test_set_certificate(self):
        """Test setting certificate."""
        mgr = credentials.CredentialManager()
        cert_pem = b"-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----"
        cert_context = MagicMock()

        with patch("tempfile.mkdtemp", return_value="/tmp/test"), patch(
            "pathlib.Path.write_bytes"
        ), patch.object(mgr, "_export_private_key", return_value=True), patch.object(
            mgr, "_obtain_kibana_session"
        ):
            result = mgr.set_certificate(cert_pem, cert_context)
            assert result is True

    def test_get_certificate_files_no_cert(self):
        """Test getting certificate files when none set."""
        mgr = credentials.CredentialManager()
        assert mgr.get_certificate_files() is None

    def test_cleanup(self):
        """Test cleanup functionality."""
        mgr = credentials.CredentialManager()
        with patch("os.path.exists", return_value=True), patch("os.unlink"), patch(
            "shutil.rmtree"
        ):
            mgr.cleanup()
            # Should not raise exceptions
