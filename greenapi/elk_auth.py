import re
import requests
import os
import json
import platform
import subprocess
from typing import Optional, Tuple
from dotenv import load_dotenv

load_dotenv(".env.local")

KIBANA_URL = "https://elk.prod.greenapi.org"
SEARCH_SIZE = 50
TIME_GTE = "now-7d"
KIBANA_AUTH_PATHS = ["/internal/security/me", "/api/security/v1/me", "/api/status"]

# Helper functions

def get_kibana_session_cookie(
    cert_files: Optional[Tuple[str, str]] = None
) -> Optional[str]:
    """
    Automatically authenticate to Kibana using certificate and retrieve session cookie.
    
    Tries multiple approaches:
    1. Certificate-only mode (Windows handles key in background)
    2. With extracted private key
    3. Returns None if all methods fail (fallback to manual entry)
    
    Args:
        cert_files: Tuple of (cert_path, key_path) for client certificates
    
    Returns:
        Session cookie string if successful, None otherwise
    """
    
    # Strategy 1: Try WinHTTP with cert from store (no key export)
    if platform.system() == "Windows":
        cookie = _try_kibana_auth_winhttp(cert_files)
        if cookie:
            return cookie

    # Strategy 2: Try Windows PowerShell with cert from store (no key export)
    if platform.system() == "Windows":
        cookie = _try_kibana_auth_powershell(cert_files)
        if cookie:
            return cookie

    # Strategy 3: Try certificate-only mode (let Windows/SSL handle the key)
    cookie = _try_kibana_auth_cert_only(cert_files)
    if cookie:
        return cookie
    
    # Strategy 4: Try with full private key export
    cookie = _try_kibana_auth_with_key(cert_files)
    if cookie:
        return cookie
    
    # Strategy 3: Failed - return None for fallback to manual entry
    return None


def get_kibana_session_cookie_with_password(
    username: str,
    password: str,
    cert_files: Optional[Tuple[str, str]] = None,
) -> Optional[str]:
    """Authenticate to Kibana using username/password + cert and return session cookie."""
    if platform.system() != "Windows":
        return None
    return _try_kibana_auth_powershell_login(username, password, cert_files)


def _try_kibana_auth_cert_only(cert_files: Optional[Tuple[str, str]]) -> Optional[str]:
    """Try to authenticate using just the certificate (Windows handles key)."""
    try:
        cert = cert_files or ("client.crt", "client.key")
        
        # Use only the cert file, not the key - let Windows SSL handle it
        cert_only = cert[0] if isinstance(cert, tuple) else cert
        
        for path in KIBANA_AUTH_PATHS:
            resp = requests.get(
                f"{KIBANA_URL}{path}",
                cert=cert_only,  # Just the cert, no key
                verify=True,
                timeout=10,
                allow_redirects=True
            )
            
            if resp.status_code in (200, 302, 401, 403):
                cookie = _extract_session_cookie(resp)
                if cookie:
                    return cookie
        
        return None
            
    except Exception:
        return None

def _try_kibana_auth_powershell(cert_files: Optional[Tuple[str, str]]) -> Optional[str]:
    """Try to authenticate using PowerShell and a cert from Windows store (no key export)."""
    try:
        thumbprint = _get_thumbprint_from_cert_files(cert_files)
        if not thumbprint:
            return None

        script = f"""
$ErrorActionPreference = 'Stop'
$thumb = '{thumbprint}'
$cert = Get-Item -Path ('Cert:\\CurrentUser\\My\\' + $thumb) -ErrorAction Stop
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$paths = @({', '.join([f"'{p}'" for p in KIBANA_AUTH_PATHS])})
foreach ($p in $paths) {{
    $uri = '{KIBANA_URL}' + $p
    $resp = Invoke-WebRequest -Uri $uri -Certificate $cert -WebSession $session -UseBasicParsing -TimeoutSec 10
    $cookies = $session.Cookies.GetCookies([Uri]$uri)
    if ($cookies.Count -gt 0) {{
        ($cookies | ForEach-Object {{ "$($_.Name)=$($_.Value)" }}) -join '; '
        break
    }}
}}
"""

        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20
        )

        if result.returncode != 0:
            return None

        cookie = (result.stdout or "").strip()
        if cookie:
            return cookie

        return None

    except Exception:
        return None


def _try_kibana_auth_powershell_login(
        username: str,
        password: str,
        cert_files: Optional[Tuple[str, str]],
) -> Optional[str]:
    """Use PowerShell to log into Kibana with username/password and cert-store auth."""
    try:
        thumbprint = _get_thumbprint_from_cert_files(cert_files)
        if not thumbprint:
            return None

        provider_name = os.getenv("KIBANA_PROVIDER_NAME", "basic")
        provider_type = os.getenv("KIBANA_PROVIDER_TYPE", "basic")

        script = f"""
$ErrorActionPreference = 'Stop'
$thumb = '{thumbprint}'
$cert = Get-Item -Path ('Cert:\\CurrentUser\\My\\' + $thumb) -ErrorAction Stop
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$base = '{KIBANA_URL}'
$headers = @{{ 'kbn-xsrf' = 'true'; 'Content-Type' = 'application/json' }}
$user = $env:KIBANA_USER
$pass = $env:KIBANA_PASS
$ptype = $env:KIBANA_PROVIDER_TYPE
$pname = $env:KIBANA_PROVIDER_NAME

$body = @{{
    providerType = $ptype
    providerName = $pname
    currentURL = "$base/app/home"
    params = @{{ username = $user; password = $pass }}
}} | ConvertTo-Json -Depth 6

try {{
    Invoke-WebRequest -Uri ($base + '/internal/security/login') -Method POST -Body $body -Headers $headers -Certificate $cert -WebSession $session -UseBasicParsing -TimeoutSec 10 | Out-Null
}} catch {{
    $body2 = @{{ username = $user; password = $pass }} | ConvertTo-Json
    Invoke-WebRequest -Uri ($base + '/api/security/v1/login') -Method POST -Body $body2 -Headers $headers -Certificate $cert -WebSession $session -UseBasicParsing -TimeoutSec 10 | Out-Null
}}

foreach ($p in @({', '.join([f"'{p}'" for p in KIBANA_AUTH_PATHS])})) {{
    $uri = $base + $p
    $cookies = $session.Cookies.GetCookies([Uri]$uri)
    if ($cookies.Count -gt 0) {{
        ($cookies | ForEach-Object {{ "$($_.Name)=$($_.Value)" }}) -join '; '
        break
    }}
}}
"""

        env = os.environ.copy()
        env["KIBANA_USER"] = username
        env["KIBANA_PASS"] = password
        env["KIBANA_PROVIDER_TYPE"] = provider_type
        env["KIBANA_PROVIDER_NAME"] = provider_name

        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )

        if result.returncode != 0:
            return None

        cookie = (result.stdout or "").strip()
        if cookie:
            return cookie

        return None

    except Exception:
        return None


def _try_kibana_auth_winhttp(cert_files: Optional[Tuple[str, str]]) -> Optional[str]:
    """Try to authenticate using WinHTTP COM with a cert from Windows store."""
    try:
        import win32com.client

        thumbprint = _get_thumbprint_from_cert_files(cert_files)
        if not thumbprint:
            return None

        store_paths = [
            f"CURRENT_USER\\MY\\{thumbprint}",
            f"CurrentUser\\MY\\{thumbprint}",
            f"CurrentUser\\My\\{thumbprint}",
        ]

        for store_path in store_paths:
            req = win32com.client.Dispatch("WinHTTP.WinHTTPRequest.5.1")
            req.SetTimeouts(10000, 10000, 10000, 10000)
            try:
                req.SetClientCertificate(store_path)
            except Exception:
                continue

            for path in KIBANA_AUTH_PATHS:
                url = f"{KIBANA_URL}{path}"
                req.Open("GET", url, False)
                req.Send()

                headers = req.GetAllResponseHeaders()
                cookie = _extract_cookie_from_headers(headers)
                if cookie:
                    return cookie

        return None

    except Exception:
        return None


def _try_kibana_auth_with_key(cert_files: Optional[Tuple[str, str]]) -> Optional[str]:
    """Try to authenticate with extracted private key using Windows CryptoAPI."""
    try:
        from greenapi.credentials import get_credential_manager
        
        cert_mgr = get_credential_manager()
        
        # Try to extract the private key properly
        if not _extract_private_key_windows():
            return None
        
        # Refresh cert files after extraction attempt
        cert = cert_files
        if not cert or (isinstance(cert, tuple) and len(cert) > 1 and not cert[1]):
            cert = cert_mgr.get_certificate_files() or ("client.crt", "client.key")
        if isinstance(cert, tuple) and len(cert) > 1 and not cert[1]:
            return None
        
        resp = requests.get(
            f"{KIBANA_URL}/api/status",
            cert=cert,  # Both cert and key
            verify=True,
            timeout=10,
            allow_redirects=True
        )
        
        if resp.status_code == 200:
            return _extract_session_cookie(resp)
        else:
            return None
            
    except Exception:
        return None


def _extract_private_key_windows() -> bool:
    """
    Attempt to extract private key from Windows certificate store using CryptoAPI.
    Returns True if successful, False otherwise.
    """
    try:
        from greenapi.credentials import get_credential_manager
        
        cert_mgr = get_credential_manager()
        
        # First, check if a key was already exported during certificate setup
        if cert_mgr.ensure_private_key_exported():
            return True
        
        return False
        
    except Exception:
        return False


def _extract_session_cookie(response) -> Optional[str]:
    """Extract session cookie from Kibana response."""
    try:
        # Try to get cookies from response
        if response.cookies:
            cookie_str = "; ".join([f"{k}={v}" for k, v in response.cookies.items()])
            if cookie_str:
                return cookie_str
        
        # Try Set-Cookie header
        if 'Set-Cookie' in response.headers:
            cookies = response.cookies
            for cookie_name, cookie_value in cookies.items():
                if cookie_name and cookie_value:
                    return f"{cookie_name}={cookie_value}"
        
        return None
        
    except Exception:
        return None


def get_api_token(
    instance_id: str,
    kibana_cookie: Optional[str] = None,
    cert_files: Optional[Tuple[str, str]] = None
) -> str:
    """
    Retrieve the API token for the given instance_id by querying the ELK stack.
    
    Args:
        instance_id: The WhatsApp instance ID
        kibana_cookie: Kibana session cookie (if None, tries to load from env)
        cert_files: Tuple of (cert_path, key_path) for client certificates
                   (if None, tries to load from default files)
    
    Returns:
        The API token string, or error message if not found
    """
    token_re = re.compile(
        rf"(?:/| )waInstance{re.escape(instance_id)}/[A-Za-z]+/([a-fA-F0-9]{{32,}})"
    )

    proxy_url = f"{KIBANA_URL}/api/console/proxy"

    # Use provided credentials or fall back to environment/files
    cookie = kibana_cookie or os.getenv("KIBANA_COOKIE")
    if not cookie:
        return "Kibana cookie not provided. Please authenticate."
    
    cert = cert_files or ("client.crt", "client.key")
    if isinstance(cert, tuple) and len(cert) > 1 and not cert[1]:
        cert = cert[0]

    # If we don't have a private key file, use PowerShell with cert store
    if platform.system() == "Windows" and (not isinstance(cert, tuple)):
        ps_content = _get_api_token_powershell(instance_id, cookie, cert_files)
        if ps_content is None:
            return "Request Error: PowerShell token request failed"
        if isinstance(ps_content, dict) and ps_content.get("error"):
            return ps_content.get("error", "PowerShell token request failed")
        for hit in ps_content.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            for text in (src.get("uri", ""), src.get("message", "")):
                if not text:
                    continue
                m = token_re.search(text)
                if m:
                    return m.group(1)
        return "apiToken not found"

    try:
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
                "Cookie": cookie,
                "Content-Type": "application/json",
            },
            cert=cert,
            verify=True,
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
    
    except requests.exceptions.SSLError as e:
        return f"SSL Certificate Error: {str(e)}\nPlease check your client certificate."
    except requests.exceptions.RequestException as e:
        return f"Request Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


def _get_api_token_powershell(
    instance_id: str,
    cookie: str,
    cert_files: Optional[Tuple[str, str]],
) -> Optional[dict]:
    """Use PowerShell + Windows cert store to query Kibana logs when no key file is available."""
    try:
        thumbprint = _get_thumbprint_from_cert_files(cert_files)
        if not thumbprint:

            return None

        body = {
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
        }

        script = f"""
$ErrorActionPreference = 'Stop'
$thumb = '{thumbprint}'
$cert = Get-Item -Path ('Cert:\\CurrentUser\\My\\' + $thumb) -ErrorAction Stop
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$headers = @{{ 'kbn-xsrf' = 'true'; 'Content-Type' = 'application/json' }}

# Parse and add cookie to session
$cookiePairs = $env:KIBANA_COOKIE -split '; '
foreach ($pair in $cookiePairs) {{
    if ($pair -match '^(.+?)=(.+)$') {{
        $name = $Matches[1]
        $value = $Matches[2]
        $cookie = New-Object System.Net.Cookie($name, $value, '/', 'elk.prod.greenapi.org')
        $session.Cookies.Add($cookie)
    }}
}}

$uri = '{KIBANA_URL}/api/console/proxy?path=logs-*,filebeat-*/_search&method=GET'
$body = @'
{json.dumps(body)}
'@
$resp = Invoke-WebRequest -Uri $uri -Method POST -Body $body -Headers $headers -Certificate $cert -WebSession $session -UseBasicParsing -TimeoutSec 60
$resp.Content
"""

        env = os.environ.copy()
        env["KIBANA_COOKIE"] = cookie

        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=70,
            env=env,
        )

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            return {"error": f"ERROR: {err}"}

        content = (result.stdout or "").strip()
        if not content:
            return {"error": "ERROR: Empty response"}

        return json.loads(content)

    except Exception as e:
        return {"error": f"ERROR: {e}"}


def _get_thumbprint_from_cert_files(cert_files: Optional[Tuple[str, str]]) -> Optional[str]:
    """Compute certificate thumbprint from PEM file for store lookup."""
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes

        if not cert_files:
            return None
        cert_path = cert_files[0] if isinstance(cert_files, tuple) else cert_files
        if not cert_path or not os.path.exists(cert_path):
            return None

        with open(cert_path, "rb") as f:
            cert_pem = f.read()
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        return cert.fingerprint(hashes.SHA1()).hex().upper()

    except Exception:
        return None


def _extract_cookie_from_headers(headers: str) -> Optional[str]:
    """Extract session cookie from raw header string."""
    try:
        if not headers:
            return None
        lines = [h.strip() for h in headers.splitlines() if h.strip()]
        cookies = []
        for line in lines:
            if line.lower().startswith("set-cookie:"):
                value = line.split(":", 1)[1].strip()
                # Keep only the cookie key=value part
                pair = value.split(";", 1)[0].strip()
                if pair:
                    cookies.append(pair)
        if cookies:
            return "; ".join(cookies)
        return None
    except Exception:
        return None
