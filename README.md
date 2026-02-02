# Green API Helper

A small Windows desktop tool to quickly call Green API endpoints using an **Instance ID**. Each button runs a single API request (similar to Postman), optimized for daily support and operations workflows.

---

## Features

- Automatic API URL resolution based on Instance ID
- Automatic API token lookup from Kibana logs
- Windows Certificate Store integration (no file handling needed)
- Safe in-memory credentials and temp-file cleanup on exit

---

## Requirements

- Windows 10/11
- Python 3.10+ (for running from source)
- Access to Kibana and a valid client certificate with private key

---

## Quick Start (from source)

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

### 2) Run the app

```bash
python -m app.main
```

### 3) First-time authentication flow

When you click any action button for the first time:

1. **Certificate Selection Dialog** appears
   - Choose a client certificate from the Windows Certificate Store
   - Only certificates with private keys are valid for authentication

2. **Kibana Authentication**
   - If automatic login is not available, you will be prompted
   - You can provide either:
     - Kibana username/password (recommended), or
     - A Kibana session cookie (manual)

Credentials are remembered for the current app session only.

---

## Environment configuration (optional)

Create a .env.local file in the project root to prefill or automate authentication:

```
KIBANA_COOKIE=your_cookie_here
KIBANA_USER=your_username
KIBANA_PASS=your_password
KIBANA_PROVIDER_TYPE=basic
KIBANA_PROVIDER_NAME=basic
```

Notes:
- `KIBANA_COOKIE` is only used as a fallback if no session cookie is available.
- `KIBANA_USER`/`KIBANA_PASS` enable automatic login without cookie copying.
- Provider settings are optional and default to `basic`.

---

## Legacy file-based certificate setup (optional)

If you prefer using certificate files, place them in the working directory:

```
client.crt
client.key
```

You can extract them from a .pfx file:

```
openssl pkcs12 -legacy -in name.pfx -clcerts -nokeys -out client.crt
openssl pkcs12 -legacy -in name.pfx -nocerts -nodes -out client.key
```

If `openssl` is unavailable, install Git Bash (https://git-scm.com/install/windows) and run the commands there.

---

## How to use

1. Enter the **Instance ID**
2. Click an action (Get State, Settings, Journals, Reboot, etc.)
3. Review the response in the output area

---

## Safety notes

- The **Reboot Instance** and destructive actions prompt for confirmation.
- Do not share `.env.local`, cookies, or certificate files.
- Each user should use their own credentials.

---

## Troubleshooting

### Buttons do nothing

- Ensure your certificate is present in Windows Certificate Store (Current User → Personal)
- Confirm the certificate has a private key
- Verify Kibana access and credentials

### Certificate errors

- Verify the certificate is valid and not expired
- Re-import with “Mark this key as exportable” if required

### “apiToken not found”

- The instance may be inactive
- Check Kibana access and time range settings

---

## Support / improvements

Contact the maintainer for new endpoints, UI changes, or output formatting adjustments.
