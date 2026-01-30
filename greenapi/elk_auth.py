import re
import requests
import os
from dotenv import load_dotenv

load_dotenv(".env.local")

KIBANA_URL = "https://elk.prod.greenapi.org"
KIBANA_COOKIE = os.getenv("KIBANA_COOKIE")
CLIENT_CERT = "client.crt"
CLIENT_KEY = "client.key"
SEARCH_SIZE = 50
TIME_GTE = "now-7d"

# Helper functions

def get_api_token(instance_id: str) -> str:
    """
    Retrieve the API token for the given instance_id by querying the ELK stack. If not found, returns "apiToken not found".
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
