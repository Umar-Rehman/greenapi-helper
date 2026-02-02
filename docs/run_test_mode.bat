@echo off
echo Starting Green API Helper in Test Mode...
echo.
echo This version includes a "Test Update Available" button that simulates
echo an update being available without requiring network access.
echo.
echo Press any key to continue...
pause > nul

REM Run the application with test mode enabled
start "" "%~dp0greenapi-helper-test.exe" --test-mode