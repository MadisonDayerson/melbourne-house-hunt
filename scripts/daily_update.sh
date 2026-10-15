#!/bin/bash
# Daily refresh: new listings in, leased ones out, scores for anything new, then rebuild the site.
# Runs on GitHub Actions every morning (.github/workflows/daily-update.yml); also works on a Mac.
set -euo pipefail
cd "$(dirname "$0")/.."

for pool in large three small; do
  echo "== Listings: $pool";              python3 scripts/fetch_listings.py --pool $pool
done
echo "== Location scores"
for pool in large three small; do python3 scripts/enrich.py --pool $pool; done
echo "== Details for new listings";        python3 scripts/fetch_details.py
echo "== Build age";                       python3 scripts/build_age.py
echo "== Agencies (new ones only)";        python3 scripts/agencies.py --incremental > /dev/null
tail -1 data/agencies.log
echo "== Build site";                      python3 scripts/build.py
