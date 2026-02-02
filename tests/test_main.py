import pytest
from unittest.mock import patch, MagicMock
from PySide6 import QtWidgets
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

    def test_get_instance_id_or_warn_starts_with_letters(self, app):
        """Test instance ID that doesn't start with digits."""
        app.instance_input.setText("abcd1234")
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
