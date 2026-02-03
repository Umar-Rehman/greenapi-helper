"""Additional tests to increase coverage of core business logic."""

from unittest.mock import patch
from greenapi import client
from greenapi.api_url_resolver import resolve_api_url


class TestClientAdditional:
    """Additional tests for client.py to increase coverage."""

    def test_get_instance_settings(self):
        """Test get_instance_settings."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = {"webhookUrl": "https://example.com", "outgoingWebhook": "yes"}
            result = client.get_instance_settings("https://api.green-api.com", "1234", "token123")
            assert "webhookUrl" in result
            mock_send.assert_called_once()

    def test_set_instance_settings(self):
        """Test set_instance_settings."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = {"success": True}
            settings = {"webhookUrl": "https://new.com"}
            result = client.set_instance_settings("https://api.green-api.com", "1234", "token123", settings)
            assert result == {"success": True}
            mock_send.assert_called_once()

    def test_get_wa_settings(self):
        """Test get_wa_settings."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = {"avatar": "base64data", "phone": "1234567890"}
            result = client.get_wa_settings("https://api.green-api.com", "1234", "token123")
            assert "avatar" in result
            mock_send.assert_called_once()

    def test_logout_instance(self):
        """Test logout_instance."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = {"isLogged": False}
            result = client.logout_instance("https://api.green-api.com", "1234", "token123")
            assert result["isLogged"] is False
            mock_send.assert_called_once()

    def test_reboot_instance(self):
        """Test reboot_instance."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = {"success": True}
            result = client.reboot_instance("https://api.green-api.com", "1234", "token123")
            assert result["success"] is True
            mock_send.assert_called_once()

    def test_get_qr_code(self):
        """Test get_qr_code."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = {"type": "qrCode", "message": "qr_data_here"}
            result = client.get_qr_code("https://api.green-api.com", "1234", "token123")
            assert result["type"] == "qrCode"
            mock_send.assert_called_once()

    def test_get_incoming_statuses(self):
        """Test get_incoming_statuses."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = [{"idMessage": "123", "status": "delivered"}]
            result = client.get_incoming_statuses("https://api.green-api.com", "1234", "token123", minutes=60)
            assert isinstance(result, list)
            mock_send.assert_called_once()

    def test_get_outgoing_statuses(self):
        """Test get_outgoing_statuses."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = [{"idMessage": "456", "status": "sent"}]
            result = client.get_outgoing_statuses("https://api.green-api.com", "1234", "token123", minutes=120)
            assert isinstance(result, list)
            mock_send.assert_called_once()

    def test_get_incoming_msgs_journal(self):
        """Test get_incoming_msgs_journal."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = [{"type": "incoming", "textMessage": "Hello"}]
            result = client.get_incoming_msgs_journal("https://api.green-api.com", "1234", "token123", minutes=30)
            assert isinstance(result, list)
            mock_send.assert_called_once()

    def test_get_outgoing_msgs_journal(self):
        """Test get_outgoing_msgs_journal."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = [{"type": "outgoing", "textMessage": "Hi"}]
            result = client.get_outgoing_msgs_journal("https://api.green-api.com", "1234", "token123", minutes=45)
            assert isinstance(result, list)
            mock_send.assert_called_once()

    def test_get_chat_history(self):
        """Test get_chat_history."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = [{"idMessage": "789", "textMessage": "Test"}]
            result = client.get_chat_history("https://api.green-api.com", "1234", "token123", "1234567890@c.us", 10)
            assert isinstance(result, list)
            mock_send.assert_called_once()

    def test_get_message(self):
        """Test get_message."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = {"idMessage": "msg123", "textMessage": "Content"}
            result = client.get_message("https://api.green-api.com", "1234", "token123", "chat@c.us", "msg123")
            assert result["idMessage"] == "msg123"
            mock_send.assert_called_once()

    def test_get_msg_queue_count(self):
        """Test get_msg_queue_count."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = {"count": 5}
            result = client.get_msg_queue_count("https://api.green-api.com", "1234", "token123")
            assert result["count"] == 5
            mock_send.assert_called_once()

    def test_get_msg_queue(self):
        """Test get_msg_queue."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = [{"message": "queued1"}, {"message": "queued2"}]
            result = client.get_msg_queue("https://api.green-api.com", "1234", "token123")
            assert len(result) == 2
            mock_send.assert_called_once()

    def test_clear_msg_queue_to_send(self):
        """Test clear_msg_queue_to_send."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = {"success": True}
            result = client.clear_msg_queue_to_send("https://api.green-api.com", "1234", "token123")
            assert result["success"] is True
            mock_send.assert_called_once()

    def test_get_webhook_count(self):
        """Test get_webhook_count."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = {"count": 3}
            result = client.get_webhook_count("https://api.green-api.com", "1234", "token123")
            assert result["count"] == 3
            mock_send.assert_called_once()

    def test_clear_webhooks_queue(self):
        """Test clear_webhooks_queue."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = {"success": True}
            result = client.clear_webhooks_queue("https://api.green-api.com", "1234", "token123")
            assert result["success"] is True
            mock_send.assert_called_once()

    def test_get_status_statistic(self):
        """Test get_status_statistic."""
        with patch("greenapi.client.send_request") as mock_send:
            mock_send.return_value = {"sent": 100, "delivered": 95, "read": 80}
            result = client.get_status_statistic("https://api.green-api.com", "1234", "token123", "msg_id_123")
            assert result["sent"] == 100
            mock_send.assert_called_once()


class TestApiUrlResolverAdditional:
    """Additional tests for api_url_resolver.py."""

    def test_resolve_api_url_with_direct_host(self):
        """Test that instances with direct_host return the correct URL."""
        # 1103 has direct_host
        url = resolve_api_url("1103")
        assert url == "https://1103.api.green-api.com"

    def test_resolve_api_url_7103_direct(self):
        """Test 7103 direct host."""
        url = resolve_api_url("7103")
        assert url == "https://7103.api.greenapi.com"

    def test_resolve_api_url_9903_direct(self):
        """Test 9903 direct host."""
        url = resolve_api_url("9903")
        assert url == "https://9903.api.green-api.com"

    def test_resolve_api_url_9906_direct(self):
        """Test 9906 direct host."""
        url = resolve_api_url("9906")
        assert url == "https://9906.api.green-api.com"

    def test_resolve_api_url_prefix_99(self):
        """Test 99XX prefix (like 9901, 9902)."""
        url = resolve_api_url("9901")
        assert url == "https://api.p03.green-api.com"

    def test_resolve_api_url_prefix_33(self):
        """Test 33XX prefix."""
        url = resolve_api_url("3301")
        assert url == "https://api.green-api.com"

    def test_resolve_api_url_prefix_55(self):
        """Test 55XX prefix."""
        url = resolve_api_url("5501")
        assert url == "https://api.green-api.com"

    def test_resolve_api_url_5700_direct(self):
        """Test 5700 has direct host."""
        url = resolve_api_url("5700")
        assert url == "https://5700.api.green-api.com"

    def test_resolve_api_url_7700_direct(self):
        """Test 7700 has direct host."""
        url = resolve_api_url("7700")
        assert url == "https://7700.api.greenapi.com"

    def test_resolve_api_url_3100_direct(self):
        """Test 3100 has direct host."""
        url = resolve_api_url("3100")
        assert url == "https://3100.api.green-api.com/v3"

    def test_resolve_api_url_1101_default(self):
        """Test 1101 uses default."""
        url = resolve_api_url("1101")
        assert url == "https://api.green-api.com"

    def test_resolve_api_url_1102_default(self):
        """Test 1102 uses default."""
        url = resolve_api_url("1102")
        assert url == "https://api.green-api.com"

    def test_resolve_api_url_2204_default(self):
        """Test 2204 uses default."""
        url = resolve_api_url("2204")
        assert url == "https://api.greenapi.com"
