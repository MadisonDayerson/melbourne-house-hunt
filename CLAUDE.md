# Melbourne House Hunt

Rental search site for a group of 5 housemates (one couple), live at
https://madisondayerson.github.io/melbourne-house-hunt/ (GitHub Pages, served from `docs/`).

## Publishing changes (standing instruction from the owner)

Any change requested in this project should end up live on the website without asking:

1. Edit the source (`app/template.html`, `scripts/*.py`, `data/*.json`), never `docs/index.html` directly.
2. Rebuild: `python3 scripts/build.py` (writes `docs/index.html` and the claude.ai artifact copy).
3. Check the page script still parses before committing.
4. Commit with a short message describing the change, then `git push`. GitHub Pages redeploys in about a minute.
5. Tell the owner what changed and that the site is updated. If the push fails with an authentication error,
   the saved GitHub token has expired: walk the owner through making a new fine-grained token and pushing
   once from a Terminal tab (they want step-by-step guidance for account tasks).

Never commit `site_config.json` secrets other than the Supabase anon key (the service_role key must never
be in this repo), and never commit the large raw downloads listed in `.gitignore`.

## Data refresh

See README.md. Shared votes on the website live in Supabase (`supabase/setup.sql`), not in this repo,
so rebuilding and pushing never touches them.
