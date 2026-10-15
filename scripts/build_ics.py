"""
build_ics.py — YAML event lists → subscribable ICS feeds + landing page.

Reads calendars.yaml, validates every events/*.yaml file and writes one ICS file per
calendar plus index.html into the output directory (served by GitHub Pages).

Usage:
    # CLI (GitHub Action / terminal); exits 1 on validation errors
    python scripts/build_ics.py --config calendars.yaml --out _site
    python scripts/build_ics.py --check            # validate only

    # Python import
    from build_ics import build
    result = build("calendars.yaml", "_site")
"""

import argparse
import html
import json
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

NAMESPACE = uuid.UUID("6f1d2c4e-8a7b-4e3f-9c51-2b7d0e9a4f13")
STATUSES = {"confirmed", "tbd", "cancelled", "discontinued"}
REQUIRED = {"title", "series", "status"}
ALLOWED = REQUIRED | {
    "edition", "start", "end", "organiser", "location", "country", "category",
    "cost", "link", "source", "checked", "notes",
}


# ── Validation ───────────────────────────────────────────────────────────────

def _as_date(value, field: str, errors: list, where: str):
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        errors.append(f"{where}: {field} '{value}' is not YYYY-MM-DD")
        return None


def load_events(path: Path, cal_id: str, errors: list) -> list[dict]:
    """Load and validate one events file; problems are appended to errors."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list):
        errors.append(f"{path}: top level must be a list")
        return []

    events, uids = [], {}
    for i, ev in enumerate(raw, 1):
        where = f"{path.name} #{i} ({ev.get('title', '?') if isinstance(ev, dict) else '?'})"
        if not isinstance(ev, dict):
            errors.append(f"{where}: entry must be a mapping")
            continue
        missing = REQUIRED - ev.keys()
        unknown = ev.keys() - ALLOWED
        if missing:
            errors.append(f"{where}: missing {sorted(missing)}")
        if unknown:
            errors.append(f"{where}: unknown keys {sorted(unknown)}")
        if ev.get("status") not in STATUSES:
            errors.append(f"{where}: status must be one of {sorted(STATUSES)}")

        start = _as_date(ev.get("start"), "start", errors, where)
        end = _as_date(ev.get("end"), "end", errors, where) or start
        if start and end and end < start:
            errors.append(f"{where}: end before start")
        if ev.get("status") == "confirmed" and not start:
            errors.append(f"{where}: confirmed events need a start date")
        country = ev.get("country")
        if country and not (len(str(country)) == 2 and str(country).isupper()):
            errors.append(f"{where}: country '{country}' should be a 2-letter code")

        # One UID per series and edition, so a moved date updates the event instead of duplicating it
        edition = ev.get("edition") or (start.year if start else None)
        key = f"{cal_id}|{ev.get('series')}|{edition}"
        if start and key in uids:
            errors.append(f"{where}: same series+edition as #{uids[key]}; set a distinct 'edition'")
        uids.setdefault(key, i)

        events.append({**ev, "start": start, "end": end, "uid": str(uuid.uuid5(NAMESPACE, key))})
    return events


# ── ICS ──────────────────────────────────────────────────────────────────────

def _esc(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Fold content lines at 75 octets (RFC 5545 §3.1) without splitting UTF-8 sequences."""
    data, out, limit = line.encode("utf-8"), [], 75
    while len(data) > limit:
        cut = limit
        while (data[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(data[:cut].decode("utf-8"))
        data, limit = data[cut:], 74
    out.append(data.decode("utf-8"))
    return "\r\n ".join(out)


def _summary(ev: dict, prefix: str) -> str:
    s = ev["title"]
    if prefix == "country" and ev.get("country"):
        s = f"[{ev['country']}] {s}"
    if ev["status"] == "tbd":
        s += " (date tbc)"
    if ev["status"] == "cancelled":
        s = f"CANCELLED: {s}"
    return s


def _description(ev: dict) -> str:
    parts = []
    if ev["status"] == "tbd":
        parts.append("Date not yet confirmed by the organiser.")
    for label, key in (("Organiser", "organiser"), ("Cost", "cost"), ("Link", "link")):
        if ev.get(key):
            parts.append(f"{label}: {ev[key]}")
    return "\n".join(parts)


def to_ics(cal: dict, events: list[dict], stamp: str) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//Event Calendars//{cal['id']}//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_esc(cal['name'])}",
        f"X-WR-CALDESC:{_esc(cal.get('description', ''))}",
        "X-WR-TIMEZONE:Europe/Berlin",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    for ev in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev['uid']}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{ev['start']:%Y%m%d}",
            f"DTEND;VALUE=DATE:{ev['end'] + timedelta(days=1):%Y%m%d}",  # DTEND is exclusive
            f"SUMMARY:{_esc(_summary(ev, cal.get('summary_prefix')))}",
        ]
        if ev.get("location"):
            lines.append(f"LOCATION:{_esc(ev['location'])}")
        if _description(ev):
            lines.append(f"DESCRIPTION:{_esc(_description(ev))}")
        if ev.get("link"):
            lines.append(f"URL:{ev['link']}")
        if ev.get("category"):
            lines.append(f"CATEGORIES:{_esc(ev['category'])}")
        lines.append("STATUS:" + {"cancelled": "CANCELLED", "tbd": "TENTATIVE"}.get(ev["status"], "CONFIRMED"))
        lines += ["TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


# ── Landing page ─────────────────────────────────────────────────────────────

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{--bg:#fafaf8;--fg:#1d1d1f;--muted:#6e6e73;--line:#e3e3e0;--accent:#c2410c;--card:#fff}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151515;--fg:#f2f2f0;--muted:#9a9a9f;--line:#2c2c2c;--accent:#fb923c;--card:#1d1d1d}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Inter","Segoe UI",sans-serif}}
main{{max-width:760px;margin:0 auto;padding:48px 16px 64px}}h1{{font-size:28px;letter-spacing:-.02em;margin:0 0 6px}}
p.lead{{color:var(--muted);margin:0 0 32px}}section{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;margin:0 0 20px}}
h2{{font-size:18px;margin:0 0 4px}}.desc{{color:var(--muted);font-size:14px;margin:0 0 14px}}
.row{{display:flex;flex-wrap:wrap;gap:8px}}a.btn,button{{font:inherit;font-size:14px;border-radius:999px;padding:7px 14px;border:1px solid var(--line);background:transparent;color:var(--fg);text-decoration:none;cursor:pointer}}
a.btn.primary{{background:var(--accent);border-color:var(--accent);color:#fff}}code{{font-size:12px;word-break:break-all;color:var(--muted)}}
details{{margin-top:14px}}summary{{cursor:pointer;font-size:14px;color:var(--muted)}}ul{{list-style:none;padding:0;margin:10px 0 0}}
li{{display:grid;grid-template-columns:118px 1fr;gap:10px;padding:7px 0;border-top:1px solid var(--line);font-size:14px}}
li .d{{color:var(--muted);font-variant-numeric:tabular-nums}}li .t small{{color:var(--muted)}}.tbd{{color:var(--accent);font-size:12px}}
.help{{font-size:14px;color:var(--muted)}}.help b{{color:var(--fg);font-weight:600}}
</style></head><body><main>
<h1>{title}</h1>
<p class="lead">Subscribe once; your calendar app picks up new and changed events automatically.</p>
{sections}
<section class="help"><b>Outlook (web or new Outlook):</b> Calendar → Add calendar → Subscribe from web → paste the copied link.<br>
<b>Apple Calendar, Outlook for Mac:</b> click “Subscribe”.<br>Updated {updated}.</section>
</main>
<script>
const base = location.href.replace(/[^/]*$/, "");
document.querySelectorAll("[data-ics]").forEach(el => {{
  const url = base + el.dataset.ics;
  if (el.tagName === "A") el.href = url.replace(/^https?:/, "webcal:");
  if (el.tagName === "CODE") el.textContent = url;
  if (el.tagName === "BUTTON") el.onclick = () => navigator.clipboard.writeText(url).then(() => {{ el.textContent = "Copied"; }});
}});
</script></body></html>
"""

SECTION = """<section><h2>{name}</h2><p class="desc">{desc}</p>
<div class="row"><a class="btn primary" data-ics="{file}" href="{file}">Subscribe</a><button data-ics="{file}">Copy link</button><a class="btn" href="{file}" download>Download .ics</a></div>
<p><code data-ics="{file}">{file}</code></p>
<details><summary>{n} upcoming events</summary><ul>{items}</ul></details></section>"""


def _fmt_range(s: date, e: date) -> str:
    if s == e:
        return f"{s:%d %b %Y}"
    if (s.year, s.month) == (e.year, e.month):
        return f"{s:%d}–{e:%d %b %Y}"
    return f"{s:%d %b}–{e:%d %b %Y}"


def to_html(site_title: str, cals: list[tuple[dict, list[dict]]], today: date) -> str:
    sections = []
    for cal, events in cals:
        upcoming = [e for e in events if e["end"] >= today and e["status"] != "cancelled"]
        items = "".join(
            f'<li><span class="d">{_fmt_range(e["start"], e["end"])}</span>'
            f'<span class="t">{html.escape(e["title"])} <small>{html.escape(e.get("location") or "")}</small>'
            f'{" <span class=tbd>date tbc</span>" if e["status"] == "tbd" else ""}</span></li>'
            for e in upcoming
        )
        sections.append(SECTION.format(
            name=html.escape(cal["name"]), desc=html.escape(cal.get("description", "")),
            file=cal["output"], n=len(upcoming), items=items,
        ))
    return PAGE.format(title=html.escape(site_title), sections="\n".join(sections), updated=f"{today:%d %b %Y}")


# ── Pipeline ─────────────────────────────────────────────────────────────────

def build(config: str | Path = "calendars.yaml", out: str | Path | None = "_site", today: date | None = None) -> dict:
    """Validate all calendars; write ICS + index.html to `out` unless it is None."""
    config = Path(config)
    base = config.parent
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    today = today or date.today()
    cutoff = today - timedelta(days=cfg.get("keep_past_days", 365))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    errors, built, page_data = [], [], []
    for cal in cfg["calendars"]:
        events = load_events(base / cal["events"], cal["id"], errors)
        feed = sorted(
            (e for e in events if e["start"] and e["end"] >= cutoff and e["status"] != "discontinued"),
            key=lambda e: (e["start"], e["title"]),
        )
        page_data.append((cal, feed))
        built.append({
            "calendar": cal["id"], "file": cal["output"], "in_feed": len(feed),
            "undated_watchlist": sum(1 for e in events if not e["start"]),
            "tbd_in_feed": sum(1 for e in feed if e["status"] == "tbd"),
        })

    if errors or out is None:
        return {"ok": not errors, "errors": errors, "calendars": built}

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for cal, feed in page_data:
        (out / cal["output"]).write_bytes(to_ics(cal, feed, stamp).encode("utf-8"))
    (out / "index.html").write_text(to_html(cfg.get("site_title", "Event Calendars"), page_data, today), encoding="utf-8")
    return {"ok": True, "errors": [], "calendars": built, "out": str(out)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--config", default="calendars.yaml")
    ap.add_argument("--out", default="_site")
    ap.add_argument("--check", action="store_true", help="validate only, write nothing")
    a = ap.parse_args()
    result = build(a.config, None if a.check else a.out)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)
