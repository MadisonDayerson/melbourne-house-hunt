# Melbourne House Hunt

4+ bedroom rentals across Melbourne, scored for walkability, public transport, noise, air quality, safety and agency track record, with a shared shortlist for housemates.

- Website (GitHub Pages): `docs/index.html`
- claude.ai version: https://claude.ai/artifact/W8Nyo9htpZm7Un8Fp81kWb

## Hosting on GitHub Pages

1. **Shared votes (Supabase, free):** create a project at supabase.com, open SQL Editor, paste `supabase/setup.sql` and press Run. Copy `site_config.example.json` to `site_config.json` and fill in the Project URL and the `anon` public key (Project Settings > API). The anon key is meant to be public; the database functions only answer to the right house code.
2. `python3 scripts/build.py` writes `docs/index.html` with that config.
3. Push to GitHub, then in the repository's Settings > Pages choose "Deploy from a branch", branch `main`, folder `/docs`.
4. Housemates open the site, enter their name and the house code you choose (6+ characters, keep it among yourselves).

## Refresh the listings

```bash
cd ~/Downloads/Personal/Rentals
python3 scripts/fetch_listings.py   # 4+ bed rentals in 539 metro suburbs from rent.com.au (~35 min, resumable)
./data/fetch_osm.sh                 # OpenStreetMap shops, services, stops, roads, rail (16 tiles, ~30 min)
python3 scripts/enrich.py           # location scores
python3 scripts/fetch_details.py    # listing descriptions (~1 hr; run a 2nd copy with --reverse to halve it)
python3 scripts/build_age.py        # build age + comfort features from descriptions
python3 scripts/agencies.py         # agency reviews (ProductReview) + Consumer Affairs Victoria records (~30 min)
python3 scripts/build.py            # writes app/northside-house-hunt.html
```

Then commit and push `docs/index.html` to update the website (and/or republish `app/northside-house-hunt.html` to the artifact). Votes, notes and added listings live in the artifact's database, so they survive republishing.

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
