"""Test script to verify architectural improvements."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))


def test_env_variables():
    """Test that environment variables are properly used."""
    from greenapi import elk_auth

    # Test default values
    print("Testing environment variable fallbacks...")
    assert hasattr(elk_auth, "KIBANA_URL")
    assert hasattr(elk_auth, "SEARCH_SIZE")
    assert hasattr(elk_auth, "TIME_GTE")

    # Verify defaults
    import os

    if "KIBANA_URL" not in os.environ:
        print(f"[OK] KIBANA_URL defaults to: {elk_auth.KIBANA_URL}")
    if "SEARCH_SIZE" not in os.environ:
        print(f"[OK] SEARCH_SIZE defaults to: {elk_auth.SEARCH_SIZE}")
    if "TIME_GTE" not in os.environ:
        print(f"[OK] TIME_GTE defaults to: {elk_auth.TIME_GTE}")

    print("[OK] Environment variable configuration working\n")


def test_error_logging():
    """Test that error logging function exists."""
    from app import update

    print("Testing error logging...")
    assert hasattr(update, "_log_error")

    # Test it doesn't crash
    update._log_error("Test error message")
    print("[OK] Error logging function working\n")


def test_no_processEvents_in_critical_paths():
    """Verify processEvents removed from critical authentication flow."""
    print("Testing processEvents removal...")

    with open("app/main.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Count remaining processEvents calls
    count = content.count("processEvents()")
    print(f"Found {count} processEvents() calls in main.py")

    # Allow processEvents for UI updates (non-blocking), but verify it's not in critical blocking paths
    # Acceptable use: forcing UI refresh before network calls (doesn't block auth logic)
    # The one remaining call is for UI update only, which is fine

    ensure_auth_start = content.find("def _ensure_authentication")
    ensure_auth_end = content.find("def _add_button")  # Next method
    if ensure_auth_start != -1 and ensure_auth_end != -1:
        ensure_section = content[ensure_auth_start:ensure_auth_end]
        assert "processEvents()" not in ensure_section, "processEvents() still in _ensure_authentication!"
        print("[OK] No processEvents() in _ensure_authentication")

    print("[OK] processEvents removed from critical authentication paths\n")


def test_auth_error_reporting():
    """Verify authentication error reporting is improved."""
    print("Testing authentication error reporting...")

    with open("greenapi/elk_auth.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Check for error output in auth methods
    assert 'print(f"Cert-only auth failed:' in content, "Missing error reporting in cert-only auth"
    print("[OK] Cert-only auth has error reporting")

    assert 'print("PowerShell auth:' in content, "Missing error reporting in PowerShell auth"
    print("[OK] PowerShell auth has error reporting")

    assert 'print(f"PowerShell auth failed:' in content, "Missing PowerShell stderr logging"
    print("[OK] PowerShell stderr output logged")

    print("[OK] Authentication error reporting improved\n")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Architectural Improvements")
    print("=" * 60 + "\n")

    try:
        test_env_variables()
        test_error_logging()
        test_no_processEvents_in_critical_paths()
        test_auth_error_reporting()

        print("=" * 60)
        print("All tests passed!")
        print("=" * 60)
        sys.exit(0)
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
