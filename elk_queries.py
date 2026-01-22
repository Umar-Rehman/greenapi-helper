import re
import requests
import os
from dotenv import load_dotenv
from api_url_resolver import resolve_api_url

load_dotenv(".env.local")

KIBANA_URL = "https://elk.prod.greenapi.org"
KIBANA_COOKIE = os.getenv("KIBANA_COOKIE")

CLIENT_CERT = "client.crt"
CLIENT_KEY = "client.key"

SEARCH_SIZE = 50
TIME_GTE = "now-7d"

# ---------- Helper Functions ---------- #

def get_api_token(instance_id: str) -> str:
    """
    Docstring for get_api_token
    
    :param instance_id: Description
    :type instance_id: str
    :return: Description
    :rtype: str
    """
    token_re = re.compile(
        rf"(?:/| )waInstance{re.escape(instance_id)}/[A-Za-z]+/([a-fA-F0-9]{{32,}})"
    )

    proxy_url = f"{KIBANA_URL}/api/console/proxy"

    resp = requests.post(
        proxy_url,
        params={"path": "logs-*,filebeat-*/_search", "method": "GET"},
        json={
            "size": SEARCH_SIZE,
            "track_total_hits": False,
            "sort": [{"@timestamp": {"order": "desc"}}],
            "query": {
                "bool": {
                    "filter": [
                        {"range": {"@timestamp": {"gte": TIME_GTE}}},
                        {"query_string": {"query": f"waInstance{instance_id}"}},
                    ]
                }
            },
            "_source": ["@timestamp", "uri", "message"],
        },
        headers={
            "kbn-xsrf": "true",
            "Cookie": KIBANA_COOKIE,
            "Content-Type": "application/json",
        },
        cert=(CLIENT_CERT, CLIENT_KEY),
        verify=True, # Set to False for debugging with self-signed certs
        timeout=60,
    )

    if resp.status_code != 200:
        return f"HTTP {resp.status_code}: {resp.text}"

    for hit in resp.json().get("hits", {}).get("hits", []):
        src = hit.get("_source", {})
        for text in (src.get("uri", ""), src.get("message", "")):
            if not text:
                continue
            m = token_re.search(text)
            if m:
                return m.group(1)

    return "apiToken not found"

def send_request(url: str) -> str:
    resp = requests.get(
    url,
    headers={"accept": "application/json"},
    cert=(CLIENT_CERT, CLIENT_KEY),
    verify=True,  # Set to False for debugging with self-signed certs
    timeout=60,
    )
    if resp.status_code != 200:
        return f"HTTP {resp.status_code}: {resp.text}"
    
    return resp.text

def _build_url(api_url: str, instance_id: str, path: str) -> str:
    return f"{api_url}/waInstance{instance_id}/{path}"

# ---------- Account Calls ---------- #

def get_instance_state(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"getStateInstance/{api_token}")
    return send_request(url)

def get_instance_settings(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"getSettings/{api_token}")
    return send_request(url)

def set_instance_settings(instance_id: str, api_token: str, settings: dict) -> str:
    """
    Calls:
      {{apiUrl}}/waInstance{{idInstance}}/setSettings/{{apiTokenInstance}}
    """
    api_url = resolve_api_url(instance_id)
    url = f"{api_url}/waInstance{instance_id}/setSettings/{api_token}"
    output = send_request(url)
    return output

def logout_instance(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"logout/{api_token}")
    return send_request(url)

def reboot_instance(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"reboot/{api_token}")
    return send_request(url)

# ---------- Journal Calls ---------- #

def get_incoming_msgs_journal(api_url: str, instance_id: str, api_token: str, minutes: int = 1440) -> str:
    url = _build_url(api_url, instance_id, f"lastIncomingMessages/{api_token}?minutes={minutes}")
    return send_request(url)

def get_outgoing_msgs_journal(api_url: str, instance_id: str, api_token: str, minutes: int = 1440) -> str:
    url = _build_url(api_url, instance_id, f"lastOutgoingMessages/{api_token}?minutes={minutes}")
    return send_request(url)

# ---------- Queue Calls ---------- #

def get_msg_queue_count(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"getMessagesCount/{api_token}")
    return send_request(url)

def get_msg_queue(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"showMessagesQueue/{api_token}")
    return send_request(url)

def clear_msg_queue_to_send(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"clearMessagesQueue/{api_token}")
    return send_request(url)

def get_webhook_count(api_url: str, instance_id: str, api_token: str) -> str:
    url = _build_url(api_url, instance_id, f"getWebhooksCount/{api_token}")
    return send_request(url)
