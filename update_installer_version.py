"""
Update installer.nsi with the current version from version.json
Run this before building the NSIS installer to keep versions in sync.
"""

import json
import re


def update_installer_version():
    # Read current version
    with open("version.json", "r", encoding="utf-8") as f:
        version_data = json.load(f)

    version = version_data["version"]

    # Read installer script
    with open("installer.nsi", "r", encoding="utf-8") as f:
        content = f.read()

    # Update version in installer script
    pattern = r'(!define APP_VERSION ")[^"]*(")'
    replacement = rf"\g<1>{version}\g<2>"
    updated_content = re.sub(pattern, replacement, content)

    # Write back to installer script
    with open("installer.nsi", "w", encoding="utf-8") as f:
        f.write(updated_content)

    print(f"Updated installer.nsi to version {version}")


if __name__ == "__main__":
    update_installer_version()
