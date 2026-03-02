import os
import sys
import ssl
import platform
import subprocess
import socket

def print_header(title):
    print("\n" + "="*len(title))
    print(title)
    print("="*len(title))

def check_python_env():
    print_header("Python Environment")
    print("Python executable:", sys.executable)
    print("Python version:", sys.version)
    try:
        import cryptography
        import requests
        print("cryptography version:", cryptography.__version__)
        print("requests version:", requests.__version__)
    except ImportError as e:
        print("Missing package:", e)

def check_ssl():
    print_header("SSL/OpenSSL")
    print("ssl.OPENSSL_VERSION:", ssl.OPENSSL_VERSION)
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname="elk.prod.greenapi.org") as s:
            s.settimeout(5)
            s.connect(("elk.prod.greenapi.org", 443))
            print("SSL handshake to elk.prod.greenapi.org:443 succeeded.")
    except Exception as e:
        print("SSL handshake failed:", e)

def check_cert_store():
    print_header("Windows Certificate Store (Current User)")
    if platform.system() != "Windows":
        print("Not running on Windows, skipping cert store check.")
        return
    try:
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", "Get-ChildItem -Path Cert:\\CurrentUser\\My | Format-List -Property Subject,Thumbprint,HasPrivateKey"],
            text=True,
            timeout=10
        )
        print(output)
    except Exception as e:
        print("Failed to query certificate store:", e)

def check_proxy():
    print_header("Proxy/Network Environment")
    for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        print(f"{var}:", os.environ.get(var))
    try:
        import requests
        resp = requests.get("https://elk.prod.greenapi.org/api/status", timeout=10)
        print("Kibana status code:", resp.status_code)
    except Exception as e:
        print("Kibana API request failed:", e)

def check_time():
    print_header("System Time")
    from datetime import datetime
    print("System time:", datetime.now())

if __name__ == "__main__":
    check_python_env()
    check_ssl()
    check_cert_store()
    check_proxy()
    check_time()