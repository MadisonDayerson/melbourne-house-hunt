# Melbourne House Hunt

Rentals across Melbourne for any household, scored for walkability, public transport, noise, air quality, safety and agency track record. Each **hunt** (a tab on the site) has its own people, rent split, budget, bedrooms, votes and notes, and can be shared with an invite link.

- Website: https://madisondayerson.github.io/melbourne-house-hunt/ (built into `docs/`)
- The earlier claude.ai copy (https://claude.ai/artifact/W8Nyo9htpZm7Un8Fp81kWb) was retired on 2026-10-15 and no longer updates.

## Hosting on GitHub Pages

1. **Shared hunts (Supabase, free):** create a project at supabase.com, open SQL Editor, paste `supabase/setup.sql` and press Run, then do the same with `supabase/002_hunts.sql`. Copy `site_config.example.json` to `site_config.json` and fill in the Project URL and the `anon` public key (Project Settings > API). The anon key is meant to be public; the database functions only answer to the right house code.
2. `python3 scripts/build.py` writes `docs/index.html` with that config.
3. Push to GitHub, then in the repository's Settings > Pages choose "Deploy from a branch", branch `main`, folder `/docs`.
4. On the site, **+ New hunt** creates a hunt; **Invite people** gives a link to send.

## Refresh the listings

```bash
cd ~/Downloads/Personal/Rentals
./scripts/daily_update.sh           # everything below in order (this is what runs on GitHub every morning)
python3 scripts/fetch_listings.py --pool large|three|small   # rent.com.au: 4+ bed / 3 bed / studio-2 bed
./data/fetch_osm.sh                 # OpenStreetMap shops, services, stops, roads, rail (16 tiles, ~30 min)
python3 scripts/enrich.py --pool large|three|small           # location scores
python3 scripts/fetch_details.py    # listing descriptions (~1 hr; run a 2nd copy with --reverse to halve it)
python3 scripts/build_age.py        # build age, comfort features, rooming house / student flags
python3 scripts/agencies.py         # agency reviews (ProductReview) + Consumer Affairs Victoria records (~30 min)
python3 scripts/build.py            # writes docs/index.html, docs/data/<pool>.json, docs/geo.json
```

Then commit and push `docs/` to update the website. Hunts, votes, notes and added listings live in Supabase, so they survive rebuilds.

`./scripts/progress.sh` shows live progress of the two downloads.

The suburb list and crime counts come from `scripts/crime.py` (needs `pip install openpyxl`) and populations from `scripts/population.py`; rerun those only when new crime data is released. To re-download map data, delete `data/osm_tiles/` first. Crime data is `data/csa_lga_offences_jun2026.xlsx` from the Crime Statistics Agency (next release: year ending September 2026, due December).

## Files

- `scripts/crime.py`: metro suburb list (31 councils, 6 regions) and suburb crime counts
- `scripts/population.py`: 2021 Census population per suburb
- `scripts/fetch_listings.py`: collects listings
- `scripts/fetch_details.py`, `scripts/build_age.py`: when each house was built, read from its description
- `scripts/agencies.py`: agency reviews and regulator records; `data/cav_review.json` holds the manual check of each CAV match (add new matches there after a rerun)
- `scripts/enrich.py`: walkability, transport, noise, air and safety scoring (the method is in the page's "How scores work" tab)
- `scripts/build.py` + `app/template.html`: builds the page
- `data/`: raw and processed data
