import pytest
import os
from unittest.mock import patch, MagicMock
from PySide6 import QtCore
from app.main import App


class TestApp:
    """Test cases for the main application."""

    @pytest.fixture
    def app(self, qtbot):
        """Create a test app instance."""
        app = App()
        qtbot.addWidget(app)
        return app

    def test_get_instance_id_or_warn_valid(self, app):
        """Test valid instance ID validation."""
        app.instance_input.setText("7107348018")
        result = app._get_instance_id_or_warn()
        assert result == "7107348018"

    def test_get_instance_id_or_warn_empty(self, app):
        """Test empty instance ID handling."""
        app.instance_input.setText("")
        result = app._get_instance_id_or_warn()
        assert result is None
        # Check that error message was set
        assert "Please enter an Instance ID" in app.output.toPlainText()

    def test_get_instance_id_or_warn_too_short(self, app):
        """Test instance ID that is too short."""
        app.instance_input.setText("123")
        result = app._get_instance_id_or_warn()
        assert result is None
        assert "Invalid Instance ID format" in app.output.toPlainText()

    def test_get_instance_id_or_warn_contains_letters(self, app):
        """Test instance ID that contains non-numeric characters."""
        app.instance_input.setText("1234abcd")
        result = app._get_instance_id_or_warn()
        assert result is None
        assert "Invalid Instance ID format" in app.output.toPlainText()

    def test_get_instance_id_or_warn_with_whitespace(self, app):
        """Test instance ID with leading/trailing whitespace."""
        app.instance_input.setText("  7107348018  ")
        result = app._get_instance_id_or_warn()
        assert result == "7107348018"

    def test_get_instance_id_or_warn_minimum_valid(self, app):
        """Test minimum valid instance ID (4 digits)."""
        app.instance_input.setText("1234")
        result = app._get_instance_id_or_warn()
        assert result == "1234"

    def test_handle_api_error_401(self, app):
        """Test 401 authentication error handling."""
        error = "HTTP 401: Invalid token"
        result = app._handle_api_error(error)
        assert "Authentication Failed (401)" in result

    def test_handle_api_error_404(self, app):
        """Test 404 not found error handling."""
        error = "HTTP 404: Resource not found"
        result = app._handle_api_error(error)
        assert "Not Found (404)" in result

    def test_handle_api_error_500(self, app):
        """Test 500 server error handling."""
        error = "HTTP 500: Internal server error"
        result = app._handle_api_error(error)
        assert "Server Error (500)" in result

    def test_handle_api_error_ssl_certificate(self, app):
        """Test SSL certificate error handling."""
        error = "SSL Certificate Error: certificate verify failed"
        result = app._handle_api_error(error)
        assert "SSL Certificate Error" in result

    def test_handle_api_error_timeout(self, app):
        """Test timeout error handling."""
        error = "Request Error: HTTPSConnectionPool(host='api.green-api.com', port=443): Read timed out."
        result = app._handle_api_error(error)
        assert "Request Timeout" in result

    def test_handle_api_error_connection(self, app):
        """Test connection error handling."""
        error = "Request Error: Connection refused"
        result = app._handle_api_error(error)
        assert "Connection Error" in result

    def test_handle_api_error_unknown(self, app):
        """Test unknown error handling."""
        error = "Some unknown error occurred"
        result = app._handle_api_error(error)
        assert "An error occurred" in result
        assert "Details:" in result

    def test_loading_states_ui_elements(self, app):
        """Test that loading state UI elements are properly initialized."""
        # Check that status label exists and has correct initial state
        assert hasattr(app, "status_label")
        assert app.status_label.text() == "Ready"

        # Check that progress bar exists and is initially hidden
        assert hasattr(app, "progress_bar")

    def test_show_hide_progress(self, app):
        """Test progress bar show/hide functionality."""
        # Initially ready state
        assert app.status_label.text() == "Ready"

        # Show progress
        app._show_progress("Testing operation")
        assert "⏳ Testing operation..." in app.status_label.text()
        assert "color: #2196F3" in app.status_label.styleSheet()

        # Hide progress
        app._hide_progress()
        assert app.status_label.text() == "Ready"
        assert "color: #666" in app.status_label.styleSheet()

    @patch("app.main.QtWidgets.QProgressDialog")
    @patch("app.main.get_kibana_session_cookie_with_password")
    def test_authenticate_kibana_progress_dialog_creation(
        self, mock_get_cookie, mock_progress_dialog, app
    ):
        """Test that the authentication progress dialog is created with correct settings."""
        # Mock the progress dialog
        mock_dialog = MagicMock()
        mock_progress_dialog.return_value = mock_dialog

        # Mock the authentication function to return a cookie
        mock_get_cookie.return_value = "test_cookie"

        # Set environment variables to trigger the progress dialog path
        with patch.dict(
            os.environ, {"KIBANA_USER": "testuser", "KIBANA_PASS": "testpass"}
        ):
            # Call the method that creates the progress dialog
            result = app._authenticate_kibana()

        # Verify authentication succeeded
        assert result is True

        # Verify the progress dialog was created with correct parameters
        mock_progress_dialog.assert_called_once_with(
            "Authenticating with Kibana...", "Please wait...", 0, 0, app
        )

        # Verify dialog settings
        mock_dialog.setWindowModality.assert_called_once_with(QtCore.Qt.WindowModal)
        mock_dialog.setWindowTitle.assert_called_once_with("Kibana Authentication")
        mock_dialog.setCancelButton.assert_called_once_with(None)
        mock_dialog.setMinimumDuration.assert_called_once_with(0)
        mock_dialog.setLabelText.assert_called_once_with(
            "Authenticating with Kibana using certificate..."
        )
        mock_dialog.show.assert_called_once()
        mock_dialog.close.assert_called_once()
