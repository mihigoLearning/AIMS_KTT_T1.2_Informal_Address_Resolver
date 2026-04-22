"""
Reproducible synthetic data generator for T1.2 Informal Address Resolver.
Run: python generate_data.py
Regenerates gazetteer.json, descriptions.csv, gold.csv in under 2 minutes.
"""

import json
import csv
import random
import math

random.seed(42)


import os

os.makedirs("data", exist_ok=True)

# ---------------------------------------------------------------------------
# 50 Kigali landmarks (real places, realistic coordinates)
# ---------------------------------------------------------------------------
RAW_LANDMARKS = [
    ("Kimironko Market",        ["Marché Kimironko",      "Isoko ya Kimironko"],      "market",    -1.9382, 30.1083, "Gasabo"),
    ("Nyabugogo Bus Terminal",  ["Gare de Nyabugogo",     "Sitasiyo ya Nyabugogo"],   "stop",      -1.9302, 30.0494, "Nyarugenge"),
    ("Kigali Convention Centre",["KCC",                   "Inzu y'Inama"],            "building",  -1.9464, 30.0619, "Nyarugenge"),
    ("Union Trade Centre",      ["UTC",                   "Centre Commercial Union"], "market",    -1.9530, 30.0589, "Nyarugenge"),
    ("Remera Roundabout",       ["Carrefour Remera",      "Akarere ka Remera"],       "stop",      -1.9493, 30.1079, "Gasabo"),
    ("Sonatubes",               ["Sonatubes Kacyiru",     "Sonatubes"],               "building",  -1.9378, 30.0743, "Gasabo"),
    ("Kigali Heights",          ["Kigali Heights Mall",   "Kabari ya Kigali Heights"],"market",    -1.9393, 30.0791, "Gasabo"),
    ("Saint Michel Church",     ["Église Saint Michel",   "Itorero rya Saint Michel"],"church",    -1.9553, 30.0601, "Nyarugenge"),
    ("Nyamirambo Mosque",       ["Grande Mosquée",        "Musigiti ya Nyamirambo"],  "church",    -1.9770, 30.0428, "Nyarugenge"),
    ("Petite Barrière",         ["Petite Barrière",       "Barikiyeri Nto"],          "stop",      -1.9453, 30.0543, "Nyarugenge"),
    ("Grande Barrière",         ["Grande Barrière",       "Barikiyeri Nkuru"],        "stop",      -1.9432, 30.0531, "Nyarugenge"),
    ("Gisozi Memorial",         ["Mémorial de Gisozi",   "Inkumbura ya Gisozi"],     "building",  -1.9278, 30.0773, "Gasabo"),
    ("Kibagabaga Hospital",     ["Hôpital Kibagabaga",    "Ibitaro bya Kibagabaga"],  "pharmacy",  -1.9233, 30.1098, "Gasabo"),
    ("King Faisal Hospital",    ["Hôpital King Faisal",   "Ibitaro bya King Faisal"], "pharmacy",  -1.9342, 30.0780, "Gasabo"),
    ("CHUK Hospital",           ["CHUK",                  "Ibitaro bya CHUK"],        "pharmacy",  -1.9452, 30.0571, "Nyarugenge"),
    ("Kicukiro Centre",         ["Centre Kicukiro",       "Ikigo cya Kicukiro"],      "stop",      -1.9726, 30.0966, "Kicukiro"),
    ("Gikondo Market",          ["Marché Gikondo",        "Isoko ya Gikondo"],        "market",    -1.9644, 30.0720, "Kicukiro"),
    ("Kigali International Airport",["Aéroport de Kigali","Ikaramu ry'Indege Kigali"],"building",  -1.9690, 30.1396, "Gasabo"),
    ("Chez Lando Hotel",        ["Hôtel Chez Lando",      "Hoteli ya Chez Lando"],    "building",  -1.9360, 30.0800, "Gasabo"),
    ("BPR Bank Kacyiru",        ["Banque Populaire Kacyiru","BPR Kacyiru"],           "building",  -1.9354, 30.0752, "Gasabo"),
    ("Bank of Kigali HQ",       ["Banque de Kigali",      "BK HQ"],                   "building",  -1.9510, 30.0605, "Nyarugenge"),
    ("MTN Centre Kigali",       ["MTN Kigali",            "Centre ya MTN"],           "building",  -1.9497, 30.0618, "Nyarugenge"),
    ("Primus Factory",          ["Brasserie Primus",      "Fabrique ya Primus"],      "building",  -1.9580, 30.0490, "Nyarugenge"),
    ("Rwanda Parliament",       ["Parlement rwandais",    "Inteko Ishinga Amategeko"],"building",  -1.9441, 30.0697, "Nyarugenge"),
    ("Kigali City Hall",        ["Hôtel de Ville",        "Inyubako ya Mairie"],      "building",  -1.9499, 30.0605, "Nyarugenge"),
    ("Kigali Post Office",      ["Bureau de Poste",       "Posita ya Kigali"],        "building",  -1.9511, 30.0580, "Nyarugenge"),
    ("Canal Olympia",           ["Cinéma Canal Olympia",  "Cinema Canal"],            "building",  -1.9700, 30.0980, "Kicukiro"),
    ("Simba Supermarket Remera",["Supermarché Simba",     "Iduka rya Simba"],         "market",    -1.9480, 30.1050, "Gasabo"),
    ("Gisimenti Health Centre", ["Centre de Santé Gisimenti","Ivuriro rya Gisimenti"],"pharmacy",  -1.9450, 30.1020, "Gasabo"),
    ("Kacyiru Police Station",  ["Commissariat Kacyiru",  "Polisi ya Kacyiru"],       "building",  -1.9360, 30.0710, "Gasabo"),
    ("Nyarutarama Mall",        ["Mall de Nyarutarama",   "Nyarutarama"],             "market",    -1.9298, 30.1010, "Gasabo"),
    ("Kimisagara Market",       ["Marché Kimisagara",     "Isoko ya Kimisagara"],     "market",    -1.9612, 30.0471, "Nyarugenge"),
    ("Biryogo Market",          ["Marché Biryogo",        "Isoko ya Biryogo"],        "market",    -1.9600, 30.0530, "Nyarugenge"),
    ("Kagarama Health Centre",  ["Centre de Santé Kagarama","Ivuriro rya Kagarama"], "pharmacy",  -1.9808, 30.0911, "Kicukiro"),
    ("Vision 2020 Roundabout",  ["Carrefour Vision 2020", "Akarere Vision 2020"],     "stop",      -1.9238, 30.0832, "Gasabo"),
    ("Ndera Psychiatric Hospital",["Hôpital Ndera",       "Ibitaro bya Ndera"],      "pharmacy",  -1.9097, 30.1214, "Gasabo"),
    ("RBC Kacyiru",             ["Rwanda Biomedical Centre","RBC"],                   "building",  -1.9345, 30.0765, "Gasabo"),
    ("MINISANTE",               ["Ministère de la Santé", "Minisante"],              "building",  -1.9335, 30.0755, "Gasabo"),
    ("Kabeza Shopping Centre",  ["Centre Commercial Kabeza","Kabeza"],                "market",    -1.9750, 30.1050, "Kicukiro"),
    ("Magerwa",                 ["Magerwa Gikondo",       "Magerwa"],                 "building",  -1.9660, 30.0680, "Kicukiro"),
    ("Equity Bank Remera",      ["Equity Bank",           "Banki ya Equity"],         "building",  -1.9490, 30.1060, "Gasabo"),
    ("Nakumatt Supermarket",    ["Carrefour Kigali",      "Supermarché Kigali"],      "market",    -1.9519, 30.0572, "Nyarugenge"),
    ("Kacyiru Health Centre",   ["Centre de Santé Kacyiru","Ivuriro rya Kacyiru"],   "pharmacy",  -1.9380, 30.0730, "Gasabo"),
    ("Kabusunzu Market",        ["Marché Kabusunzu",      "Isoko ya Kabusunzu"],      "market",    -1.9270, 30.0921, "Gasabo"),
    ("Rebero Hill",             ["Colline Rebero",        "Umusozi wa Rebero"],       "building",  -1.9820, 30.0840, "Kicukiro"),
    ("Amahoro National Stadium",["Stade Amahoro",         "Sitade ya Amahoro"],       "building",  -1.9432, 30.1042, "Gasabo"),
    ("Nyanza Bus Stop",         ["Arrêt Nyanza",          "Amaferwa ya Nyanza"],      "stop",      -1.9800, 30.0710, "Kicukiro"),
    ("RN3 Pharmacy",            ["Pharmacie RN3",         "Farumasi ya RN3"],         "pharmacy",  -1.9440, 30.0650, "Nyarugenge"),
    ("Gikondo Bus Stop",        ["Arrêt Gikondo",         "Amaferwa ya Gikondo"],     "stop",      -1.9660, 30.0730, "Kicukiro"),
    ("Kinyinya Market",         ["Marché Kinyinya",       "Isoko ya Kinyinya"],       "market",    -1.9162, 30.1103, "Gasabo"),
]

def build_gazetteer():
    landmarks = []
    for i, (name, aliases, ltype, lat, lon, district) in enumerate(RAW_LANDMARKS, 1):
        landmarks.append({
            "id": i,
            "name": name,
            "aliases": aliases,
            "type": ltype,
            "lat": lat,
            "lon": lon,
            "district": district,
        })
    return landmarks


# ---------------------------------------------------------------------------
# Modifiers and their bearings / distances
# ---------------------------------------------------------------------------
MODIFIERS = [
    ("behind",      180, 60),
    ("inyuma ya",   180, 60),
    ("derrière",    180, 60),
    ("next to",      90, 30),
    ("hafi ya",      90, 30),
    ("near",           0, 50),
    ("opposite",       0, 40),
    ("above",         45, 25),
    ("en face de",    0, 40),
]

EN_NOISE_WORDS  = ["big", "small", "old", "new", "red gate", "blue building", "opposite the", "near the"]
FR_NOISE_WORDS  = ["grand", "petit", "vieux", "nouveau", "portail rouge"]
KIN_NOISE_WORDS = ["nini", "nto", "kera", "mishya"]

TYPO_PAIRS = [
    ("pharmacy", "pharmaacy"), ("market", "markett"), ("hospital", "hospittal"),
    ("church", "churhc"), ("terminal", "termnal"), ("roundabout", "roundabuot"),
    ("kimironko", "kimirnoko"), ("nyabugogo", "nyabugog"), ("kacyiru", "kacyru"),
    ("remera", "remeera"), ("gikondo", "gikoddo"), ("kicukiro", "kicukrio"),
]

EMOJI_SET = ["🏍️", "📍", "✅", "🔴", "🏪", "🏥"]


def add_noise(text, p_typo=0.3, p_emoji=0.2):
    for orig, noisy in TYPO_PAIRS:
        if orig in text.lower() and random.random() < p_typo:
            text = text.lower().replace(orig, noisy, 1)
            break
    if random.random() < p_emoji:
        text = random.choice(EMOJI_SET) + " " + text
    return text


def offset_coords(lat, lon, bearing_deg, distance_m):
    d = distance_m / 1000.0
    R = 6371.0
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    b_r = math.radians(bearing_deg)
    new_lat_r = math.asin(
        math.sin(lat_r) * math.cos(d / R) +
        math.cos(lat_r) * math.sin(d / R) * math.cos(b_r)
    )
    new_lon_r = lon_r + math.atan2(
        math.sin(b_r) * math.sin(d / R) * math.cos(lat_r),
        math.cos(d / R) - math.sin(lat_r) * math.sin(new_lat_r),
    )
    return math.degrees(new_lat_r), math.degrees(new_lon_r)


def generate_description(landmark, lang="en"):
    modifier, bearing, dist = random.choice(MODIFIERS)
    name = landmark["name"]
    aliases = landmark.get("aliases", [])

    # Sometimes use alias instead of canonical name
    if aliases and random.random() < 0.4:
        name = random.choice(aliases)

    noise = ""
    if lang == "en":
        if random.random() < 0.5:
            noise = random.choice(EN_NOISE_WORDS) + " "
        text = f"{modifier} {noise}{name}"
    elif lang == "fr":
        if random.random() < 0.5:
            noise = random.choice(FR_NOISE_WORDS) + " "
        text = f"{modifier} {noise}{name}"
    else:  # kin
        kin_mods = {"behind": "inyuma ya", "next to": "hafi ya", "near": "hafi ya",
                    "opposite": "imbere ya", "above": "hejuru ya"}
        modifier = kin_mods.get(modifier, modifier)
        if random.random() < 0.5:
            noise = random.choice(KIN_NOISE_WORDS) + " "
        text = f"{modifier} {noise}{name}"

    text = add_noise(text)

    # Compute true coords with Gaussian offset in modifier direction + 60m std
    actual_dist = dist + random.gauss(0, 20)
    actual_dist = max(5, actual_dist)
    true_lat, true_lon = offset_coords(landmark["lat"], landmark["lon"], bearing, actual_dist)

    return text.strip(), lang, landmark["id"], true_lat, true_lon


def main():
    gazetteer = build_gazetteer()
    with open("data/gazetteer.json", "w") as f:
        json.dump(gazetteer, f, indent=2, ensure_ascii=False)
    print(f"gazetteer.json: {len(gazetteer)} landmarks")

    langs = ["en"] * 90 + ["fr"] * 60 + ["kin"] * 50
    random.shuffle(langs)

    rows = []
    for i, lang in enumerate(langs, 1):
        landmark = random.choice(gazetteer)
        text, lang_used, lm_id, true_lat, true_lon = generate_description(landmark, lang)
        rows.append({
            "description_id": i,
            "description_text": text,
            "language_hint_optional": lang_used,
            "landmark_id": lm_id,
            "true_lat": round(true_lat, 6),
            "true_lon": round(true_lon, 6),
        })

    with open("data/descriptions.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["description_id", "description_text", "language_hint_optional"])
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r[k] for k in ["description_id", "description_text", "language_hint_optional"]})
    print(f"descriptions.csv: {len(rows)} rows")

    # gold.csv: first 25 seeded + 25 held-out (rows 26-50)
    gold_rows = rows[:50]
    with open("data/gold.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["description_id", "true_lat", "true_lon"])
        writer.writeheader()
        for r in gold_rows:
            writer.writerow({"description_id": r["description_id"],
                             "true_lat": r["true_lat"],
                             "true_lon": r["true_lon"]})
    print(f"gold.csv: {len(gold_rows)} rows (25 seeded + 25 held-out)")


if __name__ == "__main__":
    main()
