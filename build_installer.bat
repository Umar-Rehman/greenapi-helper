@echo off
echo Building NSIS installer...
echo.

REM Check if NSIS is installed
where makensis >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: NSIS (makensis) not found in PATH
    echo Please install NSIS from https://nsis.sourceforge.io/Download
    echo or add NSIS to your PATH
    pause
    exit /b 1
)

REM Check if executable exists
if not exist "dist\greenapi-helper.exe" (
    echo ERROR: dist\greenapi-helper.exe not found
    echo Please build the executable first using PyInstaller
    pause
    exit /b 1
)

REM Build the installer
python update_installer_version.py
makensis installer.nsi

if %ERRORLEVEL% EQU 0 (
    echo.
    echo SUCCESS! Installer created at: dist\greenapi-helper-setup.exe
    echo.
    echo To test:
    echo 1. Run dist\greenapi-helper-setup.exe
    echo 2. It will install to %LOCALAPPDATA%\GreenAPIHelper
    echo 3. Check Start Menu for shortcuts
    pause
) else (
    echo.
    echo ERROR: Failed to build installer
    pause
    exit /b 1
)
