"""Work out which protocol an SMS provider speaks.

Run this where the provider is reachable -- your own machine or the server the
bot will run on -- and it reports whether the existing SMS-Activate adapter can
talk to it as-is, or whether a new adapter is needed.

    python -m scripts.probe_sms_provider https://api.temporasms.com YOUR_API_KEY

It only makes read-only calls: balance, service list, country list. Nothing is
purchased and no money moves.
"""

from __future__ import annotations

import json
import sys
from urllib.parse import urljoin

import httpx

#: Where SMS-Activate-compatible providers put their endpoint. Clones vary on
#: the path but keep the query protocol, so each is worth trying.
CANDIDATE_PATHS = [
    "stubs/handler_api.php",
    "handler_api.php",
    "api/handler_api.php",
    "",
]

TIMEOUT = 20.0


def probe(base_url: str, api_key: str) -> int:
    base = base_url if base_url.endswith("/") else base_url + "/"
    print(f"\nProbing {base}\n" + "=" * 60)

    working_path = None
    reached_anything = False
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        for path in CANDIDATE_PATHS:
            url = urljoin(base, path)
            label = f"/{path}" if path else "/"
            try:
                response = client.get(
                    url, params={"api_key": api_key, "action": "getBalance"}
                )
            except httpx.HTTPError as exc:
                print(f"  {label:24} unreachable — {type(exc).__name__}")
                continue

            reached_anything = True
            body = response.text.strip()
            print(f"  {label:24} HTTP {response.status_code} — {body[:70]!r}")

            if body.startswith("ACCESS_BALANCE"):
                print(f"\n✅ SMS-Activate protocol, at {label}")
                print(f"   Balance: {body.split(':', 1)[1]}")
                working_path = path
                break
            if body.startswith(("BAD_KEY", "WRONG_KEY", "ERROR_KEY")):
                print("\n❌ SMS-Activate protocol, but the API key was rejected.")
                return 1

        if working_path is None:
            if not reached_anything:
                # Nothing answered at all, so nothing has been learned about
                # the protocol. Saying "different protocol" here would be a
                # conclusion the evidence does not support.
                return _report_unreachable(base)
            return _report_unknown(client, base, api_key)

        _check_catalogue(client, urljoin(base, working_path), api_key)

    print("\n" + "=" * 60)
    print("This provider works with the existing adapter. Set in .env:\n")
    print("    SMS_PROVIDER=sms_activate")
    print(f"    SMS_ACTIVATE_BASE_URL={base}")
    print("    SMS_ACTIVATE_API_TOKEN=<your key>\n")
    if working_path != "stubs/handler_api.php":
        print(f"⚠️  Its endpoint is /{working_path}, not the default")
        print("    /stubs/handler_api.php — tell Claude, the adapter needs")
        print("    one line changed to point at it.\n")
    return 0


def _check_catalogue(client: httpx.Client, url: str, api_key: str) -> None:
    """Confirm the calls the bot actually depends on return usable data."""
    print("\nChecking the calls the bot needs:")

    for action, label in (
        ("getServicesList", "service list"),
        ("getTopCountriesByService", "countries + prices"),
    ):
        params = {"api_key": api_key, "action": action}
        if action == "getTopCountriesByService":
            params["service"] = "wa"
        try:
            response = client.get(url, params=params)
            payload = response.json()
        except httpx.HTTPError as exc:
            print(f"  ❌ {label:22} unreachable — {exc}")
            continue
        except ValueError:
            print(f"  ⚠️  {label:22} not JSON — {response.text[:60]!r}")
            continue

        size = len(payload.get("services", payload)) if isinstance(payload, dict) else len(payload)
        print(f"  ✅ {label:22} {size} entries")
        sample = json.dumps(payload, ensure_ascii=False)[:160]
        print(f"     {sample}")


def _report_unreachable(base: str) -> int:
    print("\n🚫 Could not reach the provider at all — every request failed.")
    print("   Nothing has been learned about its protocol yet.\n")
    print("   Usually one of:")
    print("     • no internet, or a proxy/firewall in the way")
    print("     • the base URL is wrong (check it opens in a browser)")
    print("     • the provider is down\n")
    print(f"   Try:  curl -v {base}\n")
    return 3


def _report_unknown(client: httpx.Client, base: str, api_key: str) -> int:
    """Nothing matched, so gather what a new adapter would be written against."""
    print("\n❓ This is not the SMS-Activate protocol.")
    print("   A small adapter is needed. Gathering what it would be built on:\n")

    for path in ("", "api", "v1", "docs", "api/v1"):
        url = urljoin(base, path)
        try:
            response = client.get(url, params={"api_key": api_key})
        except httpx.HTTPError as exc:
            print(f"  /{path:12} unreachable — {type(exc).__name__}")
            continue
        content_type = response.headers.get("content-type", "?").split(";")[0]
        print(f"  /{path:12} HTTP {response.status_code}  {content_type}")
        print(f"               {response.text[:120]!r}")

    print("\nSend Claude:")
    print("  • the output above")
    print("  • a link to the provider's API documentation")
    print("  • one sample response for 'get balance' and 'buy a number'")
    print("\nThat is enough to write the adapter. Nothing else in the bot changes.\n")
    return 2


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    return probe(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    raise SystemExit(main())
