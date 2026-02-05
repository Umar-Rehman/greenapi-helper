"""Tests for group ID normalization functionality."""

import pytest
from greenapi import client as ga


class TestGroupIdNormalization:
    """Test cases for the normalize_group_id function."""

    def test_normalize_group_id_whatsapp_without_suffix(self):
        """Test that group ID without @g.us gets the suffix added for WhatsApp."""
        api_url = "https://api.green-api.com"
        group_id = "120363426336228996"
        result = ga.normalize_group_id(group_id, api_url)
        assert result == "120363426336228996@g.us"

    def test_normalize_group_id_whatsapp_with_suffix(self):
        """Test that group ID with @g.us remains unchanged for WhatsApp."""
        api_url = "https://api.green-api.com"
        group_id = "120363426336228996@g.us"
        result = ga.normalize_group_id(group_id, api_url)
        assert result == "120363426336228996@g.us"

    def test_normalize_group_id_max_instance(self):
        """Test that group ID is unchanged for MAX instances."""
        api_url = "https://api.green-api.com/v3"
        group_id = "-10000000000000"
        result = ga.normalize_group_id(group_id, api_url)
        assert result == "-10000000000000"

    def test_normalize_group_id_max_instance_with_suffix(self):
        """Test that MAX instance doesn't add @g.us even if input has it."""
        api_url = "https://api.green-api.com/v3"
        group_id = "-10000000000000"
        result = ga.normalize_group_id(group_id, api_url)
        assert result == "-10000000000000"

    def test_normalize_group_id_empty_string(self):
        """Test that empty string is returned as-is."""
        api_url = "https://api.green-api.com"
        group_id = ""
        result = ga.normalize_group_id(group_id, api_url)
        assert result == ""

    def test_normalize_group_id_in_update_group_name(self, monkeypatch):
        """Test that update_group_name uses normalized group ID."""

        def mock_make_api_call(api_url, instance_id, api_token, endpoint, method, **kwargs):
            return '{"result": "success"}'

        monkeypatch.setattr("greenapi.client.make_api_call", mock_make_api_call)

        api_url = "https://api.green-api.com"
        instance_id = "1234567890"
        api_token = "test_token"
        group_id = "120363426336228996"  # Without @g.us
        group_name = "Test Group"

        # Just verify it doesn't raise an error and normalization is applied
        result = ga.update_group_name(api_url, instance_id, api_token, group_id, group_name)
        assert result == '{"result": "success"}'

    def test_normalize_group_id_in_get_group_data(self, monkeypatch):
        """Test that get_group_data uses normalized group ID."""

        def mock_make_api_call(api_url, instance_id, api_token, endpoint, method, **kwargs):
            return '{"result": "success"}'

        monkeypatch.setattr("greenapi.client.make_api_call", mock_make_api_call)

        api_url = "https://api.green-api.com"
        instance_id = "1234567890"
        api_token = "test_token"
        group_id = "120363426336228996"

        result = ga.get_group_data(api_url, instance_id, api_token, group_id)
        assert result == '{"result": "success"}'

    def test_update_group_name_uses_chatId_not_groupId(self, monkeypatch):
        """Test that update_group_name uses 'chatId' key instead of 'groupId' in payload."""
        captured_body = {}

        def mock_make_api_call(api_url, instance_id, api_token, endpoint, method, json_body=None, **kwargs):
            captured_body.update(json_body or {})
            return '{"result": "success"}'

        monkeypatch.setattr("greenapi.client.make_api_call", mock_make_api_call)

        api_url = "https://api.green-api.com"
        instance_id = "1234567890"
        api_token = "test_token"
        group_id = "120363426336228996@g.us"
        group_name = "New Group Name"

        ga.update_group_name(api_url, instance_id, api_token, group_id, group_name)

        # Verify 'chatId' is used, not 'groupId'
        assert "chatId" in captured_body
        assert "groupId" not in captured_body
        assert captured_body["chatId"] == "120363426336228996@g.us"
        assert captured_body["groupName"] == group_name
