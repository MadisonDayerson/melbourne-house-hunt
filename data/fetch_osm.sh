#!/bin/zsh
# Downloads OpenStreetMap amenity, road and rail data for metropolitan Melbourne, in tiles
# so each Overpass request stays small. Output: osm_amenities.json, osm_roads.json
cd "${0:A:h}"
mkdir -p osm_tiles
LATS=(-38.52 -38.25 -37.98 -37.71 -37.40)
LNGS=(144.40 144.75 145.10 145.45 145.85)

fetch() { # $1 query, $2 outfile
  [[ -s $2 ]] && head -c 20 $2 | grep -q '{' && return 0
  for i in 1 2 3 4 5 6; do
    for u in https://overpass-api.de/api/interpreter https://overpass.kumi.systems/api/interpreter; do
      curl -s -m 300 -A "melb-rentals/1.0 (personal research)" -H "Accept: application/json" --data-urlencode "data=$1" $u -o $2.tmp
      if head -c 20 $2.tmp | grep -q '{' && grep -q '"elements"' $2.tmp && ! grep -q '"remark": "runtime error' $2.tmp; then mv $2.tmp $2; echo "ok $2"; return 0; fi
      sleep 15
    done
  done; echo "FAILED $2"; return 1
}

for ((a=1; a<${#LATS}; a++)); do for ((b=1; b<${#LNGS}; b++)); do
  BBOX="${LATS[a]},${LNGS[b]},${LATS[a+1]},${LNGS[b+1]}"
  fetch "[out:json][timeout:240];(
nwr[shop~\"^(supermarket|greengrocer|butcher|bakery)$\"]($BBOX);
nwr[amenity~\"^(pharmacy|doctors|clinic|cafe|restaurant|pub|bar|library|community_centre|cinema|marketplace)$\"]($BBOX);
nwr[leisure~\"^(park|playground|fitness_centre|sports_centre|swimming_pool|dog_park)$\"]($BBOX);
node[railway~\"^(station|tram_stop)$\"]($BBOX);
node[highway=bus_stop]($BBOX);
);out center tags;" osm_tiles/amen_${a}_${b}.json
  fetch "[out:json][timeout:240];(way[highway~\"^(motorway|trunk|primary|motorway_link)$\"]($BBOX);way[railway=rail]($BBOX););out geom tags;" osm_tiles/roads_${a}_${b}.json
done; done

python3 - <<'EOF'
import json, glob
for kind, out in (("amen", "osm_amenities.json"), ("roads", "osm_roads.json")):
    seen, els = set(), []
    for f in sorted(glob.glob(f"osm_tiles/{kind}_*.json")):
        for e in json.load(open(f))["elements"]:
            k = (e["type"], e["id"])
            if k not in seen:
                seen.add(k); els.append(e)
    json.dump({"elements": els}, open(out, "w"))
    print(out, len(els))
EOF
