"""Human-readable names for SMS provider service codes.

Providers in the SMS-Activate family identify services by short opaque codes
(``tg``, ``ttf``, ``obi``). SMS-Activate itself exposes ``getServicesList`` to
resolve them; several forks do not, so a bot talking to a fork would show
users the raw code.

The map below covers the codes that are stable across the family. Anything
missing falls back to the uppercased code, which is honest -- a wrong name
beside a real phone number is worse than an unfamiliar one. To label a code
this map does not know, add it here rather than guessing at runtime.
"""

from __future__ import annotations

SERVICE_NAMES: dict[str, str] = {
    "av": "Avito",
    "ab": "Alibaba",
    "am": "Amazon",
    "ap": "Apple",
    "bd": "Badoo",
    "bz": "Blizzard",
    "cy": "Yandex",
    "dr": "OpenAI",
    "ds": "Discord",
    "ew": "Nike",
    "fb": "Facebook",
    "ff": "Xiaomi",
    "fu": "Snapchat",
    "go": "Google",
    "gf": "GoFundMe",
    "ig": "Instagram",
    "ka": "Shopee",
    "kt": "KakaoTalk",
    "lf": "TikTok",
    "li": "LinkedIn",
    "ls": "Lyft",
    "ma": "Mail.ru",
    "mb": "Yahoo",
    "me": "Line",
    "mm": "Microsoft",
    "mt": "Steam",
    "nf": "Netflix",
    "nv": "Naver",
    "oi": "Tinder",
    "ot": "Other",
    "pm": "AOL",
    "qq": "QQ",
    "re": "Coinbase",
    "tg": "Telegram",
    "ti": "Tinder",
    "ts": "PayPal",
    "tw": "Twitter",
    "ub": "Uber",
    "vi": "Viber",
    "vk": "VKontakte",
    "wa": "WhatsApp",
    "wb": "WeChat",
    "wx": "Apple",
    "ya": "Yandex",
    "zy": "Zoho",
}


def service_name(code: str) -> str:
    """Return a display name for ``code``, falling back to the code itself."""
    return SERVICE_NAMES.get(code.lower(), code.upper())
