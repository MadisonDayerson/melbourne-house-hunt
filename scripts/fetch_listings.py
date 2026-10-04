"""Collect current 4+ bedroom rental listings across metropolitan Melbourne from rent.com.au search pages.

Reads the listing data embedded in public search result pages (allowed by the site's robots.txt),
politely, one request every few seconds. Suburbs come from data/suburbs.json (built by crime.py). Each suburb's results are cached in
data/cache/ for the day, so an interrupted run picks up where it stopped.
Output: data/listings_raw.json
"""
import json, re, time, urllib.request, pathlib

SUBURBS_FILE = pathlib.Path(__file__).resolve().parent.parent / "data" / "suburbs.json"
MAX_PAGES = 3  # results also include neighbouring suburbs, so a few pages per suburb covers it
MAX_RENT = 1900  # a little above the $1,750 group ceiling so near-misses show up
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "listings_raw.json"


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
    }


def main():
    cache = OUT.parent / "cache" / time.strftime("%Y-%m-%d")
    cache.mkdir(parents=True, exist_ok=True)
    suburbs = json.load(open(SUBURBS_FILE))
    for i, s in enumerate(suburbs):
        f = cache / f"{slug(s['suburb'])}.json"
        if f.exists():
            continue
        got = []
        for page in range(1, MAX_PAGES + 1):
            url = f"https://www.rent.com.au/properties/{slug(s['suburb'])}-vic-{s['postcode']}?bedrooms=4&page={page}"
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
    rows = [r for r in rows.values() if (r["beds"] or 0) >= 4 and r["rent"] and r["rent"] <= MAX_RENT]
    OUT.write_text(json.dumps(rows, indent=1))
    print("saved", len(rows), "to", OUT)


if __name__ == "__main__":
    main()
