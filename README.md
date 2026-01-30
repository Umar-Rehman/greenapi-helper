# The Helper – Green API Tool

This is a small desktop tool to quickly call Green API endpoints using an **Instance ID**.
Each button runs **one API request**, similar to Postman, but faster for daily support tasks without the need for context switching and extra parameter gathering.

---

## New: Windows Certificate Store Integration

**No more certificate files needed!** The application now supports:
- Direct certificate selection from Windows Certificate Store
- Seamless Kibana authentication on first use
- Secure credential management in memory
- Automatic cleanup on exit

---

## What this tool does

* You enter an **Instance ID**
* Click a button (Get State, Settings, Journals, Reboot, etc.)
* The tool:
  * automatically finds the API URL
  * automatically finds the API token from logs
  * sends the API request
* The response is shown in the output box

You **do not** need to enter API tokens or URLs manually.

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the application

```bash
python -m app.main
```

### 3. On first use

When you click any button for the first time:

1. **Certificate Selection Dialog** will appear:
   - Select your client certificate from Windows Certificate Store
   - Only certificates with private keys are shown

2. **Kibana Authentication Dialog** will appear:
   - Enter your Kibana session cookie
   - Get it from browser: F12 → Application → Cookies

3. **Done!** Credentials are remembered for the session

---

## Legacy Setup (Optional)

### If you prefer using certificate files:

Place your **client certificate files** in the same folder as `TheHelper.exe`:

```
client.crt
client.key
```

These files are required to access ELK / API endpoints.

You may do this by adding the .pfx file to this directory then running the commands:

```
openssl pkcs12 -legacy -in name.pfx -clcerts -nokeys -out client.crt
openssl pkcs12 -legacy -in name.pfx -nocerts -nodes -out client.key
```

If you are having openssl issues, like `openssl : The term 'openssl' is not recognized as the name of a cmdlet, function, script file, or operable program.` then install bash: https://git-scm.com/install/windows and run the above commands in this terminal instead.

---

### 3. Run the app

Double-click:

```
TheHelper.exe
```

---

## How to use

1. Enter the **Instance ID**
2. Click the action you want:

   * Get Instance State
   * Get Instance Settings
   * Get Journals
   * Reboot Instance (confirmation required)
3. View the result in the output area

---

## Reboot action warning

The **Reboot Instance** button will:

* show a confirmation popup
* only reboot if you click **Yes**

This action may interrupt message processing.

---

## Troubleshooting

### App starts but buttons do nothing

* Check that `.env.local` exists
* Check that `KIBANA_COOKIE` is filled

### Certificate errors

* Ensure `client.crt` and `client.key` are present
* Ensure they are valid and not expired

### “apiToken not found”

* The instance may be inactive
* Try increasing log time range (if available)
* Check ELK access

---

## Security notes

* Do **not** share your `.env.local`
* Do **not** share your certificate files
* Each user must use their **own** credentials

---

## Support / improvements

If you need:

* a new endpoint button
* a dashboard alternative
* changes to output formatting

Contact the maintainer of this tool.
