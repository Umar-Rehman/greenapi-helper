import requests
from pathlib import Path
from urllib.parse import urlencode

# --------- Configuration ---------- #

CLIENT_CERT = Path("client.crt")
CLIENT_KEY = Path("client.key")

VERIFY_TLS = True
TIMEOUT_SECONDS = 60

# --------- Helper Functions ---------- #

def _build_url(api_url: str, instance_id: str, path: str) -> str:
    return f"{api_url}/waInstance{instance_id}/{path}"

def send_request(method: str, url: str, *, json_body: dict | None = None) -> str:
    resp = requests.request(
        method=method.upper(),
        url=url,
        headers={"accept": "application/json"},
        json=json_body,
        cert=(str(CLIENT_CERT), str(CLIENT_KEY)),
        verify=VERIFY_TLS,
        timeout=TIMEOUT_SECONDS,
    )

    if resp.status_code != 200:
        return f"HTTP {resp.status_code}: {resp.text}"

    return resp.text

def make_api_call(api_url: str, instance_id: str, api_token: str, path: str, method: str, json_body=None, query_params=None) -> str:
    url = _build_url(api_url, instance_id, f"{path}/{api_token}")
    if query_params:
        from urllib.parse import urlencode
        url += "?" + urlencode(query_params)
    return send_request(method, url, json_body=json_body)

# ---------- Account Calls ---------- #

def get_instance_state(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "getStateInstance", "GET")

def get_instance_settings(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "getSettings", "GET")

def set_instance_settings(api_url: str, instance_id: str, api_token: str, settings: dict) -> str:
    return make_api_call(api_url, instance_id, api_token, "setSettings", "POST", json_body=settings)

def logout_instance(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "logout", "GET")

def reboot_instance(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "reboot", "GET")

def get_qr_code(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "qr", "GET")

def get_wa_settings(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "getWASettings", "GET")

# ---------- Journal Calls ---------- #

def get_incoming_msgs_journal(api_url: str, instance_id: str, api_token: str, minutes: int = 1440) -> str:
    return make_api_call(api_url, instance_id, api_token, "lastIncomingMessages", "GET", query_params={"minutes": minutes})

def get_outgoing_msgs_journal(api_url: str, instance_id: str, api_token: str, minutes: int = 1440) -> str:
    return make_api_call(api_url, instance_id, api_token, "lastOutgoingMessages", "GET", query_params={"minutes": minutes})

def get_chat_history(api_url: str, instance_id: str, api_token: str, chat_id: str, count: int = 10) -> str:
    return make_api_call(api_url, instance_id, api_token, "getChatHistory", "POST", json_body={"chatId": chat_id, "count": count})

def get_message(api_url: str, instance_id: str, api_token: str, chat_id: str, id_message: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "getMessage", "POST", json_body={"chatId": chat_id, "idMessage": id_message})

# ---------- Queue Calls ---------- #

def get_msg_queue_count(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "getMessagesCount", "GET")

def get_msg_queue(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "showMessagesQueue", "GET")

def clear_msg_queue_to_send(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "clearMessagesQueue", "GET")

def get_webhook_count(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "getWebhooksCount", "GET")

def clear_webhooks_queue(api_url: str, instance_id: str, api_token: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "clearWebhooksQueue", "DELETE")

# ---------- Status Calls ---------- #

def get_outgoing_statuses(api_url: str, instance_id: str, api_token: str, minutes: int = 1440) -> str:
    return make_api_call(api_url, instance_id, api_token, "getOutgoingStatuses", "GET", query_params={"minutes": minutes})

def get_incoming_statuses(api_url: str, instance_id: str, api_token: str, minutes: int = 1440) -> str:
    return make_api_call(api_url, instance_id, api_token, "getIncomingStatuses", "GET", query_params={"minutes": minutes})

def get_status_statistic(api_url: str, instance_id: str, api_token: str, id_message: str) -> str:
    return make_api_call(api_url, instance_id, api_token, "getStatusStatistic", "GET", query_params={"idMessage": id_message})