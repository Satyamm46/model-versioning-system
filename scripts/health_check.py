"""CD step: poll /api/health until the freshly deployed app answers UP (or give up)."""
import json
import os
import sys
import time
import urllib.request

URL = f"http://localhost:{os.getenv('MVS_PORT', '8000')}/api/health"


def main(tries: int = 15, delay: int = 2) -> int:
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(URL, timeout=3) as resp:
                body = json.load(resp)
            if resp.status == 200 and body.get("status") == "UP":
                print(f"Health check passed: {body}")
                return 0
        except Exception as exc:
            print(f"Attempt {attempt}/{tries}: not ready yet ({exc})")
        time.sleep(delay)
    print("Health check FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
