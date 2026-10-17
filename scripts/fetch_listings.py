"""Collect current rental listings across metropolitan Melbourne from rent.com.au search pages.

Three pools, so a hunt for any household size has listings to choose from:
  python3 scripts/fetch_listings.py --pool large   4+ bedrooms up to $1,900/wk (the default)
  python3 scripts/fetch_listings.py --pool three   3 bedrooms up to $1,400/wk
  python3 scripts/fetch_listings.py --pool small   studio to 2 bedrooms up to $900/wk (--solo also works)

Reads the listing data embedded in public search result pages (allowed by the site's robots.txt),
politely, one request every few seconds. Suburbs come from data/suburbs.json (built by crime.py). Each suburb's results are cached in
data/cache/ for the day, so an interrupted run picks up where it stopped.
Output: data/cache/listings_raw_<pool>.json
"""
import json, re, sys, time, urllib.request, pathlib

SUBURBS_FILE = pathlib.Path(__file__).resolve().parent.parent / "data" / "suburbs.json"
# surrounding_suburbs=0 keeps each search to its own suburb; rent_high is the site's max-rent filter;
# bedrooms=N means N or more; max_pages is high for small places because the CBD alone has 500+. Rent caps sit a little above realistic budgets so near-misses show up.
PROFILES = {
    "large": {"query": "bedrooms=4", "max_pages": 3, "min_beds": 4, "max_beds": 99, "max_rent": 1900,
              "out": "listings_raw.json", "published": "listings_enriched.json"},
    "three": {"query": "surrounding_suburbs=0&bedrooms=3&rent_high=1400", "max_pages": 20, "min_beds": 3, "max_beds": 3,
              "max_rent": 1400, "out": "listings_raw_three.json", "published": "listings_enriched_three.json"},
    "small": {"query": "surrounding_suburbs=0&rent_high=900", "max_pages": 40, "min_beds": 0, "max_beds": 2,
              "max_rent": 900, "out": "listings_raw_solo.json", "published": "listings_enriched_solo.json"},
}
POOL = "small" if "--solo" in sys.argv else (sys.argv[sys.argv.index("--pool") + 1] if "--pool" in sys.argv else "large")
PROFILE = PROFILES[POOL]
MAX_PAGES = PROFILE["max_pages"]
MAX_RENT = PROFILE["max_rent"]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "cache" / PROFILE["out"]  # raw downloads stay out of git; the scored file is what's published


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def extract(html):
    """Pull the propertiesData JSON out of the escaped Next.js payload."""
    i = html.find('\\"propertiesData\\":')
    if i < 0:
        return [], None
    s = html[i:]
    # find the properties array: unescape the payload chunk, then raw_decode from the array start
    chunk = s[: 2_000_000].encode().decode("unicode_escape", "ignore")
    j = chunk.find('"properties":')
    arr, _ = json.JSONDecoder().raw_decode(chunk[j + len('"properties":'):])
    m = re.search(r'"count":(\d+)', chunk)
    return arr, int(m.group(1)) if m else None


def rent_value(s):
    m = re.search(r"\$+([\d,]+)", s or "")
    return int(m.group(1).replace(",", "")) if m else None


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def row(p):
    return {
        "id": p["id"], "url": p.get("url"), "type": p.get("property_type"),
        "street": (p.get("street_address") or "").strip().rstrip(","),
        "suburb": (p.get("suburb") or "").title(), "postcode": p.get("postcode"),
        "rent_text": (p.get("weekly_rent") or "").replace("$$", "$"),
        "rent": rent_value(p.get("weekly_rent")),
        "beds": p.get("bedrooms"), "baths": p.get("bathrooms"), "cars": p.get("car_spaces"),
        "pets": p.get("pets_allowed"),
        "lat": p.get("latitude"), "lng": p.get("longitude"),
        "available": p.get("date_available"), "listed": (p.get("activated_at") or "")[:10],
        "walk_score": (p.get("walkability_score") or {}).get("walk_score"),
        "transit_score": (p.get("walkability_score") or {}).get("transit_score"),
        "agency": ((p.get("contact") or {}).get("company") or {}).get("trading_name"),
        "photos": photo_paths(p),
    }


PHOTO_BASE = "https://cdn.rent.com.au/photos/images/"


def photo_paths(p, n=4):
    """First few photos, stored without the CDN prefix and cache-busting query to keep the data small.
    The page puts PHOTO_BASE back on and shows them straight from rent.com.au's image server."""
    out = []
    for g in (p.get("gallery") or []):
        u = (g or {}).get("url") or ""
        if g.get("gallery_type", "photo") == "photo" and u.startswith(PHOTO_BASE):
            out.append(u[len(PHOTO_BASE):].split("?")[0])
        if len(out) == n:
            break
    return out


def main():
    cache = DATA / "cache" / (time.strftime("%Y-%m-%d") + ("" if POOL == "large" else "-" + POOL))
    cache.mkdir(parents=True, exist_ok=True)
    suburbs = json.load(open(SUBURBS_FILE))
    for i, s in enumerate(suburbs):
        f = cache / f"{slug(s['suburb'])}.json"
        if f.exists():
            continue
        got = []
        for page in range(1, MAX_PAGES + 1):
            url = f"https://www.rent.com.au/properties/{slug(s['suburb'])}-vic-{s['postcode']}?{PROFILE['query']}&page={page}"
            try:
                props, total = extract(get(url))
            except Exception as e:
                print("ERR", url, e); props, total = [], 0
            got += [row(p) for p in props]
            time.sleep(2)
            if len(props) < 25 or (total and page * 25 >= total):
                break
        f.write_text(json.dumps(got))
        print(f"[{i + 1}/{len(suburbs)}] {s['suburb']}: {len(got)}", flush=True)

    rows = {}
    for f in cache.glob("*.json"):
        for r in json.loads(f.read_text()):
            rows[r["id"]] = r
    rows = [r for r in rows.values() if PROFILE["min_beds"] <= (r["beds"] or 0) <= PROFILE["max_beds"]
            and r["rent"] and r["rent"] <= MAX_RENT and (r["type"] or "").lower() not in ("share", "room", "share house")]
    # Safety check: a big drop usually means the site was down or refused us, not that half of
    # Melbourne's rentals were leased overnight. Stop rather than wipe listings from the website.
    published = DATA / PROFILE["published"]  # compare with what the website shows (raw files aren't kept on GitHub)
    if published.exists() and "--force" not in sys.argv:
        before = sum(1 for l in json.loads(published.read_text()) if not l.get("gone"))
        if before and len(rows) < 0.7 * before:
            print(f"ABORT: only {len(rows)} listings today vs {before} last time; keeping the old file")
            sys.exit(1)
    OUT.write_text(json.dumps(rows, indent=1))
    print("saved", len(rows), "to", OUT)


if __name__ == "__main__":
    main()
