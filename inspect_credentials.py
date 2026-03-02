import json
import traceback
from greenapi.credentials import get_credential_manager


def main():
    try:
        mgr = get_credential_manager()
        cert_files = mgr.get_certificate_files()
        kibana_cookie = mgr.get_kibana_cookie()
        has_key_exported = mgr.ensure_private_key_exported()
        saved_thumb = mgr.get_saved_certificate_thumbprint()

        info = {
            "cert_files": cert_files,
            "kibana_cookie": kibana_cookie,
            "has_key_exported": has_key_exported,
            "saved_thumbprint": saved_thumb,
        }
        print(json.dumps(info, indent=2))
    except Exception:
        traceback.print_exc()


if __name__ == '__main__':
    main()
