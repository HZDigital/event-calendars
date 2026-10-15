# Event Calendars

Two subscribable calendars (PE & Deal Sourcing, Restructuring) for internal use.
The landing page on GitHub Pages has the subscribe links.

```
events/*.yaml  →  GitHub Action (scripts/build_ics.py)  →  GitHub Pages  →  webcal:// subscribers
      ↑
on request ("Führe ROUTINE.md aus") Claude opens a pull request and merges it once the check is green
```

## Change an event

Edit `events/pe.yaml` or `events/restructuring.yaml` (format: see `ROUTINE.md`) and push to
`main`. The feed updates within about two minutes; calendar apps pick it up on their next
refresh (usually within a few hours, Outlook up to 24 h).

Check locally before pushing:

```bash
pip install -r requirements.txt
python scripts/build_ics.py --check          # validate only
python scripts/build_ics.py --out _site      # build feeds + index.html
```

## Add an event a colleague sent

Colleagues send event links to the calendar owner by mail or Teams; there is no form and no contact
on the page. The owner hands the link to Claude ("trag das in den Kalender ein"). Claude then:

1. Picks the calendar (PE or Restructuring) and opens the event page once.
2. Adds one entry in the format from `ROUTINE.md`, with a new `series` key; `confirmed` only if the
   page states the date, otherwise `tbd`.
3. Runs `python scripts/build_ics.py --check`, opens a PR and merges it once the check is green,
   as in `ROUTINE.md` step 7.

## Behaviour

- Feeds have no year in their name and keep running; events drop out 30 days after they end
  (`keep_past_days` in `calendars.yaml`). The Action rebuilds weekly for that.
- UIDs come from `series` + `edition`, so a moved date updates the existing calendar entry.
- `tbd` events show as "(date tbc)"; `cancelled` ones as "CANCELLED: …"; `discontinued` and
  undated entries stay out of the feeds.

## Calendar check on demand

The check of all entries is not scheduled. When the owner says "Führe ROUTINE.md aus" in the Claude app,
Claude follows `ROUTINE.md`: it branches, checks the entries against the organisers' pages, opens a pull
request and merges it once the `build` check is green. Only the weekly rebuild (so past events roll off)
runs automatically.

## Setup

Done once by `setup_hz_repo.sh` (HZ SharePoint, `02_Event_Calendar_Sync`): repo, Pages source **GitHub Actions**,
first build. The Claude GitHub app must have access to this repository so Claude can open and merge
pull requests when working in this repository (an org owner at H&Z Digital approves this). No secrets needed.

## Later

- Newsletter "Upcoming events" via Outlook (idea from 10/2026; not built).
