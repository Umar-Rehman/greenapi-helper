"""Credential manager for storing certificates and Kibana credentials in memory."""

from __future__ import annotations

import tempfile
import os
import subprocess
import secrets
import keyring
import time
from pathlib import Path
from typing import Optional
import atexit


class CredentialManager:
    """
    Manages client certificates and Kibana credentials for the application session.

    Certificates from Windows store are temporarily exported to files for use with requests library,
    and cleaned up on application exit.
    """

    def __init__(self):
        self._cert_context = None
        self._cert_pem: Optional[bytes] = None
        self._temp_cert_file: Optional[Path] = None
        self._temp_key_file: Optional[Path] = None
        self._kibana_cookie: Optional[str] = None
        self._temp_dir: Optional[str] = None

        # Clean up old temp directories from previous sessions
        self._cleanup_old_temp_dirs()

        # Register cleanup
        atexit.register(self.cleanup)

    def set_certificate(self, cert_pem: bytes, cert_store_obj) -> bool:
        """
        Set the client certificate for API calls and automatically obtain Kibana session.

        Args:
            cert_pem: Certificate in PEM format
            cert_store_obj: wincertstore CERT_CONTEXT object

        Returns:
            True if certificate was set successfully, False otherwise
        """
        try:
            # Clean up any existing temp files
            self.cleanup()

            self._cert_pem = cert_pem
            self._cert_context = cert_store_obj

            # Create temporary directory for certificate files
            self._temp_dir = tempfile.mkdtemp(prefix="greenapi_")

            # Write certificate to temp file
            self._temp_cert_file = Path(self._temp_dir) / "client.crt"
            self._temp_cert_file.write_bytes(cert_pem)

            # Try to export the private key
            self._export_private_key()

            # Automatically obtain Kibana session cookie using the certificate
            self._obtain_kibana_session()

            return True

        except Exception:
            self.cleanup()
            raise

    def _obtain_kibana_session(self):
        """Automatically authenticate to Kibana using the certificate."""
        try:
            from greenapi.elk_auth import get_kibana_session_cookie

            cert_files = self.get_certificate_files()
            if not cert_files:
                return

            cookie = get_kibana_session_cookie(cert_files)
            if cookie:
                self.set_kibana_cookie(cookie)

        except Exception:
            pass

    def _export_private_key(self) -> bool:
        """
        Try to export the private key from the certificate store object.

        Returns:
            True if key was successfully exported, False otherwise
        """
        try:
            # Method 1: Try using Windows certutil command (cleanest approach)
            if self._export_via_certutil():
                return True

                # Method 2: Try oscrypto if available (removed - not needed)
                return True

            # Method 3: Try low-level Windows API (complex but sometimes works)
            if self._export_via_windows_api():
                return True

            return False

        except Exception:
            return False

    def _export_via_certutil(self) -> bool:
        """Use Windows certutil.exe to export the PFX by thumbprint (more reliable than CN)."""
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import hashes, serialization

            if not self._temp_cert_file or not self._temp_cert_file.exists():
                return False

            # Read the PEM certificate
            cert_pem = self._temp_cert_file.read_bytes()
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

            # Use thumbprint to avoid CN ambiguity
            thumbprint = cert.fingerprint(hashes.SHA1()).hex().upper()

            # Get CN for fallback attempts
            cn_attrs = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
            cn = cn_attrs[0].value if cn_attrs else "Certificate"

            pfx_file = Path(self._temp_dir) / "temp.pfx"
            pfx_password = secrets.token_urlsafe(18)

            # Try certutil export by thumbprint (current user store)
            try:
                result = subprocess.run(
                    [
                        "certutil.exe",
                        "-user",
                        "-exportPFX",
                        "-p",
                        pfx_password,
                        "-f",
                        "MY",
                        thumbprint,
                        str(pfx_file),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )

                if result.returncode != 0:
                    # Fallback: try CN (less reliable)
                    result = subprocess.run(
                        [
                            "certutil.exe",
                            "-user",
                            "-exportPFX",
                            "-p",
                            pfx_password,
                            "-f",
                            "MY",
                            cn,
                            str(pfx_file),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )

                if result.returncode == 0 and pfx_file.exists():
                    # Load and extract from PFX
                    from cryptography.hazmat.primitives.serialization import pkcs12

                    pfx_data = pfx_file.read_bytes()
                    private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
                        pfx_data, pfx_password.encode(), backend=default_backend()
                    )

                    if private_key:
                        # Export key to PEM
                        key_pem = private_key.private_bytes(
                            encoding=serialization.Encoding.PEM,
                            format=serialization.PrivateFormat.TraditionalOpenSSL,
                            encryption_algorithm=serialization.NoEncryption(),
                        )

                        self._temp_key_file = Path(self._temp_dir) / "client.key"
                        self._temp_key_file.write_bytes(key_pem)
                        return True

                return False
            finally:
                try:
                    if pfx_file.exists():
                        pfx_file.unlink()
                except Exception:
                    pass

        except Exception:
            return False

    # def _export_via_windows_api(self) -> bool:
    #     """Try using pywin32 Windows API to export the key."""
    #     try:
    #         import ctypes
    #         from ctypes import c_void_p, POINTER, c_uint32

    #         # This is very complex and requires proper CryptoAPI setup
    #         # For now, we'll document this and return False
    #         # Full implementation would require:
    #         # 1. CryptFindCertificateKeyProvInfo to find key provider
    #         # 2. CryptGetUserKey to get the key handle
    #         # 3. CryptExportKey to export the key

    #         return False

    #     except Exception:
    #         return False

    def get_certificate_files(self) -> Optional[tuple[str, str]]:
        """
        Get the paths to temporary certificate files.

        Returns:
            Tuple of (cert_path, key_path) or None if no certificate is set.
            If key file is not available, returns (cert_path, None).
        """
        if self._temp_cert_file and self._temp_cert_file.exists():
            key_path = None
            if self._temp_key_file and self._temp_key_file.exists():
                key_path = str(self._temp_key_file)
            return (str(self._temp_cert_file), key_path)
        return None

    def get_certificate_context(self):
        """Get the Windows certificate context."""
        return self._cert_context

    def ensure_private_key_exported(self) -> bool:
        """Ensure the private key is exported to a temp file if possible."""
        if self._temp_key_file and self._temp_key_file.exists():
            return True
        return self._export_private_key()

    def set_kibana_cookie(self, cookie: str):
        """Set the Kibana session cookie."""
        self._kibana_cookie = cookie

    def get_kibana_cookie(self) -> Optional[str]:
        """Get the Kibana session cookie."""
        return self._kibana_cookie

    def save_credentials(self, username: str, password: str):
        """Save username and password to Windows Credential Manager."""
        try:
            keyring.set_password("GreenAPIHelper", "kibana_username", username)
            keyring.set_password("GreenAPIHelper", username, password)
        except Exception:
            pass  # Fail silently if credential storage fails

    def get_saved_credentials(self) -> Optional[tuple[str, str]]:
        """Retrieve saved username and password from Windows Credential Manager."""
        try:
            username = keyring.get_password("GreenAPIHelper", "kibana_username")
            if username:
                password = keyring.get_password("GreenAPIHelper", username)
                if password:
                    return (username, password)
        except Exception:
            pass
        return None

    def clear_saved_credentials(self):
        """Clear saved credentials from Windows Credential Manager."""
        try:
            username = keyring.get_password("GreenAPIHelper", "kibana_username")
            if username:
                keyring.delete_password("GreenAPIHelper", username)
            keyring.delete_password("GreenAPIHelper", "kibana_username")
        except Exception:
            pass

    def save_certificate_thumbprint(self, thumbprint: str):
        """Save certificate thumbprint for auto-selection on next launch."""
        try:
            keyring.set_password("GreenAPIHelper", "cert_thumbprint", thumbprint)
        except Exception:
            pass

    def get_saved_certificate_thumbprint(self) -> Optional[str]:
        """Get saved certificate thumbprint."""
        try:
            return keyring.get_password("GreenAPIHelper", "cert_thumbprint")
        except Exception:
            return None

    def has_certificate(self) -> bool:
        """Check if a certificate is configured."""
        return self._temp_cert_file is not None and self._temp_cert_file.exists()

    def has_kibana_cookie(self) -> bool:
        """Check if Kibana cookie is configured."""
        return bool(self._kibana_cookie)

    def is_authenticated(self) -> bool:
        """Check if both certificate and Kibana cookie are configured."""
        return self.has_certificate() and self.has_kibana_cookie()

    def cleanup(self):
        """Clean up temporary certificate files."""
        try:
            if self._temp_cert_file and self._temp_cert_file.exists():
                self._temp_cert_file.unlink()
                self._temp_cert_file = None

            if self._temp_key_file and self._temp_key_file.exists():
                self._temp_key_file.unlink()
                self._temp_key_file = None

            if self._temp_dir and os.path.exists(self._temp_dir):
                # Remove any remaining files in temp dir
                import shutil

                shutil.rmtree(self._temp_dir, ignore_errors=True)
                self._temp_dir = None

        except Exception:
            pass

    def _cleanup_old_temp_dirs(self):
        """Clean up old greenapi temp directories from previous sessions.

        Removes temp directories older than 1 hour to handle cases where
        the app crashed or was force-closed without running cleanup.
        """
        try:
            import shutil

            temp_base = Path(tempfile.gettempdir())
            current_time = time.time()
            one_hour_ago = current_time - 3600

            # Find all greenapi_ temp directories
            for item in temp_base.glob("greenapi_*"):
                if item.is_dir():
                    try:
                        # Check if directory is older than 1 hour
                        dir_mtime = os.path.getmtime(item)
                        if dir_mtime < one_hour_ago:
                            shutil.rmtree(item, ignore_errors=True)
                    except (OSError, PermissionError):
                        # Skip if we can't access or delete
                        pass
        except Exception:
            # Don't fail if cleanup fails
            pass

    def clear(self, clear_saved=False):
        """Clear all credentials and clean up files.

        Args:
            clear_saved: If True, also clear saved credentials from Windows Credential Manager
        """
        self.cleanup()
        self._cert_pem = None
        self._cert_context = None
        self._kibana_cookie = None
        if clear_saved:
            self.clear_saved_credentials()


# Global credential manager instance
_credential_manager = CredentialManager()


def get_credential_manager() -> CredentialManager:
    """Get the global credential manager instance."""
    return _credential_manager
