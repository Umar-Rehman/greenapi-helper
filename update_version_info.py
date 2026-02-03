"""
Update version_info.txt with the current version from version.json
Run this before building with PyInstaller to keep versions in sync.
"""

import json


def update_version_info():
    # Read current version
    with open("version.json", "r", encoding="utf-8") as f:
        version_data = json.load(f)

    version = version_data["version"]
    version_parts = version.split(".")

    # Pad to 4 parts if needed
    while len(version_parts) < 4:
        version_parts.append("0")

    version_tuple = ", ".join(version_parts)
    version_str = ".".join(version_parts)

    # Template for version_info.txt
    template = f"""# UTF-8
#
# Version information for PyInstaller
#
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({version_tuple}),
    prodvers=({version_tuple}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'Umar Rehman'),
        StringStruct(u'FileDescription', u'Green API Helper - WhatsApp Business API Tool'),
        StringStruct(u'FileVersion', u'{version_str}'),
        StringStruct(u'InternalName', u'greenapi-helper'),
        StringStruct(u'LegalCopyright', u'Copyright (c) 2026 Umar Rehman'),
        StringStruct(u'OriginalFilename', u'greenapi-helper.exe'),
        StringStruct(u'ProductName', u'Green API Helper'),
        StringStruct(u'ProductVersion', u'{version_str}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""

    # Write version_info.txt
    with open("version_info.txt", "w", encoding="utf-8") as f:
        f.write(template)

    print(f"Updated version_info.txt to version {version}")


if __name__ == "__main__":
    update_version_info()
