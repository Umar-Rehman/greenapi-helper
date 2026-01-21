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

def prepare_request(instance_id:str) -> tuple[str, str]:
    """
    Prepares the api_url and api_token for the given instance_id.
    Returns a tuple of (api_url, api_token).
    """
    api_token = get_api_token(instance_id)
    if not api_token or api_token == "":
        return None, api_token  # Return error message
    api_url = resolve_api_url(instance_id)
    return api_url, api_token

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

# ---------- Account Calls ---------- #

def get_instance_state(instance_id: str) -> str:
    """
    Calls:
        {{apiUrl}}/waInstance{{idInstance}}/getStateInstance/{{apiTokenInstance}}
    """
    api_url, api_token = prepare_request(instance_id)
    url = f"{api_url}/waInstance{instance_id}/getStateInstance/{api_token}"
    output = send_request(url)
    return output

def get_instance_settings(instance_id: str) -> str:
    """
    Calls:
        {{apiUrl}}/waInstance{{idInstance}}/getSettings/{{apiTokenInstance}}
    """
    api_url, api_token = prepare_request(instance_id)
    url = f"{api_url}/waInstance{instance_id}/getSettings/{api_token}"
    output = send_request(url)
    return output

def set_instance_settings(instance_id: str, api_token: str, settings: dict) -> str:
    """
    Calls:
      {{apiUrl}}/waInstance{{idInstance}}/setSettings/{{apiTokenInstance}}
    """
    api_url = resolve_api_url(instance_id)
    url = f"{api_url}/waInstance{instance_id}/setSettings/{api_token}"
    output = send_request(url)
    return output

def reboot_instance(instance_id: str, api_token: str) -> str:
    """
    Calls:
      {apiUrl}/waInstance{idInstance}/reboot/{apiTokenInstance}
    """
    api_url = resolve_api_url(instance_id)
    url = f"{api_url}/waInstance{instance_id}/reboot/{api_token}"
    output = send_request(url)
    return output

def logout_instance(instance_id: str, api_token: str) -> str:
    """
    Calls:
      {{apiUrl}}/waInstance{{idInstance}}/logout/{{apiTokenInstance}}
    """
    api_url = resolve_api_url(instance_id)
    url = f"{api_url}/waInstance{instance_id}/logout/{api_token}"
    output = send_request(url)
    return output

# ---------- Journal Calls ---------- #

def get_incoming_msgs_journal(instance_id: str) -> str:
    """
    Calls:
        {{apiUrl}}/waInstance{{idInstance}}/lastIncomingMessages/{{apiTokenInstance}}?minutes=1440
    """
    api_url, api_token = prepare_request(instance_id)
    url = f"{api_url}/waInstance{instance_id}/lastIncomingMessages/{api_token}?minutes=1440"
    output = send_request(url)
    return output

def get_outgoing_msgs_journal(instance_id: str) -> str:
    """
    Calls:
        {{apiUrl}}/waInstance{{idInstance}}/lastOutgoingMessages/{{apiTokenInstance}}?minutes=1440
    """
    api_url, api_token = prepare_request(instance_id)
    url = f"{api_url}/waInstance{instance_id}/lastOutgoingMessages/{api_token}?minutes=1440"
    output = send_request(url)
    return output

# ---------- Queue Calls ---------- #

def get_msg_queue_count(instance_id: str) -> int:
    """
    Calls:
        {{apiUrl}}/waInstance{{idInstance}}/getMessagesCount/{{apiTokenInstance}}
    """
    api_url, api_token = prepare_request(instance_id)
    url = f"{api_url}/waInstance{instance_id}/getMessagesCount/{api_token}"
    output = send_request(url)
    return output

def get_msg_queue(instance_id: str) -> str:
    """Calls:
        {{apiUrl}}/waInstance{{idInstance}}/showMessagesQueue/{{apiTokenInstance}}
    """
    api_url, api_token = prepare_request(instance_id)
    url = f"{api_url}/waInstance{instance_id}/showMessagesQueue/{api_token}"
    output = send_request(url)
    return output

def clear_msg_queue_to_send(instance_id: str, api_token: str) -> str:
    """
    Calls:
        {{apiUrl}}/waInstance{{idInstance}}/clearMessagesQueue/{{apiTokenInstance}}
    """
    api_url = resolve_api_url(instance_id)
    url = f"{api_url}/waInstance{instance_id}/clearMessagesQueue/{api_token}"
    output = send_request(url)
    return output

def get_webhook_count(instance_id: str) -> int:
    """
    Calls:
        {{apiUrl}}/waInstance{{idInstance}}/getWebhooksCount/{{apiTokenInstance}}
    """
    api_url, api_token = prepare_request(instance_id)
    url = f"{api_url}/waInstance{instance_id}/getWebhooksCount/{api_token}"
    output = send_request(url)
    return output
