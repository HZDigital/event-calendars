# Calendar check (instructions for Claude, run on demand)

This check runs monthly (1st, 08:00) as a local scheduled task in the Claude Work app, only while the Mac
is on and the app is open. The owner can also start it any time by saying "Führe ROUTINE.md aus".

You keep two event calendars current. The events live in `events/pe.yaml` and
`events/restructuring.yaml`; `calendars.yaml` lists them. A GitHub Action turns them into
ICS feeds once a change reaches `main`. There are no branches and no pull requests: you change the
YAML, check it locally and commit straight to `main`. Use only the GitHub account `carl-hz`.

## Each run

1. Start on an up-to-date `main` (`git pull --ff-only`).
2. For every event that has `end` today or later, or `status: tbd`, open its `source`
   (or `link`) and check date, location and status against the organiser's page.
3. For every `series` whose most recent entry ends within the next 6 months or lies in the
   past, look for the next edition. If the organiser has announced it, add it as a new entry.
4. Set `checked: <today>` on every entry you looked at, whether or not it changed.
5. Run `python scripts/build_ics.py --check`. Fix every error it reports.
6. If `--check` is green, commit directly to `main` with the message `Calendar check YYYY-MM-DD`
   (ending `(no changes)` if only `checked` changed) and `git push`.
7. If `--check` is red, do not commit or push. Tell the owner what is wrong (entry, field, error).
   Fix an error only when its cause is obvious (typo, missing field); never push a red state.

## Keep the run small

The run is paid from a limited budget. Work through the list once, without extra rounds.

- Group entries by organiser website and open each site once (TMA, IfUS, PE Insights, BVK,
  R3 and INSOL each cover several entries).
- Skip entries with `status: confirmed` whose `checked` date is less than 60 days old and whose
  start date is more than 3 months away.
- Use at most two pages per entry: the `source`/`link` page, then one web search if that fails.
  If both fail, leave the entry unchanged apart from `checked`.
- Do not research new event series beyond what you happen to see on pages you already opened.

## Rules for entries

- `confirmed` only when an official source (organiser site, ticketing page, official
  announcement) states the exact date. Put that URL in `source`.
- If only the month is known, use `tbd` with a best-guess `start`/`end` in that month and say
  so in `notes`. If nothing is known, use `tbd` without dates (watchlist; not in the feed).
- Never delete an entry. Use `cancelled` (shown struck in calendars) or `discontinued`
  (series ended; hidden from feeds).
- Keep `series` unchanged; it builds the event UID, so changing it creates a duplicate in
  people's calendars. Events that run several times a year need a distinct `edition`
  (e.g. `2027-03`).
- `notes` is internal and never published. Mark guesses there with `Inference:`.
- Titles follow the existing style: name plus year, e.g. `IPEM Cannes 2027`.
- Read-only on the web: no registrations, forms or downloads.

## Summary for the owner

After the push (or after a red check), report in chat. Start with one line: how many entries were added, changed, cancelled, unchanged. Then a
table of every change: event, field, old → new, source URL. Then, separately, up to five
new events you came across that fit a calendar but are not in it yet (name, date, link).
Do not add those to the YAML; the owner decides.

## Entry format

```yaml
- title: IPEM Cannes 2027
  series: ipem-cannes            # stable key, never change
  edition: 2027                  # optional; defaults to the start year
  start: 2027-02-02
  end: 2027-02-04                # inclusive; same as start for one-day events
  status: confirmed              # confirmed | tbd | cancelled | discontinued
  organiser: IPEM
  location: Cannes (Palais des Festivals)
  country: FR                    # 2-letter code, shown as [FR] in the title
  category: Conference
  cost: ~€2,400
  link: https://www.ipem-market.com/
  source: https://www.ipem-market.com/   # page that states the date
  checked: 2026-10-15
  notes: internal only
```
