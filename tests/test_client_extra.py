from greenapi import client
from unittest.mock import patch
import pytest

def test_is_telegram_instance():
    # Should be True for 4100 and 4500
    assert client.is_telegram_instance("https://4100.api.green-api.com")
    assert client.is_telegram_instance("https://4500.api.green-api.com")
    # Should be False for other pools
    assert not client.is_telegram_instance("https://7103.api.greenapi.com")
    assert not client.is_telegram_instance("https://api.green-api.com/v3")

def test_get_account_settings_telegram():
    # Should call getAccountSettings for 4100/4500 (Telegram)
    with patch("greenapi.client.make_api_call") as mock_call:
        mock_call.side_effect = ["{}", "telegram_settings"]
        result = client.get_account_settings("https://4100.api.green-api.com", "4100123456", "token")
        assert result == "telegram_settings"
        assert mock_call.call_args_list[1][0][3] == "getAccountSettings"

def test_get_account_settings_max():
    # Should call getAccountSettings for MAX (v3 in URL)
    with patch("greenapi.client.make_api_call") as mock_call:
        mock_call.side_effect = ["{}", "max_settings"]
        result = client.get_account_settings("https://api.green-api.com/v3", "3100123456", "token")
        assert result == "max_settings"
        assert mock_call.call_args_list[1][0][3] == "getAccountSettings"

def test_get_account_settings_whatsapp():
    # Should call getWASettings for WhatsApp (not Telegram/MAX)
    with patch("greenapi.client.make_api_call") as mock_call:
        mock_call.side_effect = ["{}", "wa_settings"]
        result = client.get_account_settings("https://api.greenapi.com", "7103123456", "token")
        assert result == "wa_settings"
        assert mock_call.call_args_list[1][0][3] == "getWASettings"
