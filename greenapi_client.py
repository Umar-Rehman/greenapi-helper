import requests

CLIENT_CERT = "client.crt"
CLIENT_KEY = "client.key"

#--------- Helper Functions ---------- #

def _build_url(api_url: str, instance_id: str, path: str) -> str:
    return f"{api_url}/waInstance{instance_id}/{path}"

def send_request(method: str, url: str, *, json_body: dict | None = None) -> str:
    resp = requests.request(
        method=method.upper(),
        url=url,
        headers={"accept": "application/json"},
        json=json_body,
        cert=(CLIENT_CERT, CLIENT_KEY),
        verify=True,
        timeout=60,
    )

    if resp.status_code != 200:
        return f"HTTP {resp.status_code}: {resp.text}"

    return resp.text

# ---------- Account Calls ---------- #

def get_instance_state(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"getStateInstance/{api_token}")
    return send_request("GET", url)

def get_instance_settings(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"getSettings/{api_token}")
    return send_request("GET", url)

def set_instance_settings(api_url: str, instance_id: str, api_token: str, settings: dict) -> str:
    url = _build_url(api_url, instance_id, f"setSettings/{api_token}")
    return send_request("POST", url, json_body=settings)

def logout_instance(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"logout/{api_token}")
    return send_request("GET", url)

def reboot_instance(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"reboot/{api_token}")
    return send_request("GET", url)

# ---------- Journal Calls ---------- #

def get_incoming_msgs_journal(api_url: str, instance_id: str, api_token: str, minutes: int = 1440) -> str:
    url = _build_url(api_url, instance_id, f"lastIncomingMessages/{api_token}?minutes={minutes}")
    return send_request("GET", url)

def get_outgoing_msgs_journal(api_url: str, instance_id: str, api_token: str, minutes: int = 1440) -> str:
    url = _build_url(api_url, instance_id, f"lastOutgoingMessages/{api_token}?minutes={minutes}")
    return send_request("GET", url)

# ---------- Queue Calls ---------- #

def get_msg_queue_count(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"getMessagesCount/{api_token}")
    return send_request("GET", url)

def get_msg_queue(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"showMessagesQueue/{api_token}")
    return send_request("GET", url)

def clear_msg_queue_to_send(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"clearMessagesQueue/{api_token}")
    return send_request("GET", url)

def get_webhook_count(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"getWebhooksCount/{api_token}")
    return send_request("GET", url)