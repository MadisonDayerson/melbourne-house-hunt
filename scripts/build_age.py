"""Estimate when each house was built from its listing description, and pull out comfort features.

Listings don't carry a year-built field, so this reads the agent's description:
  1. an explicit year ("built in 2016", "c.1925", "2019-built")            -> confidence "stated"
  2. "brand new", "near new", "only 4 years old"                           -> confidence "stated"
  3. architectural style (Victorian, Edwardian, Californian bungalow,
     art deco, 1960s, cream brick, ...)                                    -> confidence "style"
  4. nothing in the text, but the suburb is a post-2000 growth-area estate -> confidence "suburb guess"
Otherwise the age is unknown.

Output: data/build_age.json {listing id: {year, era, bucket, confidence, evidence, renovated, comfort}}
"""
import json, re, pathlib

D = pathlib.Path(__file__).resolve().parent.parent / "data"
NOW = 2026

# Suburbs that are almost entirely post-2000 estates (Victorian Planning Authority growth corridors)
GROWTH = {
    "Tarneit", "Truganina", "Williams Landing", "Point Cook", "Wyndham Vale", "Manor Lakes", "Mambourin", "Rockbank",
    "Aintree", "Fraser Rise", "Deanside", "Thornhill Park", "Weir Views", "Strathtulloh", "Cobblebank", "Bonnie Brook",
    "Harkness", "Grangefields", "Plumpton", "Mickleham", "Kalkallo", "Donnybrook", "Wollert", "Mernda", "Doreen",
    "Clyde", "Clyde North", "Cranbourne East", "Botanic Ridge", "Officer", "Officer South", "Beveridge", "Brookfield",
    "Taylors Hill", "Caroline Springs", "Burnside Heights", "Sanctuary Lakes",
}

ERA = [  # (bucket, label)
    ("new", "Built 2020 or later"), ("modern", "Built 2000–2019"), ("late", "Built 1945–1999"),
    ("period", "Built before 1945"),
]


def bucket(year):
    return "new" if year >= 2020 else "modern" if year >= 2000 else "late" if year >= 1945 else "period"


STYLE = [  # pattern, approx year, era label
    (r"\b(?:victorian|victorian[- ]era)\s+(?:terrace|home|house|cottage|villa|style|era|weatherboard|charm|residence|beauty|classic)"
     r"|double[- ]fronted victorian|\bboom[- ]style\b|\bvictorian\s+period", 1890, "Victorian era (1850s–1901)"),
    (r"\bedwardian\b", 1910, "Edwardian (1901–1918)"),
    (r"californian? bungalow|\bart deco\b|\binter[- ]?war\b|1920s|1930s", 1930, "Interwar (1918–1940)"),
    (r"\bperiod (?:home|house|features|charm|residence|style|cottage)|\boriginal period\b|\bera charm\b", 1920, "Period home (before 1940)"),
    (r"\bpost[- ]?war\b|1940s|1950s|\bmid[- ]century\b", 1955, "Post-war (1945–1960s)"),
    (r"1960s|1970s|\bcream brick\b|\bretro (?:home|charm|style)", 1970, "1960s–70s"),
    (r"1980s|1990s", 1990, "1980s–90s"),
]

COMFORT = [
    (r"double[- ]glaz", "Double glazing"), (r"\bsolar (?:panels|power|system|hot water)|\bsolar\b", "Solar"),
    (r"ducted (?:gas )?heating|ducted heat", "Ducted heating"), (r"refrigerated cooling|ducted (?:refrigerated )?(?:cooling|air|reverse)", "Ducted cooling"),
    (r"split[- ]system|reverse[- ]cycle", "Split system"), (r"evaporative", "Evaporative cooling"),
    (r"hydronic", "Hydronic heating"), (r"(\d(?:\.\d)?)[- ]star energy", "Energy rating"),
    (r"dishwasher", "Dishwasher"), (r"insulat", "Insulation mentioned"),
]


def estimate(desc, byline, suburb):
    t = " " + (byline or "") + " . " + (desc or "") + " "
    tl = t.lower()

    def snip(m):
        a, b = max(0, m.start() - 40), min(len(t), m.end() + 40)
        return "…" + re.sub(r"\s+", " ", t[a:b]).strip() + "…"

    # 1. explicit years
    for pat in [r"\b(?:built|constructed|completed|erected)\s+(?:in|circa|around|c\.?)?\s*((?:18|19|20)\d\d)\b",
                r"\b(?:circa|c\.)\s*((?:18|19|20)\d\d)\b",
                r"\b((?:19|20)\d\d)[- ](?:built|constructed)\b"]:
        m = re.search(pat, tl)
        if m and 1840 <= int(m.group(1)) <= NOW:
            y = int(m.group(1))
            return {"year": y, "era": f"Built {y}", "bucket": bucket(y), "confidence": "stated", "evidence": snip(m)}
    m = re.search(r"(?<!age of )(?<!over )(?<!under )(?<!aged )\b(?:only|just|approx(?:imately)?\.?|around)?\s*(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s+years?\s+(?:old|young)\b"
                  r"(?! (?:or|and) (?:over|older|under))", tl)
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    if m and re.search(r"(?:age of|over|under|aged|anyone)\s*$", tl[max(0, m.start() - 14):m.start() + len(m.group(0)) - len(m.group(0).lstrip())]):
        m = None  # "over the age of 18 years old" is about applicants, not the house
    if m:
        n = words.get(m.group(1)) or int(m.group(1))
        if n <= 40:
            y = NOW - n
            return {"year": y, "era": f"About {n} year{'s' if n > 1 else ''} old (~{y})", "bucket": bucket(y), "confidence": "stated", "evidence": snip(m)}
    m = re.search(r"brand[- ]new (?:home|house|townhouse|build|residence|property|double storey|single storey|family home)|never (?:been )?lived in"
                  r"|first (?:ever )?(?:occupant|tenants?|time leased)|be the first to (?:live|call|enjoy|occupy)|newly (?:built|constructed|completed)", tl)
    if m:
        return {"year": NOW, "era": "Brand new", "bucket": "new", "confidence": "stated", "evidence": snip(m)}
    m = re.search(r"brand[- ]new\b(?!\s+(?:kitchen|carpets?|flooring|floors|paint|appliances|bathrooms?|ensuite|oven|cooktop|dishwasher|blinds|curtains|heating|cooling|split|fence|deck|hot water|fixtures|fittings|vanit|tiles|benchtops?|light|window))", tl)
    if m:
        return {"year": NOW, "era": "Brand new", "bucket": "new", "confidence": "stated", "evidence": snip(m)}
    m = re.search(r"\b(?:near|nearly|almost|as[- ]new|virtually)[- ]new\b(?![\s,:–-]{0,4}(?:\w+[\s,]+){0,2}(?:carpets?|paint|renovat|kitchen|appliances|flooring|bathroom))", tl)
    if m:
        return {"year": NOW - 3, "era": "Near new (about 1–5 years)", "bucket": "new", "confidence": "stated", "evidence": snip(m)}
    # 2. style
    for pat, y, label in STYLE:
        m = re.search(pat, tl)
        if m:
            return {"year": y, "era": label, "bucket": bucket(y), "confidence": "style", "evidence": snip(m)}
    # 3. growth-area suburb
    if suburb in GROWTH:
        return {"year": 2012, "era": "Likely 2000s or newer (new-estate suburb)", "bucket": "modern", "confidence": "suburb guess", "evidence": None}
    return {"year": None, "era": "Unknown", "bucket": "unknown", "confidence": None, "evidence": None}


def main():
    listings = [l for f in ("listings_enriched.json", "listings_enriched_solo.json") if (D / f).exists()
                for l in json.load(open(D / f))]
    out = {}
    for l in listings:
        f = D / "cache" / "details" / f"{l['id']}.json"
        det = json.loads(f.read_text()) if f.exists() else {}
        desc, by = det.get("description", ""), det.get("byline", "")
        r = estimate(desc, by, l["suburb"])
        tl = (by + " " + desc).lower()
        r["renovated"] = bool(re.search(r"\b(?:fully |newly |recently |freshly )?renovated|refurbished|brand new kitchen|new kitchen|updated throughout", tl))
        comfort = []
        for pat, label in COMFORT:
            m = re.search(pat, tl)
            if m:
                comfort.append(f"{m.group(1)}-star energy" if label == "Energy rating" else label)
        feats = det.get("features") or {}
        for k in ("heating", "airconditioning"):
            for v in feats.get(k, []):
                lab = {"ducted heating": "Ducted heating", "air-conditioning": "Air conditioning", "split system heating": "Split system",
                       "gas heating": "Gas heating", "hydronic heating": "Hydronic heating"}.get(v.lower(), v.capitalize())
                if lab not in comfort:
                    comfort.append(lab)
        r["comfort"] = comfort[:6]
        r["has_text"] = bool(desc)
        out[str(l["id"])] = r
    json.dump(out, open(D / "build_age.json", "w"), indent=1)
    from collections import Counter
    print("with description:", sum(1 for v in out.values() if v["has_text"]), "of", len(out))
    print(Counter(v["confidence"] for v in out.values()))
    print(Counter(v["bucket"] for v in out.values()))


if __name__ == "__main__":
    main()
