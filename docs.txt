# Testing Auto-Update Functionality

Since you can't run servers or open ports on your work laptop, here's how to test the auto-update functionality locally:

## Method 1: Test Mode (Recommended)

1. **Run the test application:**
   ```bash
   run_test_mode.bat
   ```
   Or manually:
   ```bash
   .\dist\greenapi-helper-test.exe --test-mode
   ```

2. **Look for the "🧪 Test Update Available" button** in the main interface (below the "Re-authenticate Kibana Session" button).

3. **Click the test button** to simulate an update being available.

4. **The update dialog will appear** - you can choose "Update Now" to test the auto-update process.

5. **In test mode, the update process is simulated** - it shows an info message and then "quits" the app to simulate the restart.

## Method 2: Manual Testing with Two Executables

1. **Build two versions:**
   ```bash
   # Build "old" version
   pyinstaller --onefile --windowed --name greenapi-helper-old --add-data "ui;ui" --add-data "version.json;." app/main.py

   # Build "new" version
   pyinstaller --onefile --windowed --name greenapi-helper-new --add-data "ui;ui" --add-data "version.json;." app/main.py
   ```

2. **Run the "old" version** and trigger an update check.

3. **Manually replace the old executable** with the new one to simulate the update process.

## What the Auto-Update Does

When you click "Update Now" in the update dialog:

1. **Downloads** the new version from the URL specified in `version.json`
2. **Creates** a batch script that replaces the current executable
3. **Launches** the batch script and exits the current application
4. **The batch script** waits, replaces the file, and restarts the application

## Test Mode Features

- **No network access required** - simulates updates locally
- **Safe testing** - doesn't modify any real files
- **Visual feedback** - shows exactly what would happen in a real update
- **Command line flag** - `--test-mode` enables test features

## Troubleshooting

If the update dialog doesn't appear:
- Check that you're running with `--test-mode`
- Look for the "🧪 Test Update Available" button
- Check the console output for any error messages

If the test update doesn't work:
- Make sure you're running the compiled executable (not from source)
- Check that the application has proper file permissions
- Look at the console output for error details