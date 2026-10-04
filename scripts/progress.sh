#!/bin/zsh
# Live progress for the data refresh. Run it, watch it, press Ctrl-C to close.
DATA="${0:A:h}/../data"
bar() { # $1 done, $2 total
  local w=40 f=$(( $1 * 40 / $2 )); printf '['; printf '%*s' $f '' | tr ' ' '#'; printf '%*s' $((w - f)) '' | tr ' ' '.'; printf '] %d/%d (%d%%)' $1 $2 $(( $1 * 100 / $2 ))
}
while true; do
  clear
  echo "Melbourne House Hunt — data refresh      $(date '+%H:%M:%S')"
  echo
  LOG="$DATA/fetch_listings.log"
  if grep -q '^saved' "$LOG" 2>/dev/null; then
    echo "1. Listings (rent.com.au)          DONE  $(grep '^saved' "$LOG" | awk '{print $2}') listings with 4+ bedrooms"
  else
    n=$(grep -c '^\[' "$LOG" 2>/dev/null)
    printf '1. Listings (rent.com.au)          '; bar ${n:-0} 539; echo
    echo "   latest: $(grep '^\[' "$LOG" | tail -1)"
  fi

  t=$(ls "$DATA"/osm_tiles/*.json 2>/dev/null | wc -l | tr -d ' ')
  if [[ $t -ge 32 && -s "$DATA/osm_roads.json" ]]; then
    echo "2. Map data (OpenStreetMap)        DONE"
  else
    printf '2. Map data (OpenStreetMap)        '; bar $t 32; echo
    tmp=$(ls "$DATA"/osm_tiles/*.tmp 2>/dev/null | head -1)
    [[ -n $tmp ]] && echo "   working on: ${tmp:t:r:r}  (server busy = it waits and retries)"
  fi

  if [[ -f "$DATA/fetch_details.log" ]]; then
    total=$(python3 -c "import json;print(len(json.load(open('$DATA/listings_enriched.json'))))" 2>/dev/null)
    n=$(ls "$DATA"/cache/details 2>/dev/null | wc -l | tr -d ' ')
    if [[ $n -ge $total ]]; then echo "3. Listing details (build age)     DONE  $n pages";
    else
      printf '3. Listing details (build age)     '; bar $n $total; echo
      w=$(pgrep -f fetch_details.py | wc -l | tr -d ' ')
      echo "   $w worker(s) running · about $(( (total - n) * 35 / 10 / 60 / (w > 0 ? w : 1) )) min left"
    fi
  fi

  ALOG="$DATA/agencies.log"
  if [[ -f $ALOG ]]; then
    if grep -q '^saved' "$ALOG"; then echo "4. Agency reviews + CAV records    DONE  $(grep '^saved' "$ALOG" | cut -d' ' -f2-)";
    else echo "4. Agency reviews + CAV records    $(tail -1 "$ALOG")"; fi
  fi
  echo
  echo "Then: score listings + rebuild page (Claude runs this)"
  echo
  echo "Refreshes every 5 seconds. Ctrl-C to close."
  sleep 5
done
