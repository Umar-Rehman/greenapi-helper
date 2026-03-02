import os
import json
import requests
import traceback

from greenapi import elk_auth


def short(s, n=1000):
    if s is None:
        return "<empty>"
    t = str(s)
    return t if len(t) <= n else t[:n] + "...[truncated]"


def main():
    print("Environment KIBANA_URL:", os.getenv("KIBANA_URL"))
    print("Requests version:", requests.__version__)

    url = os.getenv("KIBANA_URL", "https://elk.prod.greenapi.org")
    target = f"{url}/api/status"

    print("\n== Raw requests GET to /api/status ==")
    try:
        resp = requests.get(target, timeout=15)
        print("Status code:", resp.status_code)
        print("Headers:\n", json.dumps(dict(resp.headers), indent=2))
        print("Body (truncated):\n", short(resp.text, 2000))
    except Exception:
        print("Request failed:")
        traceback.print_exc()

    print("\n== Attempting automated get_kibana_session_cookie() ==")
    try:
        cookie = elk_auth.get_kibana_session_cookie()
        print("Resulting cookie:", short(cookie, 1000))
    except Exception:
        print("get_kibana_session_cookie raised exception:")
        traceback.print_exc()


if __name__ == '__main__':
    main()
