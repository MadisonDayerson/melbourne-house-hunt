"""Build the shareable page: app/northside-house-hunt.html from app/template.html + data/*.json."""
import json, math, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / "data"
listings = json.load(open(D / "listings_enriched.json"))
base = json.load(open(D / "basemap.json"))

# Map projection (equirectangular, scaled for Melbourne's latitude), padded around the listings
lats = [l["lat"] for l in listings]; lngs = [l["lng"] for l in listings]
pad = 0.012
S, N = min(lats) - pad, max(lats) + pad
W, E = min(lngs) - pad, max(lngs) + pad
k = math.cos(math.radians((S + N) / 2))
WIDTH = 1000
HEIGHT = round(WIDTH * (N - S) / ((E - W) * k))
proj = {"S": S, "N": N, "W": W, "E": E, "w": WIDTH, "h": HEIGHT}


def px(lat, lng):
    return (round((lng - W) / (E - W) * WIDTH, 1), round((N - lat) / (N - S) * HEIGHT, 1))


def path(lines):
    out = []
    for line in lines:
        pts = [px(a, b) for a, b in line]
        if all(x < -50 or x > WIDTH + 50 or y < -50 or y > HEIGHT + 50 for x, y in pts):
            continue
        out.append("M" + "L".join(f"{x:g},{y:g}" for x, y in pts))
    return "".join(out)


svg_paths = {k: path(v) for k, v in base["lines"].items()}
stations = [{"x": px(a, b)[0], "y": px(a, b)[1], "n": n} for a, b, n in base["stations"]
            if 0 <= px(a, b)[0] <= WIDTH and 0 <= px(a, b)[1] <= HEIGHT]

KEEP = ["region", "lga", "id", "url", "type", "street", "suburb", "postcode", "rent", "beds", "baths", "cars", "pets",
        "lat", "lng", "available", "listed", "walk_score", "transit_score", "agency", "cbd_km", "near",
        "counts", "met", "twenty", "transit", "roads", "quiet", "noise_flags", "air", "air_flags",
        "safety", "crime"]
data = [{k: l.get(k) for k in KEEP} for l in listings]
for d in data:
    d["id"] = str(d["id"])
    d["near"] = {k: [v["m"], v["name"]] for k, v in d["near"].items()}

# ---- agency renter-friendliness + build age ----
CAV_REVIEW = json.load(open(D / "cav_review.json")) if (D / "cav_review.json").exists() else {}


# ProductReview pages whose reviewers are almost all on the other side of the deal; shown, not scored
NOT_RENTER_REVIEWS = {
    "For Sale By Owner": "These reviews are from people selling their own homes on this platform, not renters.",
    "Ironfish Real Estate": "These reviews are mostly from property investors, not renters.",
    "Cubbi": "These reviews are mostly from landlords using this management service, not renters.",
}


def cav_kind(name):
    return (CAV_REVIEW.get(name) or {}).get("kind", "unreviewed")


def agency_score(a, name):
    rv = None if name in NOT_RENTER_REVIEWS else a.get("reviews")
    cav = a.get("cav") if cav_kind(name) in ("agency", "alleged") else []
    if not (rv and rv.get("rating")) and not cav:
        return None
    if rv and rv.get("rating"):
        # Bayesian average: few reviews pull towards a typical 2.5 stars, so 1 glowing review can't top the table
        adj = (rv["reviews"] * rv["rating"] + 10 * 2.5) / (rv["reviews"] + 10)
        base = (adj - 1) / 4 * 100
    else:
        base = 50
    if cav:  # one penalty per agency: several stories are usually about the same case
        base -= 30 if cav_kind(name) == "agency" else 15
    return max(0, min(100, round(base)))


agencies_path, age_path = D / "agencies.json", D / "build_age.json"
agencies = json.load(open(agencies_path)) if agencies_path.exists() else {}
ages = json.load(open(age_path)) if age_path.exists() else {}
ag_out = {}
for name, a in agencies.items():
    rv = a.get("reviews")
    rec = CAV_REVIEW.get(name) or {}
    ag_out[name] = {"score": agency_score(a, name), "cavKind": rec.get("kind"), "cavSummary": rec.get("summary"), "rvNote": NOT_RENTER_REVIEWS.get(name),
                    "rv": [rv["rating"], rv["reviews"], rv["level"], rv["name"], rv["slug"], rv["dist"]] if rv else None,
                    "cav": [{k: c[k] for k in ("url", "title", "date")} for c in (a.get("cav") or [])]}
for d in data:
    d["agency"] = (d.get("agency") or "").strip()
    g = ages.get(d["id"])
    if g:
        d["age"] = [g["era"], g["bucket"], g["confidence"], g["evidence"], g["renovated"], g["comfort"]]

payload = {
    "agencies": ag_out,
    "asOf": datetime.date.today().isoformat(),
    "listings": data, "proj": proj, "stations": stations,
    "suburbs": [[x["suburb"], x["region"]] for x in json.load(open(D / "suburbs.json"))],
}
template = (ROOT / "app" / "template.html").read_text()


def render(payload):
    html = template.replace("__DATA__", json.dumps(payload, separators=(",", ":")).replace("</", "<\\/"))
    for k, v in svg_paths.items():
        html = html.replace(f"__PATH_{k.upper()}__", v)
    return html.replace("__MAP_W__", str(WIDTH)).replace("__MAP_H__", str(HEIGHT))


# 1. claude.ai artifact (the artifact viewer adds the document wrapper and provides shared storage)
out = ROOT / "app" / "northside-house-hunt.html"  # file name kept so republishing updates the same artifact
out.write_text(render(payload))
print("wrote", out, f"{out.stat().st_size/1024:.0f} KB", len(data), "listings")

# 2. GitHub Pages: a complete document, with the Supabase project from site_config.json for shared votes
cfg_path = ROOT / "site_config.json"
cfg = json.load(open(cfg_path)) if cfg_path.exists() else {}
sb = cfg.get("supabase") or {}
gh_payload = dict(payload, supabase={"url": sb["url"], "key": sb["anon_key"]} if sb.get("url") and sb.get("anon_key") else None)
body = render(gh_payload)
title = body[body.index("<title>"):body.index("</title>") + 8]
body = body.replace(title, "", 1)
doc = ("<!doctype html>\n<html lang=\"en-AU\">\n<head>\n<meta charset=\"utf-8\">\n"
       "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">\n"
       f"{title}\n<meta name=\"description\" content=\"4+ bedroom rentals across Melbourne, scored for walkability, transport, noise, air, safety and agency track record.\">\n"
       "<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}"
       "body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n</head>\n<body>\n"
       + body + "\n</body>\n</html>\n")
docs = ROOT / "docs"
docs.mkdir(exist_ok=True)
(docs / "index.html").write_text(doc)
(docs / ".nojekyll").write_text("")
print("wrote", docs / "index.html", "shared votes:", "Supabase" if gh_payload["supabase"] else "off (no site_config.json)")
