"""
Conflict tagger — assigns each message to one or more conflicts.

Primary signal: the source's ``default_conflict_id`` from the registry.
Fallback: keyword matching against conflict-specific term lists (for
multi-conflict sources like X analysts).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Conflict keyword banks — keyed by conflict short_code
# ---------------------------------------------------------------------------

CONFLICT_TERMS: dict[str, set[str]] = {
    "israel-iran": {
        "Israel", "IDF", "IAF", "Mossad", "Shin Bet",
        "Iran", "IRGC", "Quds Force", "Hezbollah", "Houthis",
        "Hamas", "PIJ", "Islamic Jihad",
        "Gaza", "West Bank", "Lebanon", "Beirut", "Sidon", "Tyre",
        "Golan", "Tel Aviv", "Haifa", "Ashkelon",
        "Syria", "Damascus", "Aleppo", "Homs", "Deir ez-Zor",
        "Yemen", "Sanaa", "Hodeidah", "Bab el-Mandeb",
        "Iraq", "Baghdad", "Erbil",
        "Iron Dome", "Arrow", "David's Sling",
        "Natanz", "Isfahan", "Fordow",
    },
    "russia-ukraine": {
        "Ukraine", "Russia", "Kyiv", "Kiev", "Moscow", "Kremlin",
        "Donbas", "Donetsk", "Luhansk", "Zaporizhzhia", "Kherson",
        "Crimea", "Sevastopol", "Mariupol", "Bakhmut", "Avdiivka",
        "Kharkiv", "Odesa", "Mykolaiv",
        "Wagner", "Prigozhin", "Zelensky", "Zelenskyy", "Putin",
        "AFU", "UAF", "ZSU",
        "Leopard", "Abrams", "Bradley", "HIMARS", "ATACMS",
        "Shahed", "Lancet", "Geran",
        "Kursk", "Belgorod", "Bryansk",
        "Black Sea", "Azov",
        "Belarus", "Minsk", "Lukashenko",
    },
    "sudan": {
        "Sudan", "Khartoum", "Darfur", "RSF", "Rapid Support Forces",
        "SAF", "Sudanese Armed Forces", "Hemeti", "Hemedti",
        "al-Burhan", "Omdurman", "El Fasher", "Nyala",
        "Port Sudan", "Kassala", "Wad Madani",
        "Janjaweed",
    },
    "taiwan-china": {
        "Taiwan", "Taipei", "Kaohsiung", "Taiwan Strait",
        "China", "PLA", "PLAN", "PLAAF", "PRC", "Beijing",
        "Xi Jinping", "CCP",
        "TSMC", "semiconductor",
        "Kinmen", "Matsu", "Penghu",
        "ADIZ", "median line", "First Island Chain",
        "anti-secession", "reunification", "One China",
        "Tainan", "Hsinchu", "Pingtung",
    },
    "korean-peninsula": {
        "North Korea", "South Korea", "DPRK", "ROK",
        "Pyongyang", "Seoul", "Kim Jong Un", "Kim Jong-un",
        "DMZ", "demilitarized zone", "38th parallel",
        "ICBM", "Hwasong", "KPA", "USFK",
        "Yongbyon", "nuclear test", "missile test",
        "Panmunjom", "Kaesong", "Incheon",
        "Yoon Suk Yeol",
    },
    "venezuela": {
        "Venezuela", "Caracas", "Maduro",
        "PDVSA", "Citgo", "FANB",
        "Machado", "Gonzalez Urrutia",
        "Essequibo", "Guyana",
        "Maracaibo", "Barquisimeto",
        "SEBIN", "colectivos",
        "Bolivarian", "Chavismo",
    },
    "greenland": {
        "Greenland", "Nuuk", "Thule", "Pituffik",
        "Denmark", "Copenhagen",
        "Arctic", "rare earth",
        "Greenlandic", "Inuit",
        "Arctic sovereignty",
        "Mette Frederiksen", "Mute Egede",
    },
    "south-china-sea": {
        "South China Sea", "Spratly", "Paracel",
        "Scarborough Shoal", "Second Thomas Shoal",
        "nine-dash line", "UNCLOS",
        "Philippines", "Manila", "Marcos",
        "Vietnam", "Hanoi",
        "Mischief Reef", "Fiery Cross",
        "Subi Reef", "Woody Island",
        "FONOP", "freedom of navigation",
        "maritime militia",
        "Ayungin", "Sierra Madre",
    },
    "sahel": {
        "Sahel", "Mali", "Bamako", "Niger", "Niamey",
        "Burkina Faso", "Ouagadougou",
        "JNIM", "ISGS", "ISWAP",
        "Africa Corps",
        "ECOWAS", "AES",
        "Azawad", "Tuareg",
        "Timbuktu", "Gao", "Menaka",
        "MINUSMA", "Barkhane",
    },
    "somalia": {
        "Somalia", "Mogadishu", "Somaliland", "Hargeisa",
        "Al-Shabaab", "al-Shabaab",
        "AFRICOM", "AMISOM", "ATMIS",
        "Puntland", "Jubaland",
        "Baidoa", "Kismayo", "Beledweyne",
        "Horn of Africa",
    },
    "myanmar": {
        "Myanmar", "Burma", "Naypyidaw", "Yangon", "Rangoon",
        "Tatmadaw", "Min Aung Hlaing",
        "NUG", "People's Defense Force",
        "Rohingya", "Rakhine",
        "Arakan Army", "KIA", "KNLA", "KNU",
        "Mandalay", "Sagaing", "Chin",
        "Aung San Suu Kyi",
    },
}

# Pre-compile per-conflict patterns
_CONFLICT_PATTERNS: dict[str, re.Pattern] = {}
for _code, _terms in CONFLICT_TERMS.items():
    _escaped = [re.escape(t) for t in sorted(_terms, key=len, reverse=True)]
    _CONFLICT_PATTERNS[_code] = re.compile(
        "|".join(rf"\b{e}\b" for e in _escaped),
        re.IGNORECASE,
    )


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class ConflictMatch:
    conflict_id: int
    short_code: str
    score: float  # rough match strength
    matched_terms: list[str]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def tag_conflicts(
    text: str,
    source_default_conflict_id: int | None,
    conflict_map: dict[str, int],
) -> list[ConflictMatch]:
    """Return a list of conflicts this message relates to.

    *conflict_map* maps ``short_code`` → ``conflict.id`` (loaded from DB).
    """
    matches: list[ConflictMatch] = []

    for short_code, pattern in _CONFLICT_PATTERNS.items():
        conflict_id = conflict_map.get(short_code)
        if conflict_id is None:
            continue
        found = pattern.findall(text)
        if found:
            matches.append(ConflictMatch(
                conflict_id=conflict_id,
                short_code=short_code,
                score=len(found),
                matched_terms=found,
            ))

    # Sort by score descending — strongest match first
    matches.sort(key=lambda m: m.score, reverse=True)

    # If no keyword matches but the source has a default conflict, use it
    if not matches and source_default_conflict_id is not None:
        # Find the short_code for this ID (reverse lookup)
        code = next(
            (k for k, v in conflict_map.items() if v == source_default_conflict_id),
            "unknown",
        )
        matches.append(ConflictMatch(
            conflict_id=source_default_conflict_id,
            short_code=code,
            score=0,
            matched_terms=[],
        ))

    return matches


def get_region_bias(short_code: str) -> str | None:
    """Return a region string to bias Nominatim geocoding for a conflict."""
    REGION_BIAS = {
        "israel-iran": "Middle East",
        "russia-ukraine": "Eastern Europe",
        "sudan": "Sudan",
        "taiwan-china": "East Asia",
        "korean-peninsula": "Korean Peninsula",
        "venezuela": "South America",
        "greenland": "Greenland",
        "south-china-sea": "Southeast Asia",
        "sahel": "West Africa",
        "somalia": "East Africa",
        "myanmar": "Southeast Asia",
    }
    return REGION_BIAS.get(short_code)
