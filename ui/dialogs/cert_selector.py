"""Dialog for selecting client certificates from Windows certificate store."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QDialogButtonBox,
    QMessageBox,
    QStyleFactory,
    QWidget,
)
from PySide6.QtCore import Qt


class CertificateSelectorDialog(QDialog):
    """Dialog to select a client certificate from the Windows certificate store."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Select Client Certificate")
        self.setStyle(QStyleFactory.create("Fusion"))
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        self._selected_cert_context = None
        self._certificates = []

        self._setup_ui()
        self._load_certificates()

    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)

        # Info label
        info_label = QLabel("Select a client certificate from your Windows certificate store:")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Certificate list
        self.cert_list = QListWidget()
        self.cert_list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.cert_list)

        # Details label
        self.details_label = QLabel("Select a certificate to view details.")
        self.details_label.setWordWrap(True)
        self.details_label.setStyleSheet("padding: 10px; background: #f0f0f0;")
        layout.addWidget(self.details_label)

        self.cert_list.currentItemChanged.connect(self._on_selection_changed)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_certificates(self):
        """Load certificates from the Windows certificate store."""
        try:
            import wincertstore

            # Try multiple certificate stores to find certificates
            # MY (personal) store typically contains client certificates with private keys
            store_names = ["MY", "AuthRoot", "CA", "Trust"]
            all_certs_found = []

            for storename in store_names:
                try:
                    store = wincertstore.CertSystemStore(storename)
                    store_certs = list(store)

                    for cert_info in store_certs:
                        try:
                            # Get certificate in DER format
                            cert_der = cert_info.get_encoded()

                            # Parse certificate to get subject info
                            from cryptography import x509
                            from cryptography.hazmat.backends import default_backend

                            cert = x509.load_der_x509_certificate(cert_der, default_backend())

                            # Get subject information
                            try:
                                cn_attrs = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
                                if cn_attrs:
                                    cn = cn_attrs[0].value
                                else:
                                    cn = cert.subject.rfc4514_string()
                            except (ValueError, TypeError) as e:
                                self._log_error(f"Failed to parse certificate name: {str(e)}")
                                cn = "Unknown Certificate"

                            subject = cert.subject.rfc4514_string()
                            issuer = cert.issuer.rfc4514_string()

                            # In Windows, certificates with private keys are in the MY store
                            # Other stores contain CA certs and trusted roots (no private keys)
                            has_private_key = storename == "MY"

                            # Store all certificates found
                            all_certs_found.append(
                                {
                                    "cert_store_obj": cert_info,
                                    "cert_der": cert_der,
                                    "subject": subject,
                                    "issuer": issuer,
                                    "cn": cn,
                                    "has_key": has_private_key,
                                    "store": storename,
                                }
                            )

                        except Exception:
                            # Skip certificates that can't be processed
                            continue
                except Exception:
                    # Skip stores that can't be accessed
                    continue

            # Add certificates with private keys first (usable)
            usable_certs = [c for c in all_certs_found if c["has_key"]]

            for cert_info in usable_certs:
                self._certificates.append(cert_info)
                display_text = f"{cert_info['cn']} [{cert_info['store']}]"
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, len(self._certificates) - 1)
                self.cert_list.addItem(item)

            # Add certificates without private keys (for reference) if none with keys were found
            if self.cert_list.count() == 0:
                # No usable certificates found, show all for debugging
                for cert_info in all_certs_found:
                    self._certificates.append(cert_info)
                    status = "⚠ No Private Key"
                    display_text = f"{cert_info['cn']} - {status} [{cert_info['store']}]"
                    item = QListWidgetItem(display_text)
                    item.setData(Qt.UserRole, len(self._certificates) - 1)
                    self.cert_list.addItem(item)

            if self.cert_list.count() == 0:
                QMessageBox.warning(
                    self,
                    "No Certificates Found",
                    "No client certificates found in your Windows certificate store.\n\n"
                    "To view available certificates:\n"
                    "1. Open certmgr.msc\n"
                    "2. Navigate to Current User → Personal → Certificates\n"
                    "3. Check if your certificate is listed\n\n"
                    "If your certificate is in a different location or doesn't have a private key,\n"
                    "you may need to import it with the 'Mark this key as exportable' option.\n\n"
                    "Check the console output for debug information.",
                )

        except Exception as e:
            QMessageBox.critical(
                self, "Error Loading Certificates", f"Failed to load certificates from Windows store:\n{str(e)}"
            )

    def _on_selection_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Handle certificate selection change."""
        if not current:
            self.details_label.setText("Select a certificate to view details.")
            return

        cert_idx = current.data(Qt.UserRole)
        cert_info = self._certificates[cert_idx]

        details = (
            f"<b>Subject:</b><br>{cert_info['subject']}<br><br>"
            f"<b>Issuer:</b><br>{cert_info['issuer']}<br><br>"
            f"<b>Store:</b> {cert_info.get('store', 'Unknown')}<br>"
        )

        # Add warning if no private key
        if not cert_info.get("has_key", True):
            details += "<br><b style='color: red;'>⚠ No Private Key</b><br>"
            details += "This certificate cannot be used for authentication.<br>"
            details += "Please import a certificate with a private key."

        self.details_label.setText(details)

    def _on_accept(self):
        """Handle OK button click."""
        current = self.cert_list.currentItem()
        if not current:
            QMessageBox.warning(self, "No Selection", "Please select a certificate.")
            return

        cert_idx = current.data(Qt.UserRole)
        cert_info = self._certificates[cert_idx]

        # Check if certificate has a private key
        if not cert_info.get("has_key", False):
            QMessageBox.warning(
                self,
                "No Private Key",
                "This certificate does not have a private key associated with it.\n\n"
                "You need a certificate with a private key for client authentication.\n\n"
                "To fix this:\n"
                "1. Export the certificate from the browser where it works\n"
                "2. Import it into Windows Certificate Store with the 'Mark this key as exportable' option\n"
                "3. Try again",
            )
            return

        self._selected_cert_context = cert_info["cert_store_obj"]
        self.accept()

    def get_selected_certificate(self) -> Optional[tuple[bytes, any]]:
        """
        Get the selected certificate and its context.

        Returns:
            Tuple of (certificate_pem_bytes, cert_store_obj) or None if no selection.
        """
        if not self._selected_cert_context:
            return None

        try:
            # Get the certificate info from our list
            cert_idx = None
            for idx, cert_info in enumerate(self._certificates):
                if cert_info.get("cert_store_obj") == self._selected_cert_context:
                    cert_idx = idx
                    break

            if cert_idx is None:
                # Find by looking at stored context
                for idx, cert_info in enumerate(self._certificates):
                    cert_idx = idx
                    break

            if cert_idx is None:
                raise Exception("Certificate not found in list")

            cert_info = self._certificates[cert_idx]

            # Get certificate in DER format
            cert_der = cert_info["cert_der"]

            # Convert DER to PEM
            import base64

            cert_pem_str = "-----BEGIN CERTIFICATE-----\n"
            b64_cert = base64.b64encode(cert_der).decode("ascii")
            # Add line breaks every 64 characters
            for i in range(0, len(b64_cert), 64):
                cert_pem_str += b64_cert[i : i + 64] + "\n"
            cert_pem_str += "-----END CERTIFICATE-----\n"

            cert_pem = cert_pem_str.encode("utf-8")

            # Return the PEM and the wincertstore object
            return (cert_pem, cert_info["cert_store_obj"])

        except Exception as e:
            import traceback

            traceback.print_exc()
            QMessageBox.critical(self, "Error Exporting Certificate", f"Failed to export certificate:\n{str(e)}")
            return None
