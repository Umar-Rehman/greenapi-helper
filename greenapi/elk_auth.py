import re
import requests
import os
import json
import platform
import subprocess
from typing import Optional, Tuple
from dotenv import load_dotenv

load_dotenv(".env.local")

# Configuration with environment variable support
KIBANA_URL = os.getenv("KIBANA_URL", "https://elk.prod.greenapi.org")
SEARCH_SIZE = int(os.getenv("SEARCH_SIZE", "50"))
TIME_GTE = os.getenv("TIME_GTE", "now-7d")
KIBANA_AUTH_PATHS = ["/internal/security/me", "/api/security/v1/me", "/api/status"]

# Helper functions


def get_kibana_session_cookie(
    cert_files: Optional[Tuple[str, str]] = None,
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
            print("Strategy 1 (WinHTTP cert auth) succeeded")
            return cookie

    # Strategy 2: Try Windows PowerShell with cert from store (no key export)
    if platform.system() == "Windows":
        cookie = _try_kibana_auth_powershell(cert_files)
        if cookie:
            print("Strategy 2 (PowerShell cert auth) succeeded")
            return cookie

    # Strategy 3: Try certificate-only mode (let Windows/SSL handle the key)
    cookie = _try_kibana_auth_cert_only(cert_files)
    if cookie:
        print("Strategy 3 (Cert-only auth) succeeded")
        return cookie

    # Strategy 4: Try with full private key export
    cookie = _try_kibana_auth_with_key(cert_files)
    if cookie:
        print("Strategy 4 (Cert with key export) succeeded")
        return cookie

    # Strategy 3: Failed - return None for fallback to manual entry
    print("All authentication strategies failed - please enter Kibana session cookie manually.")
    return None


def get_kibana_session_cookie_with_password(
    username: str,
    password: str,
    cert_files: Optional[Tuple[str, str]] = None,
) -> Optional[str]:
    """Authenticate to Kibana using username/password + cert and return session cookie.

    Returns:
        Session cookie string if successful, None if authentication failed.
        Check stderr for error details when debugging.
    """
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
                allow_redirects=True,
            )

            if resp.status_code in (200, 302, 401, 403):
                cookie = _extract_session_cookie(resp)
                if cookie:
                    return cookie

        return None

    except Exception as e:
        # Log error for debugging but don't fail - try next method
        import sys

        print(f"Cert-only auth failed: {e}", file=sys.stderr)
        return None


def _try_kibana_auth_powershell(cert_files: Optional[Tuple[str, str]]) -> Optional[str]:
    """Try to authenticate using PowerShell and a cert from Windows store (no key export)."""
    try:
        thumbprint = _get_thumbprint_from_cert_files(cert_files)
        if not thumbprint:
            import sys

            print("PowerShell auth: No certificate thumbprint found", file=sys.stderr)
            return None

        script = f"""
$ErrorActionPreference = 'Stop'
$thumb = '{thumbprint}'
$cert = Get-Item -Path ('Cert:\\CurrentUser\\My\\' + $thumb) -ErrorAction Stop
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$auth_paths = @({', '.join([f"'{p}'" for p in KIBANA_AUTH_PATHS])})
foreach ($p in $auth_paths) {{
    $uri = '{KIBANA_URL}' + $p
    $resp = Invoke-WebRequest -Uri $uri -Certificate $cert `
        -WebSession $session -UseBasicParsing -TimeoutSec 10
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
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if result.returncode != 0:
            import sys

            print(f"PowerShell auth failed: {result.stderr}", file=sys.stderr)
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
        import sys

        thumbprint = _get_thumbprint_from_cert_files(cert_files)
        if not thumbprint:
            print("No certificate thumbprint found", file=sys.stderr)
            return None

        provider_name = os.getenv("KIBANA_PROVIDER_NAME", "basic")
        provider_type = os.getenv("KIBANA_PROVIDER_TYPE", "basic")

        # Verify certificate exists in store before attempting authentication
        verify_script = f"""
$thumb = '{thumbprint}'
$cert = Get-Item -Path "Cert:\\CurrentUser\\My\\$thumb" -ErrorAction SilentlyContinue
if ($cert -and $cert.HasPrivateKey) {{
    Write-Output "VALID"
}} else {{
    Write-Output "INVALID"
}}
"""
        verify_result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", verify_script],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if verify_result.stdout.strip() != "VALID":
            import sys

            print(
                "Certificate not found or missing private key in CurrentUser\\My store",
                file=sys.stderr,
            )
            return None

        # Base64 encode credentials to bypass encoding issues
        import base64

        username_b64 = base64.b64encode(username.encode("utf-8")).decode("ascii")
        password_b64 = base64.b64encode(password.encode("utf-8")).decode("ascii")
        provider_type_b64 = base64.b64encode(provider_type.encode("utf-8")).decode("ascii")
        provider_name_b64 = base64.b64encode(provider_name.encode("utf-8")).decode("ascii")

        script = f"""
$ErrorActionPreference = 'Stop'
$thumb = '{thumbprint}'

try {{
    $cert = Get-Item -Path ('Cert:\\CurrentUser\\My\\' + $thumb) -ErrorAction Stop

    if (-not $cert.HasPrivateKey) {{
        Write-Error "Certificate found but has no private key. Thumbprint: $thumb"
        exit 1
    }}
}} catch {{
    Write-Error "Certificate not found in CurrentUser\\My store. Thumbprint: $thumb. Error: $_"
    exit 1
}}

$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$base = '{KIBANA_URL}'
$headers = @{{ 'kbn-xsrf' = 'true'; 'Content-Type' = 'application/json; charset=utf-8' }}
$user = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{username_b64}'))
$pass = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{password_b64}'))
$ptype = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{provider_type_b64}'))
$pname = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{provider_name_b64}'))

$certUser = $null
if ($cert.Subject -match 'CN=([^,]+)') {{
    $certUser = $Matches[1]
}}

$userCandidates = @($user)
if ($certUser -and $certUser -ne $user) {{
    $userCandidates += $certUser
}}

$loginSucceeded = $false
$lastStatusCode = $null
$lastStatusDesc = $null
foreach ($u in $userCandidates) {{
    $body = @{{
        providerType = $ptype
        providerName = $pname
        currentURL = "$base/app/home"
        params = @{{ username = $u; password = $pass }}
    }} | ConvertTo-Json -Depth 6
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)

    try {{
        Invoke-WebRequest -Uri ($base + '/internal/security/login') `
            -Method POST -Body $bodyBytes -Headers $headers -ContentType 'application/json; charset=utf-8' `
            -Certificate $cert -WebSession $session -UseBasicParsing -TimeoutSec 10 | Out-Null
        $loginSucceeded = $true
        break
    }} catch {{
        $lastStatusCode = $_.Exception.Response.StatusCode.value__
        $lastStatusDesc = $_.Exception.Response.StatusDescription
    }}

    $body2 = @{{ username = $u; password = $pass }} | ConvertTo-Json
    $body2Bytes = [System.Text.Encoding]::UTF8.GetBytes($body2)
    try {{
        Invoke-WebRequest -Uri ($base + '/api/security/v1/login') `
            -Method POST -Body $body2Bytes -Headers $headers -ContentType 'application/json; charset=utf-8' `
            -Certificate $cert -WebSession $session -UseBasicParsing -TimeoutSec 10 | Out-Null
        $loginSucceeded = $true
        break
    }} catch {{
        $lastStatusCode = $_.Exception.Response.StatusCode.value__
        $lastStatusDesc = $_.Exception.Response.StatusDescription
    }}
}}

if (-not $loginSucceeded) {{
    $statusCode = if ($lastStatusCode) {{ $lastStatusCode }} else {{ 'Unknown' }}
    $statusDesc = if ($lastStatusDesc) {{ $lastStatusDesc }} else {{ 'Unknown' }}
    Write-Error "Kibana login failed. Status: $statusCode $statusDesc."
    exit 1
}}

$paths = @({', '.join([f"'{p}'" for p in KIBANA_AUTH_PATHS])})
foreach ($p in $paths) {{
    $uri = $base + $p
    $cookies = $session.Cookies.GetCookies([Uri]$uri)
    if ($cookies.Count -gt 0) {{
        ($cookies | ForEach-Object {{ "$($_.Name)=$($_.Value)" }}) -join '; '
        break
    }}
}}
"""

        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if result.returncode != 0:
            # Extract just the actual error messages
            import sys

            stderr = result.stderr.strip() if result.stderr else ""

            # Look for the actual executed Write-Error output (appears at the end)
            # Format: "Write-Error : <actual error message>"
            error_lines = []
            for line in stderr.split("\n"):
                # Skip the script echo and only get actual error output
                if line.strip().startswith("Write-Error :"):
                    # Extract the actual error message after "Write-Error :"
                    msg = line.split("Write-Error :", 1)[1].strip()
                    # Skip if it's just quoting the Write-Error command from script
                    if not msg.startswith('"') and msg:
                        # Clean up the message
                        msg = msg.lstrip(": ")
                        error_lines.append(msg)

            # If no Write-Error lines found, look for other error indicators
            if not error_lines:
                for line in stderr.split("\n"):
                    keywords = ["Kibana login failed", "Status:", "Unauthorized"]
                    if any(keyword in line for keyword in keywords):
                        # Make sure it's not part of the script text
                        skip_prefixes = (
                            "Write-Error",
                            "Write-Host",
                            "$",
                            "#",
                            "At line:",
                            "CategoryInfo",
                            "+",
                        )
                        if not line.strip().startswith(skip_prefixes):
                            error_lines.append(line.strip())

            if error_lines:
                print("Kibana authentication failed:", file=sys.stderr)
                # Show only unique, meaningful errors (first 2)
                seen = set()
                for msg in error_lines[:2]:
                    if msg and msg not in seen and len(msg) > 10:
                        seen.add(msg)
                        if "404" in msg and "Not Found" in msg:
                            print(
                                "  • Login endpoints not found (404). "
                                "Your Kibana version may use different authentication endpoints.",
                                file=sys.stderr,
                            )
                        elif "401" in msg or "Unauthorized" in msg:
                            print(
                                "  • Invalid username or password (401 Unauthorized)",
                                file=sys.stderr,
                            )
                        elif "403" in msg or "Forbidden" in msg:
                            print(
                                "  • Access forbidden (403). Check user permissions.",
                                file=sys.stderr,
                            )
                        else:
                            print(f"  • {msg}", file=sys.stderr)
            else:
                print(
                    "Kibana authentication failed: Invalid username or password",
                    file=sys.stderr,
                )

            return None

        cookie = (result.stdout or "").strip()
        if cookie:
            return cookie

        print(
            "Kibana login: No session cookie returned after successful authentication",
            file=sys.stderr,
        )
        return None

    except Exception as e:
        import sys

        print(f"Kibana login exception: {type(e).__name__}: {e}", file=sys.stderr)
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
            cert=cert,
            verify=True,
            timeout=10,
            allow_redirects=True,  # Both cert and key
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
        if "Set-Cookie" in response.headers:
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
    cert_files: Optional[Tuple[str, str]] = None,
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
    token_pattern = rf"(?:/| )waInstance{re.escape(instance_id)}/[A-Za-z]+/([a-fA-F0-9]{{32,}})"
    token_re = re.compile(token_pattern)

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
$resp = Invoke-WebRequest -Uri $uri -Method POST -Body $body -Headers $headers `
    -Certificate $cert -WebSession $session -UseBasicParsing -TimeoutSec 60
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
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
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


def _get_thumbprint_from_cert_files(
    cert_files: Optional[Tuple[str, str]],
) -> Optional[str]:
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
