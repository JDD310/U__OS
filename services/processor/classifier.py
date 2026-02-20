"""
Content classifier — hybrid keyword-first approach.

Categorizes messages as geopolitical (relevant) or domestic politics / satire
(filtered out). Returns a confidence score; messages below the threshold can
be routed to an LLM fallback (Phase 2+).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Keyword dictionaries
# ---------------------------------------------------------------------------

#TODO Check current terms and add more if needed

GEOPOLITICAL_HIGH = {
    "airstrike", "air strike", "drone strike", "missile strike", "bombing",
    "IRGC", "Hezbollah", "IDF", "NATO", "Wagner", "PMC",
    "ceasefire", "escalation", "ATACMS", "HIMARS", "S-300", "S-400",
    "intercepted", "launched", "casualties", "KIA", "WIA",
    "shelling", "artillery", "mortar", "rocket attack",
    "SAM", "MANPADS", "JDAM", "cruise missile", "ballistic missile",
    "frontline", "counteroffensive", "encirclement", "bridgehead",
    "air defense", "SAR", "BDA", "SIGINT", "ISR",
    "arms shipment", "weapons transfer", "military aid",
}

GEOPOLITICAL_MEDIUM = {
    "sanctions", "deployment", "military", "border", "reconnaissance",
    "convoy", "artillery", "troops", "armor", "infantry",
    "naval", "fleet", "carrier", "submarine", "warship",
    "checkpoint", "garrison", "fortification", "trench",
    "airspace", "no-fly zone", "blockade", "embargo",
    "proxy", "militia", "insurgent", "partisan",
    "humanitarian corridor", "evacuation", "refugee",
}

DOMESTIC_POLITICS_HIGH = {
    "Congress", "Senate vote", "House vote", "GOP", "Democrat",
    "MAGA", "immigration bill", "Supreme Court", "midterms",
    "presidential race", "2028", "2026 election",
    "filibuster", "impeachment", "indictment",
    "campaign trail", "primary", "caucus",
    "executive order", "veto",
}

DOMESTIC_POLITICS_MEDIUM = {
    "bipartisan", "lobbying", "PAC", "super PAC",
    "polling", "approval rating", "swing state",
    "gerrymandering", "voter registration",
}

#TODO Edit and add more satire terms
SATIRE_STRUCTURAL = {
    "lmao", "lol", "rofl", "ratio", "cope", "seethe",
    "least delusional", "most sane", "average",
    "shitpost", "parody", "satire", "/s",
    "ngl", "frfr", "no cap", "based and",
}

# Pre-compile a single pattern per category for fast scanning
_WORD_BOUNDARY = r"(?i)\b{}\b"


def _compile_set(terms: set[str]) -> re.Pattern:
    escaped = [re.escape(t) for t in sorted(terms, key=len, reverse=True)]
    return re.compile("|".join(_WORD_BOUNDARY.format(e) for e in escaped))


_RE_GEO_HIGH = _compile_set(GEOPOLITICAL_HIGH)
_RE_GEO_MED = _compile_set(GEOPOLITICAL_MEDIUM)
_RE_DOM_HIGH = _compile_set(DOMESTIC_POLITICS_HIGH)
_RE_DOM_MED = _compile_set(DOMESTIC_POLITICS_MEDIUM)
_RE_SATIRE = _compile_set(SATIRE_STRUCTURAL)


# ---------------------------------------------------------------------------
# Classification result
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    category: str  # "geopolitical", "domestic_politics", "satire", "unclassified"
    confidence: float  # 0.0 – 1.0
    is_relevant: bool  # True → keep, False → filter out
    matched_terms: list[str] = field(default_factory=list)
    event_type: str | None = None  # best-guess event type if geopolitical


# ---------------------------------------------------------------------------
# Event-type inference from matched terms
# ---------------------------------------------------------------------------

EVENT_TYPE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)\b(airstrike|air strike|drone strike|bombing|JDAM)\b"), "airstrike"),
    (re.compile(r"(?i)\b(missile strike|cruise missile|ballistic missile|rocket attack)\b"), "missile_strike"),
    (re.compile(r"(?i)\b(shelling|artillery|mortar)\b"), "shelling"),
    (re.compile(r"(?i)\b(intercepted|air defense|SAM|MANPADS|S-300|S-400)\b"), "interception"),
    (re.compile(r"(?i)\b(casualties|KIA|WIA|killed|wounded|dead)\b"), "casualty_report"),
    (re.compile(r"(?i)\b(deployment|convoy|troops|armor|infantry|movement|advancing)\b"), "movement"),
    (re.compile(r"(?i)\b(ceasefire|truce|peace talk|negotiation|diplomatic)\b"), "diplomatic"),
    (re.compile(r"(?i)\b(arms shipment|weapons transfer|military aid)\b"), "arms_transfer"),
    (re.compile(r"(?i)\b(statement|comment|remark|announce|declare)\b"), "statement"),
]


def _infer_event_type(text: str) -> str | None:
    for pattern, event_type in EVENT_TYPE_PATTERNS:
        if pattern.search(text):
            return event_type
    return None


# ---------------------------------------------------------------------------
# Core classifier
# ---------------------------------------------------------------------------

def classify(text: str, source_filter_rules: dict | None = None) -> ClassificationResult:
    """Classify a message using keyword matching.

    Returns a ClassificationResult with category, confidence, and relevance.
    Per-source filter rules (from the sources table) can raise/lower
    thresholds for specific categories.
    """
    if not text or not text.strip():
        return ClassificationResult(
            category="unclassified",
            confidence=0.0,
            is_relevant=False,
        )

    text_lower = text.lower()
    word_count = max(len(text_lower.split()), 1)

    # --- Satire check (cheapest, run first) ---
    satire_matches = _RE_SATIRE.findall(text_lower)
    satire_density = len(satire_matches) / word_count

    # --- Domestic politics ---
    dom_high = _RE_DOM_HIGH.findall(text)
    dom_med = _RE_DOM_MED.findall(text)
    dom_score = (len(dom_high) * 3 + len(dom_med)) / word_count

    # --- Geopolitical ---
    geo_high = _RE_GEO_HIGH.findall(text)
    geo_med = _RE_GEO_MED.findall(text)
    geo_score = (len(geo_high) * 3 + len(geo_med)) / word_count

    # Apply per-source adjustments
    if source_filter_rules:
        geo_score *= source_filter_rules.get("geo_weight", 1.0)
        dom_score *= source_filter_rules.get("dom_weight", 1.0)

    # --- Decision logic ---
    # Strong satire signal → filter out
    if satire_density > 0.05 and geo_score < 0.1:
        return ClassificationResult(
            category="satire",
            confidence=min(satire_density * 10, 1.0),
            is_relevant=False,
            matched_terms=satire_matches,
        )

    # Geopolitical wins if it scores higher than domestic
    if geo_score > dom_score and geo_score > 0:
        confidence = min(geo_score * 8, 1.0)
        all_matches = geo_high + geo_med
        return ClassificationResult(
            category="geopolitical",
            confidence=confidence,
            is_relevant=True,
            matched_terms=all_matches,
            event_type=_infer_event_type(text),
        )

    # Domestic politics dominates
    if dom_score > geo_score and dom_score > 0:
        confidence = min(dom_score * 8, 1.0)
        return ClassificationResult(
            category="domestic_politics",
            confidence=confidence,
            is_relevant=False,
            matched_terms=dom_high + dom_med,
        )

    # Nothing matched strongly — Telegram OSINT channels are usually
    # relevant by default, so mark as geopolitical with low confidence.
    return ClassificationResult(
        category="unclassified",
        confidence=0.0,
        is_relevant=False,
    )
