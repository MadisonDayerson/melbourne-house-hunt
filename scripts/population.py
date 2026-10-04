"""2021 Census population for every suburb in data/suburbs.json, read from Wikipedia suburb infoboxes.

Output: data/suburb_population.json {suburb: population or null}
"""
import json, re, time, urllib.request, urllib.parse, pathlib

D = pathlib.Path(__file__).resolve().parent.parent / "data"
API = "https://en.wikipedia.org/w/api.php?action=query&prop=revisions&rvprop=content&rvslots=main&rvsection=0&format=json&formatversion=2&redirects=1"
UA = {"User-Agent": "melb-rental-research/1.0 (personal project)"}

out = json.load(open(D / "suburb_population.json")) if (D / "suburb_population.json").exists() else {}
names = [s["suburb"] for s in json.load(open(D / "suburbs.json"))]
todo = [n for n in names if not out.get(n)]


def parse(text):
    m = (re.search(r"\|\s*pop\s*=\s*([\d,]{2,})", text)
         or re.search(r"population of (?:\{\{formatnum:)?([\d,]{2,})\}?\}?(?: people)? at the (?:\[\[|\{\{CensusAU\|)2021", text)
         or re.search(r"population of \{\{formatnum:([\d,]{2,})\}\}", text)
         or re.search(r"2021 (?:Australian )?census[^.]{0,80}?population of ([\d,]{2,})", text))
    return int(m.group(1).replace(",", "")) if m else None


for attempt in range(2):
    for i in range(0, len(todo), 40):
        batch = todo[i:i + 40]
        titles = {(n + ", Victoria" if attempt == 0 else n + ", Melbourne"): n for n in batch}
        data = urllib.parse.urlencode({"titles": "|".join(titles)}).encode()
        for tries in range(4):
            try:
                d = json.load(urllib.request.urlopen(urllib.request.Request(API, data=data, headers=UA), timeout=60))
                break
            except Exception as e:
                print("retry", e); time.sleep(20)
        # map redirected/normalised titles back to the suburb names we asked for
        back = dict(titles)
        for k in ("normalized", "redirects"):
            for r in d["query"].get(k, []):
                if r["from"] in back:
                    back[r["to"]] = back[r["from"]]
        for pg in d["query"]["pages"]:
            name = back.get(pg["title"])
            text = (pg.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("content", "")
            if name and text:
                out[name] = parse(text) or out.get(name)
        time.sleep(3)
    todo = [n for n in names if not out.get(n)]

json.dump(out, open(D / "suburb_population.json", "w"), indent=1)
print("have", sum(1 for n in names if out.get(n)), "of", len(names), "missing:", todo)
