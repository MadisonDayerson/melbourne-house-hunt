"""Renter-friendliness evidence for each agency managing a listing.

1. Public reviews: ProductReview.com.au rating and review count for the agency, or for its
   franchise brand (Ray White, Barry Plant, ...) when the office has no page of its own.
2. Regulator record: Consumer Affairs Victoria (CAV) news releases about enforcement against
   estate agents (bond and trust-account offences, rental-law breaches, VCAT and court action),
   matched to agency names.

Output: data/agencies.json {agency name: {...}}. Progress: data/agencies.log
"""
import json, re, time, html as H, pathlib, urllib.parse, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fetch_listings import get

D = pathlib.Path(__file__).resolve().parent.parent / "data"
LOG = open(D / "agencies.log", "w", buffering=1)
CACHE = D / "cache" / "agencies"
CACHE.mkdir(parents=True, exist_ok=True)


def log(*a):
    print(*a, file=LOG, flush=True); print(*a, flush=True)


BRANDS = ["ray white", "barry plant", "harcourts", "lj hooker", "jellis craig", "nelson alexander", "biggin scott",
          "belle property", "mcgrath", "first national", "century 21", "raine horne", "prd", "professionals",
          "opencorp", "rentbetter", "woodards", "buxton", "ypa", "stockdale leggo", "fletchers", "hocking stuart",
          "marshall white", "eview", "area specialist", "hodges", "kay burton", "wiseberry", "remax", "re max",
          "one agency", "obrien real estate", "o brien real estate", "noel jones", "philip webb", "bombay real estate",
          "ace real estate", "real estate plus", "reliance real estate", "red ink homes", "hayeswinckle",
          "brad teal", "frank dowling", "barry plant", "darren jones", "morrison kleeman", "ray white"]
GENERIC = r"\b(pty|ltd|limited|real estate|realestate|property management|property managers|property manager|" \
          r"rentals|rental|leasing|group|estate agents|agents|agency|realty|the|vic|victoria|melbourne|" \
          r"residential|management|properties|property)\b"


def norm(s):
    s = H.unescape(s or "").lower().replace("&", " ").replace("@", " ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def core(s):
    return re.sub(r"\s+", " ", re.sub(GENERIC, " ", norm(s))).strip()


def brand_of(name):
    n = norm(name)
    for b in sorted(set(BRANDS), key=len, reverse=True):
        if n.startswith(b + " ") or n == b:
            return b
    return None


def cached_get(url, key):
    f = CACHE / (re.sub(r"[^a-z0-9]+", "_", key.lower())[:120] + ".html")
    if f.exists():
        return f.read_text()
    for attempt in range(5):
        try:
            h = get(url)
            break
        except Exception as e:
            if "429" in str(e) and attempt < 4:
                log(f"  site asked us to slow down, waiting {60 * (attempt + 1)} s")
                time.sleep(60 * (attempt + 1))
            else:
                raise
    f.write_text(h)
    time.sleep(5)
    return h


# ---------- 1. ProductReview ----------
FULL_RE = re.compile(r'"fullName":"([^"]+)".{0,600}?"searchableText":"([^"]*)".{0,600}?'
                     r'"statistics":\{"ratingDistribution":\[([\d,]*)\],"numberOfReviews":(\d+),"rating":([\d.]+|null)', re.S)


def pr_search(query):
    h = cached_get("https://www.productreview.com.au/search?q=" + urllib.parse.quote(query), "pr_" + query)
    hits = []
    for m in FULL_RE.finditer(h):
        full, text, dist, n, r = m.groups()
        slugs = re.findall(r'"slug":"([a-z0-9-]+)"', h[max(0, m.start() - 2500):m.start()])
        slug = slugs[-1] if slugs else ""
        if not re.search(r"real estate|property|agent|rental|leasing", text + " " + full, re.I):
            continue
        hits.append({"slug": slug, "name": H.unescape(full), "reviews": int(n),
                     "rating": float(r) if r != "null" else None,
                     "dist": [int(x) for x in dist.split(",") if x]})
    return hits


def reviews_for(name):
    """Franchise offices use their brand's page (offices rarely have their own); others are searched by name."""
    c = core(name)
    out = None
    b = brand_of(name)
    if not b:
        for h in pr_search(name):
            if core(h["name"]) == c and c:
                out = dict(h, level="office"); break
    if not out and b:
        for h in pr_search(b):
            if core(h["name"]) == core(b) or norm(h["name"]) == b:
                out = dict(h, level="brand"); break
    return out


# ---------- 2. Consumer Affairs Victoria ----------
TITLE_RE = re.compile(r"estate|agen|rent|bond|landlord|vcat|trust account|property|tenan", re.I)


def cav_articles(max_pages=45):
    arts, seen = [], set()
    for pg in range(1, max_pages + 1):
        h = cached_get(f"https://www.consumer.vic.gov.au/latest-news?pg={pg}", f"cav_list_{pg}")
        links = re.findall(r'href="(/latest-news/[a-z0-9-]+)"[^>]*>(.*?)</a>', h, re.S)
        new = [(u, re.sub(r"<[^>]+>", "", t).strip()) for u, t in links if u not in seen and not u.endswith(("/events", "/email-updates"))]
        if not new:
            break
        for u, t in new:
            seen.add(u)
            if TITLE_RE.search(u.replace("-", " ") + " " + t):
                arts.append(u)
        log(f"CAV news page {pg}: {len(arts)} relevant stories so far")
    out = []
    for i, u in enumerate(arts):
        h = cached_get("https://www.consumer.vic.gov.au" + u, "cav_" + u.split("/")[-1])
        title = re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S)
        date = re.search(r"(\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December) 20\d\d)", h)
        body = h[h.find("<main"):] if "<main" in h else h
        text = H.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S)))
        out.append({"url": "https://www.consumer.vic.gov.au" + u,
                    "title": H.unescape(re.sub(r"<[^>]+>", "", title.group(1))).strip() if title else u,
                    "date": date.group(1) if date else None, "text": " " + norm(text) + " "})
        if i % 10 == 0:
            log(f"CAV stories read: {i + 1}/{len(arts)}")
    return out


def cav_matches(name, arts):
    """Match the agency's distinctive name (not just a franchise brand) in the story text."""
    n = norm(name)
    c = core(name)
    b = brand_of(name)
    # the full trading name, or its distinctive part when that is at least two words;
    # single words ("Williams", "Leader") match too many unrelated stories
    needles = {n} if len(n.split()) >= 2 else set()
    if len(c.split()) >= 2:
        needles.add(c)
    needles = {x for x in needles if x != b and len(x) >= 8}
    hits = []
    for a in arts:
        for x in needles:
            i = a["text"].find(f" {x} ")
            if i >= 0:
                hits.append({**{k: a[k] for k in ("url", "title", "date")}, "context": a["text"][max(0, i - 160):i + 200].strip()})
                break
    return hits


def main():
    listings = [l for f in ("listings_enriched.json", "listings_enriched_solo.json") if (D / f).exists()
                for l in json.load(open(D / f))]
    names = sorted({l["agency"].strip() for l in listings if l.get("agency")})
    log(f"{len(names)} agencies")
    arts = cav_articles()
    log(f"CAV: {len(arts)} enforcement-related stories read")
    out = {}
    for i, n in enumerate(names):
        try:
            rv = reviews_for(n)
        except Exception as e:
            log("ERR", n, e); rv = None
        out[n] = {"reviews": rv, "cav": cav_matches(n, arts),
                  "listings": sum(1 for l in listings if (l.get("agency") or "").strip() == n)}
        if i % 10 == 0:
            log(f"Agency reviews: {i + 1}/{len(names)}")
    json.dump(out, open(D / "agencies.json", "w"), indent=1)
    rated = sum(1 for v in out.values() if v["reviews"])
    log(f"saved {len(out)} agencies: {rated} with reviews, {sum(1 for v in out.values() if v['cav'])} with CAV records")


if __name__ == "__main__":
    main()
