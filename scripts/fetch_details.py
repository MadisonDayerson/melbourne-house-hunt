"""Download each listing's detail page from rent.com.au and keep the description and feature tags.

Used to estimate when the house was built (see build_age.py). Cached per listing in
data/cache/details/<id>.json, so reruns only fetch new listings. One request every 2 seconds.
"""
import json, re, time, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fetch_listings import get

D = pathlib.Path(__file__).resolve().parent.parent / "data"
CACHE = D / "cache" / "details"
CACHE.mkdir(parents=True, exist_ok=True)


def parse(html):
    c = html.encode().decode("unicode_escape", "ignore")
    out = {}
    # the long description is a Next.js text chunk referenced as "description":"$<ref>"
    m = re.search(r'"description":"\$(\w+)","byline":"([^"]*)"', c)
    if m:
        out["byline"] = m.group(2)
        t = re.search(r"\b" + re.escape(m.group(1)) + r":T[0-9a-f]+,", c)
        if t:
            body = c[t.end():t.end() + 8000]
            if body.startswith('"])'):  # text continues in the next payload chunk
                k = body.find('push([1,"')
                body = body[k + 9:] if k >= 0 else ""
            out["description"] = body.split('"])</script>')[0].strip()[:5000]
    else:  # short descriptions are stored inline
        m = re.search(r'"description":"(.{20,6000}?)","byline":"([^"]*)"', c, re.S)
        if m:
            out["description"], out["byline"] = m.group(1).replace("\\n", "\n").strip(), m.group(2)
    f = re.search(r'"features":(\{"(?:garage|heating|flooring|airconditioning|outdoor|indoor|security|appliances|laundry)[^}]*\})', c)
    if f:
        try:
            out["features"] = json.loads(f.group(1))
        except ValueError:
            pass
    for k in ("ensuites", "furnished", "bond"):
        m = re.search(r'"' + k + r'":(true|false|null|\d+)', c)
        if m:
            out[k] = json.loads(m.group(1))
    return out


def main():
    listings = [l for f in ("listings_enriched.json", "listings_enriched_solo.json") if (D / f).exists()
                for l in json.load(open(D / f))]
    todo = [l for l in listings if not (CACHE / f"{l['id']}.json").exists()]
    if "--reverse" in sys.argv:  # a second worker can run from the other end
        todo.reverse()
    print(len(listings), "listings,", len(todo), "to fetch", flush=True)
    for i, l in enumerate(todo):
        if (CACHE / f"{l['id']}.json").exists():
            break  # met the other worker
        try:
            rec = parse(get(l["url"]))
        except Exception as e:
            rec = {"error": str(e)}
        (CACHE / f"{l['id']}.json").write_text(json.dumps(rec))
        print(f"[{i + 1}/{len(todo)}] {l['id']} {'ok' if rec.get('description') else rec.get('error', 'no description')}", flush=True)
        time.sleep(2)


if __name__ == "__main__":
    main()
