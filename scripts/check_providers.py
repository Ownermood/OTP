"""Verify provider credentials before going live.

Run this after pointing ``.env`` at a new SMS or SMM panel. It makes real,
read-only calls -- no orders are placed and no money moves -- and reports what
each provider actually returned, so a wrong URL or key is caught here rather
than by a user mid-purchase.

    python -m scripts.check_providers          # everything that is enabled
    python -m scripts.check_providers --smm    # just the SMM panel
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter

from app.core.config import get_settings
from app.core.exceptions import ConfigurationError
from app.core.logging import mask_secret, setup_logging
from app.core.money import format_money
from app.providers import build_payment_providers, build_smm_provider, build_sms_provider

OK = "✅"
BAD = "❌"
WARN = "⚠️"


async def check_sms(settings) -> bool:
    print(f"\n📱 SMS provider: {settings.sms_provider}")
    print(f"   key: {mask_secret(settings.sms_activate_api_token)}")
    provider = build_sms_provider(settings)
    try:
        balance = await provider.get_balance()
        print(f"   {OK} balance: {format_money(balance, settings.currency_symbol)}")

        services = await provider.get_services()
        print(f"   {OK} services: {len(services)}")
        if services:
            preview = ", ".join(s.name for s in services[:5])
            print(f"      e.g. {preview}")

            countries = await provider.get_countries(services[0].code)
            print(f"   {OK} countries for '{services[0].name}': {len(countries)}")
            if countries:
                cheapest = countries[0]
                print(
                    f"      cheapest: {cheapest.name} — "
                    f"{format_money(cheapest.cost, settings.currency_symbol)}"
                )
        return True
    except Exception as exc:
        print(f"   {BAD} {type(exc).__name__}: {exc}")
        return False
    finally:
        await provider.close()


async def check_payments(settings) -> bool:
    print("\n💳 Payment providers")
    providers = build_payment_providers(settings)

    # Manual UPI is the primary deposit route and has no API to reach, so it
    # never appears in the provider registry. Reporting "none enabled" for a
    # bot that takes UPI deposits told operators to fix a working setup.
    if settings.manual_payment_enabled:
        print(f"   {OK} manual UPI: {settings.upi_id} -> channel {settings.manual_payment_channel_id}")
    elif not providers:
        print(f"   {BAD} none enabled")
        return False

    ok = True
    for name, provider in providers.items():
        try:
            if provider.is_native:
                # Stars checkout lives inside Telegram; there is nothing to ping.
                rate = settings.telegram_stars_rate
                print(f"   {OK} {name}: native (1 star = {rate} {settings.currency_code})")
                continue
            balance = await provider.get_balance()
            print(f"   {OK} {name}: reachable, balance {format_money(balance, settings.currency_symbol)}")
        except Exception as exc:
            print(f"   {BAD} {name}: {type(exc).__name__}: {exc}")
            ok = False
        finally:
            await provider.close()
    return ok


async def check_smm(settings) -> bool:
    print("\n📈 SMM panel")
    if not settings.smm_enabled:
        print(f"   {WARN} disabled (set SMM_ENABLED=true to use it)")
        return True

    print(f"   url: {settings.smm_api_url}")
    print(f"   key: {mask_secret(settings.smm_api_key)}")
    provider = build_smm_provider(settings)
    if provider is None:
        print(f"   {BAD} could not build the provider")
        return False

    try:
        balance = await provider.get_balance()
        print(f"   {OK} balance: {format_money(balance, settings.currency_symbol)}")

        services = await provider.get_services()
        print(f"   {OK} services: {len(services)}")
        if not services:
            print(f"   {WARN} the panel returned an empty catalogue")
            return False

        by_category = Counter(service.category for service in services)
        print("   categories:")
        for category, count in by_category.most_common():
            print(f"      {category:<12} {count}")

        sample = services[0]
        print(
            f"   sample: {sample.name}\n"
            f"      id {sample.service_id} · "
            f"{format_money(sample.rate_per_1000, settings.currency_symbol)}/1000 · "
            f"min {sample.min_quantity} · max {sample.max_quantity}"
        )
        markup = settings.smm_markup_percent
        user_price = sample.rate_per_1000 + sample.rate_per_1000 * int(markup) // 100
        print(
            f"      user pays {format_money(user_price, settings.currency_symbol)}/1000 "
            f"at {markup}% markup"
        )

        if by_category.get("other", 0) == len(services):
            print(
                f"   {WARN} every service landed in 'other' — the panel's category "
                f"names are unfamiliar, so the platform menu will have one tab"
            )
        return True
    except Exception as exc:
        print(f"   {BAD} {type(exc).__name__}: {exc}")
        return False
    finally:
        await provider.close()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sms", action="store_true", help="check only the SMS provider")
    parser.add_argument("--smm", action="store_true", help="check only the SMM panel")
    parser.add_argument("--payments", action="store_true", help="check only payment providers")
    args = parser.parse_args()

    try:
        settings = get_settings()
    except ConfigurationError as exc:
        print(f"\n{BAD} {exc}\n", file=sys.stderr)
        return 2

    setup_logging("WARNING")
    run_all = not (args.sms or args.smm or args.payments)
    results = []

    if run_all or args.sms:
        results.append(await check_sms(settings))
    if run_all or args.payments:
        results.append(await check_payments(settings))
    if run_all or args.smm:
        results.append(await check_smm(settings))

    if all(results):
        print(f"\n{OK} All checked providers responded.\n")
        return 0
    print(f"\n{BAD} Some providers failed — see above. The bot will refuse to start.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
