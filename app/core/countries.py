"""Dial codes and flags, looked up by country name.

Deliberately keyed on the name the provider returns rather than on its numeric
country id. Provider id numbering is undocumented and differs between
providers, so a mistake there would show one country's dial code beside
another's name. A name match is unambiguous, and anything not listed simply
shows no dial code -- an omission, never a wrong one.
"""

from __future__ import annotations

import re

#: Country name (lower-case, no spaces or punctuation) -> dial code.
DIAL_CODES: dict[str, str] = {
    "afghanistan": "+93", "albania": "+355", "algeria": "+213", "angola": "+244",
    "argentina": "+54", "armenia": "+374", "australia": "+61", "austria": "+43",
    "azerbaijan": "+994", "bahrain": "+973", "bangladesh": "+880", "belarus": "+375",
    "belgium": "+32", "benin": "+229", "bolivia": "+591", "bosnia": "+387",
    "botswana": "+267", "brazil": "+55", "bulgaria": "+359", "burkinafaso": "+226",
    "cambodia": "+855", "cameroon": "+237", "canada": "+1", "chad": "+235",
    "chile": "+56", "china": "+86", "colombia": "+57", "congo": "+242",
    "costarica": "+506", "croatia": "+385", "cyprus": "+357", "czechrepublic": "+420",
    "czechia": "+420", "denmark": "+45", "dominicanrepublic": "+1", "ecuador": "+593",
    "egypt": "+20", "elsalvador": "+503", "salvador": "+503", "estonia": "+372",
    "ethiopia": "+251", "finland": "+358", "france": "+33", "gabon": "+241",
    "gambia": "+220", "georgia": "+995", "germany": "+49", "ghana": "+233",
    "greece": "+30", "guatemala": "+502", "guinea": "+224", "haiti": "+509",
    "honduras": "+504", "hongkong": "+852", "hungary": "+36", "india": "+91",
    "indonesia": "+62", "iran": "+98", "iraq": "+964", "ireland": "+353",
    "israel": "+972", "italy": "+39", "ivorycoast": "+225", "jamaica": "+1",
    "japan": "+81", "jordan": "+962", "kazakhstan": "+7", "kenya": "+254",
    "kuwait": "+965", "kyrgyzstan": "+996", "laos": "+856", "latvia": "+371",
    "lebanon": "+961", "liberia": "+231", "libya": "+218", "lithuania": "+370",
    "luxembourg": "+352", "macao": "+853", "madagascar": "+261", "malawi": "+265",
    "malaysia": "+60", "mali": "+223", "malta": "+356", "mauritania": "+222",
    "mauritius": "+230", "mexico": "+52", "moldova": "+373", "mongolia": "+976",
    "montenegro": "+382", "morocco": "+212", "mozambique": "+258", "myanmar": "+95",
    "namibia": "+264", "nepal": "+977", "netherlands": "+31", "newzealand": "+64",
    "nicaragua": "+505", "niger": "+227", "nigeria": "+234", "norway": "+47",
    "oman": "+968", "pakistan": "+92", "panama": "+507", "papuanewguinea": "+675",
    "paraguay": "+595", "peru": "+51", "philippines": "+63", "poland": "+48",
    "portugal": "+351", "puertorico": "+1", "qatar": "+974", "romania": "+40",
    "russia": "+7", "rwanda": "+250", "saudiarabia": "+966", "senegal": "+221",
    "serbia": "+381", "seychelles": "+248", "sierraleone": "+232", "singapore": "+65",
    "slovakia": "+421", "slovenia": "+386", "somalia": "+252", "southafrica": "+27",
    "southkorea": "+82", "korea": "+82", "spain": "+34", "srilanka": "+94",
    "sudan": "+249", "sweden": "+46", "switzerland": "+41", "syria": "+963",
    "taiwan": "+886", "tajikistan": "+992", "tanzania": "+255", "thailand": "+66",
    "togo": "+228", "tunisia": "+216", "turkey": "+90", "turkmenistan": "+993",
    "uganda": "+256", "ukraine": "+380", "uae": "+971", "unitedarabemirates": "+971",
    "uk": "+44", "unitedkingdom": "+44", "england": "+44", "usa": "+1",
    "unitedstates": "+1", "uruguay": "+598", "uzbekistan": "+998", "venezuela": "+58",
    "vietnam": "+84", "yemen": "+967", "zambia": "+260", "zimbabwe": "+263",
}

_NORMALISE = re.compile(r"[^a-z]")


def dial_code(country_name: str) -> str:
    """Return the dial code for a country name, or ``""`` when unknown."""
    return DIAL_CODES.get(_NORMALISE.sub("", country_name.lower()), "")


#: Country name (normalised) -> ISO 3166-1 alpha-2 code, which is what a flag
#: emoji is built from. Same keying as DIAL_CODES, and for the same reason.
ISO_CODES: dict[str, str] = {
    "afghanistan": "AF", "albania": "AL", "algeria": "DZ", "angola": "AO",
    "argentina": "AR", "armenia": "AM", "australia": "AU", "austria": "AT",
    "azerbaijan": "AZ", "bahrain": "BH", "bangladesh": "BD", "belarus": "BY",
    "belgium": "BE", "benin": "BJ", "bolivia": "BO", "bosnia": "BA",
    "botswana": "BW", "brazil": "BR", "bulgaria": "BG", "burkinafaso": "BF",
    "cambodia": "KH", "cameroon": "CM", "canada": "CA", "chad": "TD",
    "chile": "CL", "china": "CN", "colombia": "CO", "congo": "CG",
    "costarica": "CR", "croatia": "HR", "cyprus": "CY", "czechia": "CZ",
    "czechrepublic": "CZ", "denmark": "DK", "dominicanrepublic": "DO", "ecuador": "EC",
    "egypt": "EG", "elsalvador": "SV", "england": "GB", "estonia": "EE",
    "ethiopia": "ET", "finland": "FI", "france": "FR", "gabon": "GA",
    "gambia": "GM", "georgia": "GE", "germany": "DE", "ghana": "GH",
    "greece": "GR", "guatemala": "GT", "guinea": "GN", "haiti": "HT",
    "honduras": "HN", "hongkong": "HK", "hungary": "HU", "india": "IN",
    "indonesia": "ID", "iran": "IR", "iraq": "IQ", "ireland": "IE",
    "israel": "IL", "italy": "IT", "ivorycoast": "CI", "jamaica": "JM",
    "japan": "JP", "jordan": "JO", "kazakhstan": "KZ", "kenya": "KE",
    "korea": "KR", "kuwait": "KW", "kyrgyzstan": "KG", "laos": "LA",
    "latvia": "LV", "lebanon": "LB", "liberia": "LR", "libya": "LY",
    "lithuania": "LT", "luxembourg": "LU", "macao": "MO", "madagascar": "MG",
    "malawi": "MW", "malaysia": "MY", "mali": "ML", "malta": "MT",
    "mauritania": "MR", "mauritius": "MU", "mexico": "MX", "moldova": "MD",
    "mongolia": "MN", "montenegro": "ME", "morocco": "MA", "mozambique": "MZ",
    "myanmar": "MM", "namibia": "NA", "nepal": "NP", "netherlands": "NL",
    "newzealand": "NZ", "nicaragua": "NI", "niger": "NE", "nigeria": "NG",
    "norway": "NO", "oman": "OM", "pakistan": "PK", "panama": "PA",
    "papuanewguinea": "PG", "paraguay": "PY", "peru": "PE", "philippines": "PH",
    "poland": "PL", "portugal": "PT", "puertorico": "PR", "qatar": "QA",
    "romania": "RO", "russia": "RU", "rwanda": "RW", "salvador": "SV",
    "saudiarabia": "SA", "senegal": "SN", "serbia": "RS", "seychelles": "SC",
    "sierraleone": "SL", "singapore": "SG", "slovakia": "SK", "slovenia": "SI",
    "somalia": "SO", "southafrica": "ZA", "southkorea": "KR", "spain": "ES",
    "srilanka": "LK", "sudan": "SD", "sweden": "SE", "switzerland": "CH",
    "syria": "SY", "taiwan": "TW", "tajikistan": "TJ", "tanzania": "TZ",
    "thailand": "TH", "togo": "TG", "tunisia": "TN", "turkey": "TR",
    "turkmenistan": "TM", "uae": "AE", "uganda": "UG", "uk": "GB",
    "ukraine": "UA", "unitedarabemirates": "AE", "unitedkingdom": "GB", "unitedstates": "US",
    "uruguay": "UY", "usa": "US", "uzbekistan": "UZ", "venezuela": "VE",
    "vietnam": "VN", "yemen": "YE", "zambia": "ZM", "zimbabwe": "ZW",
}


def iso_code(country_name: str) -> str:
    """Return the ISO alpha-2 code for a country name, or ``""`` when unknown."""
    return ISO_CODES.get(_NORMALISE.sub("", country_name.lower()), "")


def flag(country_name: str) -> str:
    """Return the flag emoji for a country name, or ``""`` when unknown.

    A flag is two regional-indicator letters, each 127397 above its ASCII
    letter. Deriving it beats storing 156 emoji: there is nothing to mistype.
    """
    code = iso_code(country_name)
    if len(code) != 2:
        return ""
    return "".join(chr(ord(letter) + 127397) for letter in code)


#: ISO 3166-1 alpha-2 -> alpha-3. A fixed international standard, not
#: provider-sourced business data -- unlike prices or stock, these values
#: cannot go stale or vary by source, so deriving ISO-3 from the alpha-2
#: table above (rather than a second name-keyed table) cannot drift out of
#: sync with it.
_ALPHA2_TO_ALPHA3: dict[str, str] = {
    "AE": "ARE", "AF": "AFG", "AL": "ALB", "AM": "ARM", "AO": "AGO", "AR": "ARG",
    "AT": "AUT", "AU": "AUS", "AZ": "AZE", "BA": "BIH", "BD": "BGD", "BE": "BEL",
    "BF": "BFA", "BG": "BGR", "BH": "BHR", "BJ": "BEN", "BO": "BOL", "BR": "BRA",
    "BW": "BWA", "BY": "BLR", "CA": "CAN", "CG": "COG", "CH": "CHE", "CI": "CIV",
    "CL": "CHL", "CM": "CMR", "CN": "CHN", "CO": "COL", "CR": "CRI", "CY": "CYP",
    "CZ": "CZE", "DE": "DEU", "DK": "DNK", "DO": "DOM", "DZ": "DZA", "EC": "ECU",
    "EE": "EST", "EG": "EGY", "ES": "ESP", "ET": "ETH", "FI": "FIN", "FR": "FRA",
    "GA": "GAB", "GB": "GBR", "GE": "GEO", "GH": "GHA", "GM": "GMB", "GN": "GIN",
    "GR": "GRC", "GT": "GTM", "HK": "HKG", "HN": "HND", "HR": "HRV", "HT": "HTI",
    "HU": "HUN", "ID": "IDN", "IE": "IRL", "IL": "ISR", "IN": "IND", "IQ": "IRQ",
    "IR": "IRN", "IT": "ITA", "JM": "JAM", "JO": "JOR", "JP": "JPN", "KE": "KEN",
    "KG": "KGZ", "KH": "KHM", "KR": "KOR", "KW": "KWT", "KZ": "KAZ", "LA": "LAO",
    "LB": "LBN", "LK": "LKA", "LR": "LBR", "LT": "LTU", "LU": "LUX", "LV": "LVA",
    "LY": "LBY", "MA": "MAR", "MD": "MDA", "ME": "MNE", "MG": "MDG", "ML": "MLI",
    "MM": "MMR", "MN": "MNG", "MO": "MAC", "MR": "MRT", "MT": "MLT", "MU": "MUS",
    "MW": "MWI", "MX": "MEX", "MY": "MYS", "MZ": "MOZ", "NA": "NAM", "NE": "NER",
    "NG": "NGA", "NI": "NIC", "NL": "NLD", "NO": "NOR", "NP": "NPL", "NZ": "NZL",
    "OM": "OMN", "PA": "PAN", "PE": "PER", "PG": "PNG", "PH": "PHL", "PK": "PAK",
    "PL": "POL", "PR": "PRI", "PT": "PRT", "PY": "PRY", "QA": "QAT", "RO": "ROU",
    "RS": "SRB", "RU": "RUS", "RW": "RWA", "SA": "SAU", "SC": "SYC", "SD": "SDN",
    "SE": "SWE", "SG": "SGP", "SI": "SVN", "SK": "SVK", "SL": "SLE", "SN": "SEN",
    "SO": "SOM", "SV": "SLV", "SY": "SYR", "TD": "TCD", "TG": "TGO", "TH": "THA",
    "TJ": "TJK", "TM": "TKM", "TN": "TUN", "TR": "TUR", "TW": "TWN", "TZ": "TZA",
    "UA": "UKR", "UG": "UGA", "US": "USA", "UY": "URY", "UZ": "UZB", "VE": "VEN",
    "VN": "VNM", "YE": "YEM", "ZA": "ZAF", "ZM": "ZMB", "ZW": "ZWE",
}


def iso3_code(country_name: str) -> str:
    """Return the ISO alpha-3 code for a country name, or ``""`` when unknown."""
    return _ALPHA2_TO_ALPHA3.get(iso_code(country_name), "")


def matches_search(name: str, needle: str, *short_codes: str) -> bool:
    """True if ``needle`` (any case, untrimmed) identifies this country.

    Matches on the full name (substring), the ISO alpha-2/alpha-3 code (exact --
    these are short enough that substring matching would false-positive), a
    colloquial short name ("uk", "usa", "uae", "england", ...) that is not
    itself the ISO code but is already a recognised alias in ``ISO_CODES``,
    the dial code (substring, so "91" finds every India-prefixed number), and
    any caller-supplied short codes (e.g. a provider's own country code), also
    exact. Case/whitespace are normalised here rather than trusted from every
    call site. One place for this so every country picker in the bot -- the
    SMS marketplace and TG-Lion alike -- searches the same way.
    """
    needle = needle.strip().lower().lstrip("+")
    if not needle:
        return False
    if needle in name.lower():
        return True
    country_iso2 = iso_code(name)
    if needle == country_iso2.lower() or needle == iso3_code(name).lower():
        return True
    if country_iso2 and ISO_CODES.get(_NORMALISE.sub("", needle)) == country_iso2:
        return True
    if needle in dial_code(name).lstrip("+"):
        return True
    return any(needle == code.lower() for code in short_codes if code)
