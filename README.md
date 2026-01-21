# The Helper – Green API Tool

This is a small desktop tool to quickly call Green API endpoints using an **Instance ID**.
Each button runs **one API request**, similar to Postman, but faster for daily support tasks without the ned for context switching and extra parameter gathering.

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

## First-time setup (required)

### 1. Prepare the config file

1. In this folder, copy:

   ```
   .env.local.example
   ```

   to:

   ```
   .env.local
   ```

2. Open `.env.local` and set:

   ```
   KIBANA_COOKIE=your_kibana_cookie_here
   ```

> This cookie is your own login session.
> Do NOT share it with others.

---

### 2. Add your certificate files

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
