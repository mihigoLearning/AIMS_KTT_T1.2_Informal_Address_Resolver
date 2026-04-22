"""
T1.2 · Informal Address Resolver
Resolves free-text Kigali delivery descriptions to (lat, lon, confidence).

API:  resolve(text) -> dict
      {lat, lon, confidence, matched_landmark, rationale, escalate}

Constraints: CPU-only, no LLM calls, sub-100ms average latency.
Libraries:   rapidfuzz, regex, geopy, langid, pandas
"""

import json
import math
import os
import re
import time
import unittest

from rapidfuzz import fuzz, process as rf_process

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GAZETTEER_PATH = os.path.join(os.path.dirname(__file__),  "data", "gazetteer.json")
ESCALATION_THRESHOLD = 0.45  # confidence below this → flag for dispatcher

# Spatial modifiers → (bearing_degrees_from_north, typical_distance_m)
# bearing 0=North, 90=East, 180=South, 270=West
MODIFIER_MAP = {
    # English
    "behind":           (180, 60),
    "next to":          ( 90, 30),
    "beside":           ( 90, 30),
    "near":             (  0, 50),
    "opposite":         (  0, 40),
    "above":            ( 45, 25),
    "in front of":      (  0, 40),
    # French
    "derrière":         (180, 60),
    "à côté de":        ( 90, 30),
    "près de":          (  0, 50),
    "en face de":       (  0, 40),
    # Kinyarwanda
    "inyuma ya":        (180, 60),   # behind
    "iruhande rwa":     ( 90, 30),   # beside / next to
    "iruhande":         ( 90, 30),   # beside (short form)
    "hafi ya":          (  0, 50),   # near
    "imbere ya":        (  0, 40),   # in front of / opposite
    "hejuru ya":        ( 45, 25),   # above
    "munsi ya":         (225, 25),   # below / under
    "kuri":             ( 90, 20),   # at / on
}

# Language marker word-sets for heuristic detection
KIN_MARKERS = {"inyuma", "ya", "hafi", "kuri", "aho", "aka", "mu", "na",
               "imbere", "hejuru", "nini", "nto", "kera", "mishya",
               "iruhande", "rwa", "munsi"}
FR_MARKERS  = {"derrière", "près", "face", "côté", "de", "du", "la",
               "le", "les", "grand", "petit", "vieux", "nouveau", "sur"}

# Kigali sector / neighbourhood qualifiers that disambiguate branch-style
# queries ("Bank of Kigali Kacyiru", "Simba Remera"). These are checked
# against the matched landmark's name/aliases/district; a mismatch is a
# strong signal that the best fuzzy hit is the WRONG instance.
LOCALITY_TOKENS = {
    # Gasabo
    "kacyiru", "remera", "kimironko", "nyarutarama", "kinyinya",
    "kabusunzu", "gisozi", "gisimenti", "kibagabaga", "ndera", "gasabo",
    # Nyarugenge
    "nyamirambo", "kimisagara", "nyabugogo", "biryogo", "nyarugenge",
    # Kicukiro
    "gikondo", "kicukiro", "nyanza", "rebero", "kagarama", "kabeza",
}

# Sector → district mapping, so a locality qualifier can still validate
# a match even when the sector name isn't in the landmark's own string.
LOCALITY_TO_DISTRICT = {
    "kacyiru":     "Gasabo", "remera":       "Gasabo",
    "kimironko":   "Gasabo", "nyarutarama":  "Gasabo",
    "kinyinya":    "Gasabo", "kabusunzu":    "Gasabo",
    "gisozi":      "Gasabo", "gisimenti":    "Gasabo",
    "kibagabaga":  "Gasabo", "ndera":        "Gasabo",
    "gasabo":      "Gasabo",
    "nyamirambo":  "Nyarugenge", "kimisagara": "Nyarugenge",
    "nyabugogo":   "Nyarugenge", "biryogo":    "Nyarugenge",
    "nyarugenge":  "Nyarugenge",
    "gikondo":     "Kicukiro", "kicukiro":    "Kicukiro",
    "nyanza":      "Kicukiro", "rebero":      "Kicukiro",
    "kagarama":    "Kicukiro", "kabeza":      "Kicukiro",
}

_GAZETTEER_CACHE = None


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_gazetteer(path: str = GAZETTEER_PATH) -> list[dict]:
    global _GAZETTEER_CACHE
    if _GAZETTEER_CACHE is None:
        with open(path, encoding="utf-8") as f:
            _GAZETTEER_CACHE = json.load(f)
    return _GAZETTEER_CACHE


def _all_names(landmark: dict) -> list[str]:
    return [landmark["name"]] + landmark.get("aliases", [])


# ---------------------------------------------------------------------------
# 1. Language detection
# ---------------------------------------------------------------------------

def detect_language(text: str) -> str:
    """
    Heuristic EN/FR/KIN detection — fast, no external model needed.
    Returns 'en', 'fr', or 'kin'.
    """
    tokens = set(re.findall(r"[a-zA-ZÀ-ÿ]+", text.lower()))
    kin_score = len(tokens & KIN_MARKERS)
    fr_score  = len(tokens & FR_MARKERS)
    if kin_score > fr_score and kin_score > 0:
        return "kin"
    if fr_score > kin_score and fr_score > 0:
        return "fr"
    return "en"


# ---------------------------------------------------------------------------
# Locality extraction & validation
# ---------------------------------------------------------------------------

def extract_locality(text: str) -> str | None:
    """
    Pull a Kigali sector/neighbourhood qualifier out of the query, e.g.
    "Bank of Kigali Kacyiru" → "kacyiru". When multiple hits exist the
    *last* one wins — qualifiers typically trail the brand/entity.
    Returns None when no known locality appears.
    """
    tokens = set(re.findall(r"[a-zA-ZÀ-ÿ]+", text.lower()))
    hits = tokens & LOCALITY_TOKENS
    if not hits:
        return None
    lower = text.lower()
    return max(hits, key=lambda t: lower.rfind(t))


def _strip_locality(text: str, locality: str | None) -> str | None:
    """
    Remove the locality token from text (whole-word, case-insensitive).

    Returns the stripped string ONLY if it still contains ≥2 alphabetic
    tokens — otherwise returns None and the caller should keep the
    original. Rationale: stripping "kimironko" from "Kimironko Market"
    leaves just "Market", which fuzzy-matches any market in the
    gazetteer; but stripping "kacyiru" from "Simba Remera Kacyiru"
    leaves "Simba Remera" — a clean brand+sector signal that matches
    the correct landmark. The 2-token floor distinguishes the two.
    """
    if not locality:
        return None
    pattern = re.compile(rf"\b{re.escape(locality)}\b", re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", pattern.sub(" ", text)).strip()
    tokens = re.findall(r"[a-zA-ZÀ-ÿ]+", stripped)
    if len(tokens) < 2:
        return None
    return stripped


def _locality_match(locality: str | None, landmark: dict) -> str:
    """
    Classify how well a landmark satisfies a locality qualifier:
      'name'     — locality appears in the landmark's name or aliases
                   (strongest signal: this IS the instance they meant)
      'district' — locality's district equals the landmark's district
                   (weak signal: right area, possibly wrong branch)
      'none'     — mismatch or no locality specified; caller decides
                   whether to penalise.
    """
    if not locality:
        return "none"
    names_joined = " ".join(_all_names(landmark)).lower()
    if locality in names_joined:
        return "name"
    if LOCALITY_TO_DISTRICT.get(locality) == landmark.get("district"):
        return "district"
    return "none"


# Road-prefix patterns to strip before matching (Kinyarwanda / French / English)
_ROAD_PREFIX_RE = re.compile(
    r"^(ku muhanda ujya|along the road to|sur la route de|route vers)\s+\w+\s*",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 2. Modifier extraction
# ---------------------------------------------------------------------------

def extract_modifier(text: str) -> tuple[str | None, int, int]:
    """
    Find the longest matching spatial modifier in text.
    Returns (modifier_key, bearing_deg, distance_m) or (None, 0, 0).
    """
    lower = text.lower()
    for mod in sorted(MODIFIER_MAP, key=len, reverse=True):
        if mod in lower:
            bearing, dist = MODIFIER_MAP[mod]
            return mod, bearing, dist
    return None, 0, 0


def _candidate_queries(
    text: str,
    modifier: str | None,
    locality: str | None = None,
) -> list[str]:
    """
    Return a ranked list of text variants to try for fuzzy matching.
    Trying shorter, cleaner substrings first improves hit rate on
    multi-part / compositional descriptions.

    When a locality qualifier is specified and stripping it still leaves
    ≥2 tokens, we SUBSTITUTE the stripped variant instead of appending
    it — because the locality token would otherwise lift landmarks that
    merely share the sector name (e.g. "Simba Remera Kacyiru" matching
    "BPR Bank Kacyiru" via the Kacyiru alias instead of the Simba brand).
    Locality validation runs separately afterward in `resolve`.
    """
    candidates = []
    lower = text.lower()

    def _use(variant: str) -> str:
        """Return locality-stripped variant when safe, else the original."""
        stripped_loc = _strip_locality(variant, locality)
        return stripped_loc if stripped_loc else variant

    # 1. Text AFTER the modifier (highest priority for compositional queries)
    if modifier and modifier in lower:
        post = lower.split(modifier, 1)[-1].strip()
        if len(post) > 2:
            candidates.append(_use(post))

    # 2. Strip road-prefix noise ("ku muhanda ujya Remera hafi ya ...")
    road_stripped = _ROAD_PREFIX_RE.sub("", text).strip()
    if road_stripped and road_stripped.lower() != text.lower():
        candidates.append(_use(road_stripped))

    # 3. Full original text (fallback)
    candidates.append(_use(text))

    return candidates


# ---------------------------------------------------------------------------
# 3. Fuzzy landmark matching
# ---------------------------------------------------------------------------

def fuzzy_match_landmark(
    text: str,
    gazetteer: list[dict],
    modifier: str | None = None,
    locality: str | None = None,
    score_cutoff: int = 65,
) -> tuple[dict | None, float, str | None]:
    """
    Match text against all landmark names + aliases using rapidfuzz.
    Tries multiple text variants (post-modifier, stripped, full) and
    returns the best hit across partial_ratio and token_set_ratio scorers.

    `locality`, when given, is passed to `_candidate_queries` so the
    sector token can be removed from queries before scoring — see the
    rationale there. Locality is NOT used to re-rank matches here; that
    validation happens in `resolve` where a mismatch escalates.
    """
    name_to_idx: list[tuple[str, int]] = []
    for idx, lm in enumerate(gazetteer):
        for name in _all_names(lm):
            name_to_idx.append((name, idx))
    query_names = [n for n, _ in name_to_idx]

    best_score = 0
    best_match = None

    for query in _candidate_queries(text, modifier, locality=locality):
        for scorer in (fuzz.partial_ratio, fuzz.token_set_ratio):
            result = rf_process.extractOne(
                query, query_names, scorer=scorer, score_cutoff=score_cutoff
            )
            if result and result[1] > best_score:
                best_score = result[1]
                best_match = result

    if best_match is None:
        return None, 0.0, None

    matched_name, raw_score, list_idx = best_match
    landmark = gazetteer[name_to_idx[list_idx][1]]
    return landmark, raw_score / 100.0, matched_name


# ---------------------------------------------------------------------------
# Coordinate arithmetic
# ---------------------------------------------------------------------------

def offset_coords(lat: float, lon: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    """
    Move (lat, lon) by distance_m metres in direction bearing_deg (0=N, 90=E).
    Uses spherical Earth approximation — accurate to <1 m at these scales.
    """
    R = 6_371_000.0  # Earth radius in metres
    d = distance_m
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    b_r   = math.radians(bearing_deg)

    new_lat_r = math.asin(
        math.sin(lat_r) * math.cos(d / R)
        + math.cos(lat_r) * math.sin(d / R) * math.cos(b_r)
    )
    new_lon_r = lon_r + math.atan2(
        math.sin(b_r) * math.sin(d / R) * math.cos(lat_r),
        math.cos(d / R) - math.sin(lat_r) * math.sin(new_lat_r),
    )
    return math.degrees(new_lat_r), math.degrees(new_lon_r)


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

def resolve(text: str) -> dict:
    """
    Resolve a free-text address description to geographic coordinates.

    Args:
        text: informal delivery description in EN, FR, or Kinyarwanda.

    Returns:
        {
          lat:              float | None,
          lon:              float | None,
          confidence:       float  [0, 1],
          matched_landmark: str   | None,
          rationale:        str,
          escalate:         bool,   # True when confidence < ESCALATION_THRESHOLD
        }
    """
    gazetteer = load_gazetteer()

    # 1. Language detection
    lang = detect_language(text)

    # 2. Modifier & locality extraction.  Locality is extracted BEFORE
    # fuzzy matching so it can be stripped from the query: otherwise a
    # sector token (e.g. "Kacyiru" in "Simba Remera Kacyiru") pulls the
    # fuzzy match toward unrelated landmarks whose alias happens to
    # contain that sector. Locality still drives the validation in
    # step 6; here it only cleans the query.
    modifier, bearing, distance_m = extract_modifier(text)
    locality = extract_locality(text)

    # 3. Fuzzy landmark matching
    landmark, match_score, matched_name = fuzzy_match_landmark(
        text, gazetteer, modifier=modifier, locality=locality
    )

    # 4. Handle no-match case → escalate
    if landmark is None:
        return {
            "lat": None,
            "lon": None,
            "confidence": 0.0,
            "matched_landmark": None,
            "rationale": "No landmark matched above threshold — escalated to dispatcher.",
            "escalate": True,
        }

    # 5. Apply directional offset
    base_lat, base_lon = landmark["lat"], landmark["lon"]
    if modifier:
        lat, lon = offset_coords(base_lat, base_lon, bearing, distance_m)
        rationale = (
            f"Matched '{landmark['name']}' via '{matched_name}' "
            f"(score={match_score:.2f}, lang={lang}); "
            f"applied modifier '{modifier}' → {bearing}° offset, {distance_m} m."
        )
    else:
        lat, lon = base_lat, base_lon
        rationale = (
            f"Matched '{landmark['name']}' via '{matched_name}' "
            f"(score={match_score:.2f}, lang={lang}); no spatial modifier detected."
        )

    # 6. Locality qualifier check.  A user-specified sector like "Kacyiru"
    # in "Bank of Kigali Kacyiru" tells us which *instance* was meant.
    #
    # Note on district-level matching: Kigali districts are coarse — Gasabo
    # alone contains Kacyiru, Remera, Kimironko, Kinyinya, Nyarutarama,
    # Gisozi, etc. So "same district" is NOT evidence of "same sector".
    # We therefore require the sector token to appear in the landmark's
    # name or aliases; anything less than that escalates, with rationale
    # tailored to how close the match got.
    locality = extract_locality(text)
    locality_kind = _locality_match(locality, landmark)
    if locality_kind == "name":
        rationale += f" Locality '{locality}' confirmed in landmark name."
    elif locality_kind == "district":
        rationale += (f" Locality '{locality}' falls inside the matched "
                      f"landmark's district '{landmark.get('district')}', but "
                      f"Kigali districts span multiple sectors — the specific "
                      f"sector is unverified; escalating.")
    elif locality is not None:  # locality_kind == "none" and user DID specify one
        rationale += (f" Locality '{locality}' specified but matched landmark "
                      f"'{landmark['name']}' is in district "
                      f"'{landmark.get('district', '?')}' — likely wrong branch; escalating.")

    # 7. Confidence: fuzzy score × modifier bonus, then cap below the
    # escalation threshold when locality evidence is weaker than name-level.
    # A hard cap (rather than a multiplicative factor) is necessary because
    # very high match_scores × 0.45 can still land at ≥ ESCALATION_THRESHOLD.
    modifier_bonus  = 1.0 if modifier else 0.80
    confidence = round(match_score * modifier_bonus, 3)
    if locality is not None and locality_kind != "name":
        confidence = min(confidence, round(ESCALATION_THRESHOLD - 0.01, 3))
    escalate = confidence < ESCALATION_THRESHOLD

    return {
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "confidence": confidence,
        "matched_landmark": landmark["name"],
        "rationale": rationale,
        "escalate": escalate,
    }


# ---------------------------------------------------------------------------
# Unit tests  (run: python resolver.py)
# ---------------------------------------------------------------------------

class TestResolve(unittest.TestCase):

    def test_english_basic(self):
        r = resolve("behind the big pharmacy on RN3")
        self.assertIsNotNone(r["lat"])
        self.assertGreater(r["confidence"], 0)

    def test_kinyarwanda_modifier(self):
        r = resolve("inyuma ya big pharmacy on RN3, red gate")
        self.assertIsNotNone(r["lat"])
        self.assertEqual(r["escalate"], False)

    def test_french_modifier(self):
        r = resolve("derrière Kimironko Market")
        self.assertIsNotNone(r["lat"])
        self.assertIn("Kimironko", r["matched_landmark"])

    def test_no_match_escalates(self):
        r = resolve("xyzzy zqjwpfm 12345abcxyz")
        self.assertTrue(r["escalate"])
        self.assertIsNone(r["lat"])

    def test_confidence_range(self):
        r = resolve("next to Nyabugogo Bus Terminal")
        self.assertGreaterEqual(r["confidence"], 0.0)
        self.assertLessEqual(r["confidence"], 1.0)

    def test_latency(self):
        start = time.perf_counter()
        for _ in range(100):
            resolve("near Kigali Convention Centre")
        elapsed_ms = (time.perf_counter() - start) * 10  # avg per call in ms
        self.assertLess(elapsed_ms, 100, "Average latency exceeds 100 ms")

    def test_empty_input_escalates(self):
        r = resolve("")
        self.assertTrue(r["escalate"])

    def test_language_detection_kin(self):
        self.assertEqual(detect_language("inyuma ya isoko"), "kin")

    def test_language_detection_fr(self):
        self.assertEqual(detect_language("derrière le grand marché"), "fr")

    def test_offset_applied(self):
        r1 = resolve("Kimironko Market")
        r2 = resolve("behind Kimironko Market")
        self.assertNotAlmostEqual(r1["lat"], r2["lat"], places=4)

    def test_kinyarwanda_iruhande_rwa(self):
        # "iruhande rwa" = "next to/beside" — 90° East offset shifts longitude.
        # "Bank of Kigali Kacyiru" does NOT exist: HQ sits in Nyarugenge,
        # so the locality check must fire → low confidence → escalate.
        r_base     = resolve("Bank of Kigali HQ")
        r_iruhande = resolve("iruhande rwa Bank of Kigali Kacyiru")
        self.assertIn("iruhande rwa", r_iruhande["rationale"])
        self.assertTrue(r_iruhande["escalate"],
            "Locality 'Kacyiru' mismatches HQ district — should escalate.")
        self.assertIn("kacyiru", r_iruhande["rationale"].lower())
        # East offset is still applied to the base landmark
        self.assertNotAlmostEqual(r_base["lon"], r_iruhande["lon"], places=4)

    def test_locality_name_hit_keeps_confidence(self):
        # Locality appears in the landmark's own name → no penalty.
        r = resolve("BPR Kacyiru")
        self.assertFalse(r["escalate"])
        self.assertIn("Kacyiru", r["matched_landmark"])
        self.assertIn("confirmed", r["rationale"].lower())

    def test_locality_mismatch_escalates(self):
        # No modifier, but locality qualifier disagrees with matched branch.
        r = resolve("Bank of Kigali Kacyiru")
        self.assertTrue(r["escalate"])
        self.assertLess(r["confidence"], ESCALATION_THRESHOLD)
        self.assertIn("kacyiru", r["rationale"].lower())
        self.assertIn("wrong branch", r["rationale"].lower())

    def test_locality_district_only_still_escalates(self):
        # "Kigali Heights" is in Gasabo district (same district as Kacyiru)
        # but the landmark name has no sector token, so we CANNOT know
        # whether this Gasabo landmark sits in Kacyiru or in Remera /
        # Kimironko / Kinyinya / ... — must escalate.
        r = resolve("Kigali Heights Kacyiru")
        self.assertTrue(r["escalate"])
        self.assertLess(r["confidence"], ESCALATION_THRESHOLD)
        self.assertIn("sector is unverified", r["rationale"].lower())

    def test_locality_cap_holds_for_perfect_fuzzy_score(self):
        # A multiplicative penalty could leave confidence at threshold when
        # match_score ≈ 1.0; the hard cap must still force escalation.
        r = resolve("Kigali Heights Nyamirambo")  # Gasabo landmark, Nyarugenge sector
        self.assertTrue(r["escalate"])
        self.assertLess(r["confidence"], ESCALATION_THRESHOLD)

    def test_extract_locality(self):
        self.assertEqual(extract_locality("Bank of Kigali Kacyiru"), "kacyiru")
        self.assertEqual(extract_locality("derrière Kimironko Market"), "kimironko")
        self.assertIsNone(extract_locality("xyz abc"))


if __name__ == "__main__":
    unittest.main()
