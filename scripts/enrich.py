"""Score each listing's location across metropolitan Melbourne: walkability, transit, noise, air, safety.

Inputs (data/): cache/listings_raw.json, osm_amenities.json, osm_roads.json,
crime_suburb_jun2026.json, suburb_population.json
Outputs: data/listings_enriched.json, data/basemap.json

Method notes (also shown in the app's "How scores work" panel):
- Walking distance = straight-line distance x 1.3 (typical street-network detour factor), 80 m per minute.
- 20-minute neighbourhood (Plan Melbourne 2017-2050): daily needs within an 800 m walk.
- Public transport standards (Victoria Planning Provisions Clause 56.04-1): bus 400 m, tram 600 m, train 800 m.
- Traffic air pollution falls off sharply within ~150-300 m of busy roads (EPA Victoria / CARB 150 m guidance).
- Noise: WHO Environmental Noise Guidelines (2018) - road, rail and aircraft are the main sources;
  distance to the source stands in for measured levels, which aren't published per address.
- Crime: Crime Statistics Agency Victoria, recorded offences year ending June 2026, by suburb,
  per 1,000 residents (2021 Census population). Victoria overall: 86.8 per 1,000.
"""
import json, math, pathlib, collections, re, sys, gzip, datetime
from zoneinfo import ZoneInfo

D = pathlib.Path(__file__).resolve().parent.parent / "data"
TODAY = datetime.datetime.now(ZoneInfo("Australia/Melbourne")).date().isoformat()  # GitHub runs on UTC
KEEP_GONE_DAYS = 14  # listings that disappear stay (marked "no longer advertised") this long


def load_json(name):
    """Read data/<name>, or its .gz copy (the compressed OSM files are what's kept in git)."""
    if (D / name).exists():
        return json.load(open(D / name))
    with gzip.open(D / (name + ".gz"), "rt") as f:
        return json.load(f)
SOLO = "--solo" in sys.argv  # studio-2 bed search for one person (see fetch_listings.py)
RAW, OUT = ("listings_raw_solo.json", "listings_enriched_solo.json") if SOLO else ("listings_raw.json", "listings_enriched.json")
DETOUR, WALK_M_PER_MIN = 1.3, 80
VIC_RATE = 86.8  # offences per 1,000 residents, Victoria, year ending June 2026
CBD = (-37.8183, 144.9671)  # Flinders Street Station
ESSENDON_FIELDS = (-37.7281, 144.9019)
MELB_AIRPORT = (-37.6690, 144.8410)
MOORABBIN_AIRPORT = (-37.9758, 145.1022)
AVALON_AIRPORT = (-38.0394, 144.4694)
MIN_POP = 1000  # crime rates for suburbs with fewer residents than this are too noisy to score

SUBURBS = {s["suburb"].lower(): s for s in json.load(open(D / "suburbs.json"))}

LAT0 = -37.85
KX, KY = 111320 * math.cos(math.radians(LAT0)), 110540


def xy(lat, lng):
    return (lng * KX, lat * KY)


def dist(a, b):
    ax, ay = xy(*a); bx, by = xy(*b)
    return math.hypot(ax - bx, ay - by)


def seg_dist(p, a, b):
    px, py = p; ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


# ---------- amenities ----------
def category(tags):
    s, a, l, r, h = (tags.get(k) for k in ("shop", "amenity", "leisure", "railway", "highway"))
    if s == "supermarket": return "supermarket"
    if s in ("greengrocer", "butcher", "bakery"): return "fresh"
    if a == "pharmacy": return "pharmacy"
    if a in ("doctors", "clinic"): return "gp"
    if a in ("cafe", "restaurant"): return "cafe"
    if a in ("pub", "bar"): return "bar"
    if l in ("park", "dog_park", "playground"): return "park"
    if l in ("fitness_centre", "sports_centre", "swimming_pool"): return "gym"
    if a in ("library", "community_centre"): return "library"
    if r == "station" and tags.get("station") != "light_rail": return "train"
    if r == "tram_stop": return "tram"
    if h == "bus_stop": return "bus"
    if a == "cinema": return "cinema"
    if a == "marketplace": return "fresh"
    return None


CELL = 0.01  # ~1 km grid for fast nearest-neighbour lookups


def cell(lat, lng):
    return (int(math.floor(lat / CELL)), int(math.floor(lng / CELL)))


amen = collections.defaultdict(list)
for e in load_json("osm_amenities.json")["elements"]:
    c = category(e.get("tags", {}))
    if not c:
        continue
    lat = e.get("lat") or (e.get("center") or {}).get("lat")
    lng = e.get("lon") or (e.get("center") or {}).get("lon")
    if lat is None:
        continue
    if c == "train" and "tram" in (e["tags"].get("name", "").lower()):
        continue
    amen[c].append((lat, lng, e["tags"].get("name", "")))
print({k: len(v) for k, v in amen.items()})
grid = {c: collections.defaultdict(list) for c in amen}
for c, items in amen.items():
    for it in items:
        grid[c][cell(it[0], it[1])].append(it)

# ---------- roads & rail ----------
roads = {"motorway": {}, "major": {}, "rail": {}}  # grid cell -> segments
basemap = {"motorway": [], "major": [], "rail": []}
for w in load_json("osm_roads.json")["elements"]:
    g = w.get("geometry")
    if not g:
        continue
    t = w["tags"]
    if t.get("railway") == "rail":
        if t.get("service") in ("yard", "siding", "spur"):
            continue
        k = "rail"
    elif t.get("highway") in ("motorway", "motorway_link"):
        k = "motorway"
    else:
        k = "major"  # trunk + primary arterials (e.g. Sydney Rd, Bell St, High St)
    for i in range(len(g) - 1):
        a, b = g[i], g[i + 1]
        seg = (xy(a["lat"], a["lon"]), xy(b["lat"], b["lon"]), t.get("name") or t.get("ref") or "")
        for cc in {cell(a["lat"], a["lon"]), cell(b["lat"], b["lon"])}:
            roads[k].setdefault(cc, []).append(seg)
    basemap[k].append([(round(p["lat"], 4), round(p["lon"], 4)) for p in g])


def around(p, rings):
    ci, cj = cell(*p)
    for di in range(-rings, rings + 1):
        for dj in range(-rings, rings + 1):
            yield (ci + di, cj + dj)


def nearest_line(p, k, rings=6):
    """Nearest freeway/main road/rail segment within ~6 km (5 km+ is reported as far)."""
    best, name = 1e9, ""
    px = xy(*p)
    for cc in around(p, rings):
        for a, b, n in roads[k].get(cc, ()):
            d = seg_dist(px, a, b)
            if d < best:
                best, name = d, n
    return round(min(best, 9999)), name


def nearest(p, c, rings=4):
    best = (1e9, "")
    for cc in around(p, rings):
        for lat, lng, n in grid[c].get(cc, ()):
            d = dist(p, (lat, lng))
            if d < best[0]:
                best = (d, n)
    return round(min(best[0] * DETOUR, 9999)), best[1]


def count_within(p, c, walk_m):
    r = walk_m / DETOUR
    return sum(1 for cc in around(p, 1) for lat, lng, _ in grid[c].get(cc, ())
               if dist(p, (lat, lng)) <= r)


# ---------- crime ----------
crime = json.load(open(D / "crime_suburb_jun2026.json"))
pop = json.load(open(D / "suburb_population.json"))


def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, round(v)))


DAILY_NEEDS = [
    ("supermarket", "Supermarket"), ("fresh", "Fresh food (grocer, butcher, bakery)"),
    ("pharmacy", "Pharmacy"), ("gp", "GP / medical clinic"), ("cafe", "Café or restaurant"),
    ("park", "Park or playground"), ("gym", "Gym, pool or sports centre"),
    ("library", "Library or community centre"),
]

out, missing_pop = [], set()
for L in json.load(open(D / "cache" / RAW)):
    meta = SUBURBS.get(re.sub(r"^saint ", "st ", L["suburb"].lower()))
    beds_ok = 0 <= (L["beds"] or 0) <= 2 if SOLO else 4 <= (L["beds"] or 0) <= 8
    min_rent = 180 if SOLO else 350  # below this it's a parking space, storage or a single room
    if not meta or not L["lat"] or not beds_ok or L["rent"] < min_rent:
        continue  # outside metro Melbourne, or a per-room/odd listing
    L["suburb"] = meta["suburb"]
    p = (L["lat"], L["lng"])
    near = {c: nearest(p, c) for c, _ in DAILY_NEEDS}
    for c in ("train", "tram", "bus", "bar", "cinema"):
        near[c] = nearest(p, c)
    counts = {"cafe": count_within(p, "cafe", 800), "bar": count_within(p, "bar", 800),
              "bus": count_within(p, "bus", 400), "tram": count_within(p, "tram", 600),
              "shops": sum(count_within(p, c, 800) for c in ("supermarket", "fresh", "pharmacy"))}

    # 20-minute neighbourhood: daily needs within an 800 m walk, plus frequent transport
    pt_ok = near["train"][0] <= 800 or near["tram"][0] <= 600
    met = [c for c, _ in DAILY_NEEDS if near[c][0] <= 800] + (["pt"] if pt_ok else [])
    twenty = round(100 * len(met) / (len(DAILY_NEEDS) + 1))

    # Transit: Clause 56.04-1 walking-distance standards, weighted by mode capacity/frequency
    tr = 0
    tr += 45 if near["train"][0] <= 800 else 30 if near["train"][0] <= 1200 else 15 if near["train"][0] <= 2000 else 0
    tr += 35 if near["tram"][0] <= 600 else 18 if near["tram"][0] <= 1000 else 0
    tr += 20 if near["bus"][0] <= 400 else 10 if near["bus"][0] <= 800 else 0
    transit = clamp(tr)

    mw, mw_name = nearest_line(p, "motorway")
    mj, mj_name = nearest_line(p, "major")
    rl, _ = nearest_line(p, "rail")
    ef = round(dist(p, ESSENDON_FIELDS)); ma = round(dist(p, MELB_AIRPORT))
    mo = round(dist(p, MOORABBIN_AIRPORT)); av = round(dist(p, AVALON_AIRPORT))
    bars_close = sum(1 for lat, lng, _ in amen["bar"] if dist(p, (lat, lng)) <= 150)

    noise_flags, n = [], 100
    if mw < 100: n -= 45; noise_flags.append(f"Freeway {mw} m away ({mw_name})")
    elif mw < 300: n -= 25; noise_flags.append(f"Freeway {mw} m away ({mw_name})")
    elif mw < 500: n -= 10; noise_flags.append(f"Freeway within 500 m ({mw_name})")
    if mj < 50: n -= 30; noise_flags.append(f"On or beside a main road ({mj_name}, {mj} m)")
    elif mj < 150: n -= 15; noise_flags.append(f"Main road {mj} m away ({mj_name})")
    if rl < 100: n -= 20; noise_flags.append(f"Railway line {rl} m away")
    elif rl < 250: n -= 8; noise_flags.append(f"Railway line {rl} m away")
    if bars_close: n -= min(15, 5 * bars_close); noise_flags.append(f"{bars_close} pub/bar within 150 m")
    if ef < 3000: n -= 15; noise_flags.append(f"Essendon Fields airport {ef/1000:.1f} km away")
    elif ef < 5000: n -= 6; noise_flags.append(f"Essendon Fields airport {ef/1000:.1f} km away")
    if ma < 8000: n -= 10; noise_flags.append(f"Melbourne Airport {ma/1000:.1f} km away (flight paths)")
    if mo < 3000: n -= 10; noise_flags.append(f"Moorabbin airport {mo/1000:.1f} km away (light aircraft)")
    if av < 8000: n -= 8; noise_flags.append(f"Avalon Airport {av/1000:.1f} km away")
    quiet = clamp(n)

    air_flags, a = [], 100
    if mw < 150: a -= 40; air_flags.append(f"Within 150 m of a freeway ({mw_name})")
    elif mw < 300: a -= 20; air_flags.append(f"Freeway {mw} m away ({mw_name})")
    elif mw < 500: a -= 8; air_flags.append(f"Freeway {mw} m away")
    if mj < 50: a -= 25; air_flags.append(f"Fronts a main road ({mj_name})")
    elif mj < 150: a -= 12; air_flags.append(f"Main road {mj} m away ({mj_name})")
    air = clamp(a)

    sub = L["suburb"]
    c = crime["suburb"].get(sub)
    ppl = pop.get(sub)
    if c and ppl and ppl >= MIN_POP:
        rate = 1000 * c["total"] / ppl
        burg = 1000 * c.get("burglary", 0) / ppl
        assault = 1000 * c.get("assault", 0) / ppl
        ratio = rate / VIC_RATE
        safety = clamp(100 - 50 * (ratio - 0.5))
        crime_info = {"rate": round(rate, 1), "burglary": round(burg, 1), "assault": round(assault, 1),
                      "offences": c["total"], "population": ppl}
    else:
        missing_pop.add(sub); safety, crime_info = None, None

    out.append({**L, "region": meta["region"], "lga": meta["lga"],
        "cbd_km": round(dist(p, CBD) / 1000, 1),
        "near": {k: {"m": v[0], "name": v[1]} for k, v in near.items()},
        "counts": counts, "met": met, "twenty": twenty, "transit": transit,
        "roads": {"motorway": mw, "motorway_name": mw_name, "major": mj, "major_name": mj_name, "rail": rl},
        "quiet": quiet, "noise_flags": noise_flags, "air": air, "air_flags": air_flags,
        "safety": safety, "crime": crime_info,
    })

print("listings", len(out), "missing population:", sorted(missing_pop))
# ---------- history: first seen / no longer advertised ----------
prev = {str(l["id"]): l for l in json.load(open(D / OUT))} if (D / OUT).exists() else {}
seen = set()
for l in out:
    k = str(l["id"]); seen.add(k)
    if k in prev:   # known listing: keep its date (older files have none, so use the advertised date)
        l["first_seen"] = prev[k].get("first_seen") or prev[k].get("listed") or TODAY
    else:           # new since the last run (on the very first run, use the advertised date)
        l["first_seen"] = TODAY if prev else (l.get("listed") or TODAY)
    l.pop("gone", None)
kept_gone = 0
for k, l in prev.items():
    if k in seen:
        continue
    gone = l.get("gone") or TODAY
    if (datetime.date.fromisoformat(TODAY) - datetime.date.fromisoformat(gone)).days <= KEEP_GONE_DAYS:
        l["gone"] = gone; out.append(l); kept_gone += 1
new = sum(1 for l in out if l.get("first_seen") == TODAY and not l.get("gone"))
print(f"history: {new} new today, {kept_gone} no longer advertised (kept {KEEP_GONE_DAYS} days)")
json.dump(out, open(D / OUT, "w"), indent=1)
if SOLO:
    sys.exit()  # the basemap comes from the share-house run


# ---------- basemap: simplified major roads + rail for the in-page map ----------
def simplify(pts, tol=0.0012):
    if len(pts) < 3:
        return pts
    (y1, x1), (y2, x2) = pts[0], pts[-1]
    dmax, idx = 0, 0
    for i in range(1, len(pts) - 1):
        y, x = pts[i]
        num = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1)
        den = math.hypot(y2 - y1, x2 - x1) or 1e-12
        if num / den > dmax:
            dmax, idx = num / den, i
    if dmax > tol:
        return simplify(pts[: idx + 1], tol)[:-1] + simplify(pts[idx:], tol)
    return [pts[0], pts[-1]]


bm = {k: [simplify(l) for l in v] for k, v in basemap.items()}
stations = [(round(a, 4), round(b, 4), n.replace(" Station", "").replace(" Railway", ""))
            for a, b, n in amen["train"] if n]
json.dump({"lines": bm, "stations": stations}, open(D / "basemap.json", "w"), separators=(",", ":"))
print("basemap points", sum(len(l) for v in bm.values() for l in v))
