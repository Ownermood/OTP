"""Dial codes, looked up by country name.

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
