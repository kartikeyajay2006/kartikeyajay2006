#!/usr/bin/env python3
"""Generate the two live "signal" assets at the top of the README from real
GitHub data, in one fetch:

  assets/signal-dashboard.svg  — last-12-months stat tiles, weekly
                                 contribution bars (peak + average marked),
                                 and a languages-by-bytes bar.
  assets/commit-city.svg       — the real 12-month contribution calendar as
                                 a synthwave skyline: one building per day,
                                 its height that day's contributions, rising
                                 from a scrolling neon grid under a striped
                                 sun, with the peak day as a beacon tower.

Stdlib-only (no pip install needed in CI). Reads GH_TOKEN (a PAT with
read:user scope — the default GITHUB_TOKEN cannot read
contributionsCollection) and GH_LOGIN from the environment.

What's live vs. derived, so nothing here is a self-reported number:
  - contributions / commits / pull requests: contributionsCollection over
    the trailing 12 months (the widest window that API allows).
  - public repos: owned, public, non-fork repositories.
  - streaks, active days, peak week/day, weekly average: computed from the
    same contribution calendar, with per-day counts taken from the public
    profile calendar so private-org work counts exactly as on the profile.
  - languages: bytes per language summed across those repositories, as
    GitHub's linguist reports them (vendored and generated files are
    already excluded by linguist). Jupyter Notebook is left out because a
    notebook's bytes are mostly stored cell output, not code.

SVG notes (see also generate_atlas.py): GitHub strips <script> and inline
<style>, so all motion is SMIL. GitHub's image proxy (camo) strips internal
href/xlink:href fragment references, which silently collapses <use>/<mpath>
motion paths to a static point — so every animated element carries its own
inline path/values. Anything that must be readable starts visible: bars
and buildings grow via animations that freeze at their final size, so a
renderer that ignores SMIL shows the finished chart and the finished city.

Local preview without the API: set SIGNAL_FIXTURE to a saved GraphQL
response (the raw JSON of QUERY) and the script renders from that file.

Never-fail contract: this script always exits 0. Any problem is logged to
stderr and both output files are left exactly as they were — output is
only written after both SVGs have rendered successfully.
"""
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

LOGIN = os.environ.get("GH_LOGIN", "kartikeyajay2006")
TOKEN = os.environ.get("GH_TOKEN", "")
FIXTURE = os.environ.get("SIGNAL_FIXTURE", "")
DASH_PATH = os.environ.get("DASH_PATH", "assets/signal-dashboard.svg")
CITY_PATH = os.environ.get("CITY_PATH", "assets/commit-city.svg")

W = 900
EASE = "0.42 0 0.58 1"
MONO = "ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace"
SANS = "Helvetica, Arial, sans-serif"
EXCLUDED_LANGS = {"Jupyter Notebook"}
TOP_LANGS = 6

# GitHub's API always returns light-theme hex values; map them onto GitHub's
# own dark-mode scale so the grid still reads as "the real graph".
LEVEL_BY_LIGHT_COLOR = {
    "#ebedf0": 0, "#9be9a8": 1, "#40c463": 2, "#30a14e": 3, "#216e39": 4,
    "#c6e48b": 1, "#7bc96f": 2, "#239a3b": 3, "#196127": 4,
}
DARK_BY_LEVEL = {0: "#161b22", 1: "#0e4429", 2: "#006d32", 3: "#26a641", 4: "#39d353"}
LIGHT_BY_LEVEL = {0: "#ebedf0", 1: "#9be9a8", 2: "#40c463", 3: "#30a14e", 4: "#216e39"}

# The public calendar page is exactly what the profile shows, including
# private-repo and private-org contributions (as bare counts). The GraphQL
# calendar only includes those when the token can see those repos/orgs, so
# a narrowly scoped CI token silently drops them — and breaks the streak.
PUBLIC_CALENDAR_URL = f"https://github.com/users/{LOGIN}/contributions"

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date weekday contributionCount color } }
      }
    }
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 100) {
      totalCount
      nodes {
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


class FetchError(Exception):
    pass


# ------------------------------------------------------------------ data
def _fetch_once():
    now = datetime.now(timezone.utc)
    frm = (now - timedelta(days=364)).replace(hour=0, minute=0, second=0, microsecond=0)
    body = json.dumps({"query": QUERY, "variables": {
        "login": LOGIN,
        "from": frm.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body, method="POST",
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json",
                 "User-Agent": f"{LOGIN}-signal-generator"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code} from GitHub GraphQL: {e.read().decode('utf-8', 'replace')}") from e
    except urllib.error.URLError as e:
        raise FetchError(f"network failure reaching GitHub GraphQL: {e}") from e
    except (TimeoutError, json.JSONDecodeError) as e:
        raise FetchError(f"bad response from GitHub GraphQL: {e}") from e
    return payload


def fetch():
    if FIXTURE:
        with open(FIXTURE, encoding="utf-8") as f:
            return json.load(f)
    if not TOKEN:
        raise FetchError("GH_TOKEN is not set. Add a classic PAT with 'read:user' scope as the "
                         "GH_CONTRIB_PAT repo secret.")
    last_err = None
    for attempt in range(3):
        try:
            return _fetch_once()
        except FetchError as e:
            last_err = e
            print(f"WARNING: attempt {attempt + 1}/3 failed: {e}", file=sys.stderr)
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise last_err


def fetch_public_calendar():
    """Per-day {date: (count, level)} from the public profile calendar.
    Returns {} on any failure — the API data is then used on its own."""
    if FIXTURE:
        return {}
    req = urllib.request.Request(PUBLIC_CALENDAR_URL, headers={"User-Agent": f"{LOGIN}-signal-generator"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: public calendar unavailable, using API data only: {e}", file=sys.stderr)
        return {}

    def attr(tag, name):
        m = re.search(rf'\b{name}="([^"]*)"', tag)
        return m.group(1) if m else None

    cells = {}  # id -> (date, level)
    for tag in re.findall(r"<td\b[^>]*ContributionCalendar-day[^>]*>", html):
        cid, day, lvl = attr(tag, "id"), attr(tag, "data-date"), attr(tag, "data-level")
        if cid and day and lvl is not None and lvl.isdigit():
            cells[cid] = (day, int(lvl))
    counts = {}  # id -> count
    for cid, text in re.findall(r'<tool-tip\b[^>]*\bfor="([^"]+)"[^>]*>([^<]*)</tool-tip>', html):
        text = text.strip()
        m = re.match(r"([\d,]+) contributions? on", text)
        if m:
            counts[cid] = int(m.group(1).replace(",", ""))
        elif text.startswith("No contributions"):
            counts[cid] = 0

    out = {}
    for cid, (day, lvl) in cells.items():
        if cid in counts:
            out[day] = (counts[cid], min(4, lvl))
    if len(out) < 300:  # page layout changed or partial render — don't trust it
        print(f"WARNING: public calendar parsed only {len(out)} days, using API data only", file=sys.stderr)
        return {}
    return out


def merge_public_calendar(weeks, public):
    """Swap the API's per-day counts for the profile calendar's, so the grid,
    streak and totals match the real profile. The two sources bucket days in
    slightly different timezones, so per-day max would double-count — it is
    all-or-nothing instead. The public data is only used when it covers every
    day and adds up to at least the API total (it can only ever add the
    private contributions the token can't see). Returns the new total, or
    None when the API data is kept."""
    days = [d for w in weeks for d in w["contributionDays"]]
    if not public or any(d["date"] not in public for d in days):
        return None
    api_total = sum(d["contributionCount"] for d in days)
    pub_total = sum(public[d["date"]][0] for d in days)
    if pub_total < api_total:
        return None
    for d in days:
        d["contributionCount"], lvl = public[d["date"]]
        d["color"] = LIGHT_BY_LEVEL[lvl]
    if pub_total > api_total:
        print(f"Public calendar adds {pub_total - api_total} private contributions the token can't see.")
    return pub_total


def parse(payload, public=None):
    if payload.get("errors"):
        raise FetchError(f"GraphQL returned errors: {payload['errors']}")
    user = (payload.get("data") or {}).get("user")
    if not user:
        raise FetchError(f"user '{LOGIN}' not found in GraphQL response")
    coll = user["contributionsCollection"]
    cal = coll["contributionCalendar"]
    weeks = cal.get("weeks") or []
    if len(weeks) < 10:
        raise FetchError("contribution calendar came back nearly empty")
    merged_total = merge_public_calendar(weeks, public or {})

    days = [d for w in weeks for d in w["contributionDays"]]
    counts = [d["contributionCount"] for d in days]
    max_day = max(counts) or 1
    week_totals = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks]

    # streaks — today may simply not have contributions *yet*, so the current
    # streak is allowed to end yesterday
    longest = run = 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    tail = counts[:-1] if counts and counts[-1] == 0 else counts
    current = 0
    for c in reversed(tail):
        if c == 0:
            break
        current += 1

    langs, colors = {}, {}
    for repo in user["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            if name in EXCLUDED_LANGS:
                continue
            langs[name] = langs.get(name, 0) + e["size"]
            colors[name] = e["node"]["color"] or "#8b949e"
    total_bytes = sum(langs.values()) or 1
    ranked = sorted(langs.items(), key=lambda kv: -kv[1])
    lang_rows = [(n, b / total_bytes, colors[n]) for n, b in ranked[:TOP_LANGS]]
    rest = sum(b for _, b in ranked[TOP_LANGS:]) / total_bytes
    if rest > 0:
        lang_rows.append(("Other", rest, "#6e7681"))

    peak_w = max(range(len(week_totals)), key=lambda i: week_totals[i])
    peak_d = max(days, key=lambda d: d["contributionCount"])
    return {
        "weeks": weeks,
        "week_totals": week_totals,
        "total": max(cal["totalContributions"], merged_total or 0),
        "commits": coll["totalCommitContributions"],
        "prs": coll["totalPullRequestContributions"],
        "repos": user["repositories"]["totalCount"],
        "current_streak": current,
        "longest_streak": longest,
        "active_days": sum(1 for c in counts if c > 0),
        "n_days": len(days),
        "max_day": max_day,
        "peak_week": peak_w,
        "peak_day": peak_d,
        "langs": lang_rows,
        "synced": datetime.now(timezone.utc),
    }


# ------------------------------------------------------------------ helpers
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def d_of(s):
    return date.fromisoformat(s)


def fmt_day(s):
    d = d_of(s)
    return f"{d.strftime('%b')} {d.day}"


def breathe(attr, values, dur, begin="0s"):
    n = len(values.split(";"))
    kt = ";".join(f"{i / (n - 1):.3f}" for i in range(n))
    return (f'<animate attributeName="{attr}" values="{values}" keyTimes="{kt}" calcMode="spline" '
            f'keySplines="{";".join([EASE] * (n - 1))}" dur="{dur}" begin="{begin}" repeatCount="indefinite"/>')


def level(day, max_count):
    lvl = LEVEL_BY_LIGHT_COLOR.get((day.get("color") or "").lower())
    if lvl is None:
        c = day["contributionCount"]
        lvl = 0 if c == 0 else min(4, 1 + int(3 * c / max_count))
    return lvl


def frame(h, label, right):
    return (f'<rect x="0.5" y="0.5" width="{W-1}" height="{h-1}" rx="14" fill="#0a0a0a" stroke="#1f1f1f"/>'
            f'<rect x="14" y="14" width="{W-28}" height="{h-28}" fill="url(#dotgrid)"/>'
            f'<text x="20" y="28" font-family="{MONO}" font-size="10" letter-spacing="1" fill="#555">{label}</text>'
            f'<circle cx="{W-24}" cy="24.5" r="3" fill="#22c55e" filter="url(#glow)">{breathe("opacity", "1;0.3;1", "1.8s")}</circle>'
            f'<text x="{W-34}" y="28" text-anchor="end" font-family="{MONO}" font-size="10" letter-spacing="1" fill="#555">{right}</text>')


COMMON_DEFS = """
    <pattern id="dotgrid" width="28" height="28" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#141414"/></pattern>
    <filter id="glow" x="-250%" y="-250%" width="600%" height="600%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="softBlur" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="4"/></filter>"""


# ------------------------------------------------------------------ dashboard
def build_dashboard(d):
    synced = d["synced"]
    parts = []
    tiles = [
        ("CONTRIBUTIONS", f'{d["total"]:,}', "last 12 months", "#f5a623"),
        ("COMMITS", f'{d["commits"]:,}', "authored", "#22d3ee"),
        ("PULL REQUESTS", f'{d["prs"]:,}', "opened", "#a855f7"),
        ("PUBLIC REPOS", f'{d["repos"]:,}', "owned · non-fork", "#22c55e"),
        ("DAY STREAK", f'{d["current_streak"]}', f'best {d["longest_streak"]} days', "#ec4899"),
    ]
    tile_y, tile_h, gap = 42, 74, 10
    tw = (W - 40 - gap * (len(tiles) - 1)) / len(tiles)

    chart_y = tile_y + tile_h + 14          # chart card top
    chart_h = 196
    lang_y = chart_y + chart_h + 12         # languages card top
    lang_h = 92
    H = lang_y + lang_h + 20

    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
                 f'aria-labelledby="sigTitle sigDesc">')
    parts.append('<title id="sigTitle">Live GitHub signal — last 12 months</title>')
    langs_txt = ", ".join(f"{n} {p*100:.1f}%" for n, p, _ in d["langs"])
    parts.append(f'<desc id="sigDesc">Last 12 months: {d["total"]} contributions, {d["commits"]} commits, '
                 f'{d["prs"]} pull requests, {d["repos"]} public repositories, current streak {d["current_streak"]} '
                 f'days (best {d["longest_streak"]}). Peak week {d["week_totals"][d["peak_week"]]} contributions. '
                 f'Languages by bytes: {langs_txt}. Synced {synced.strftime("%Y-%m-%d %H:%M")} UTC.</desc>')

    n = len(d["week_totals"])
    cx0, cx1 = 58, W - 36                   # bar area
    base_y = chart_y + chart_h - 34
    top_y = chart_y + 58
    step = (cx1 - cx0) / n
    bw = max(3.0, step * 0.64)

    parts.append(f'''<defs>{COMMON_DEFS}
    <linearGradient id="barGrad" gradientUnits="userSpaceOnUse" x1="{cx0}" y1="0" x2="{cx1}" y2="0">
      <stop offset="0%" stop-color="#22d3ee"/><stop offset="45%" stop-color="#3b82f6"/>
      <stop offset="78%" stop-color="#a855f7"/><stop offset="100%" stop-color="#ec4899"/>
    </linearGradient>
    <linearGradient id="barFade" gradientUnits="userSpaceOnUse" x1="0" y1="{top_y}" x2="0" y2="{base_y}">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.22"/><stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
  </defs>''')
    parts.append(frame(H, "SIGNAL // LIVE", f'LIVE · {synced.strftime("%b %Y").upper()} · SYNCED {synced.strftime("%d %b %H:%M").upper()} UTC'))

    # ---- stat tiles
    for i, (label, value, sub, c) in enumerate(tiles):
        x = 20 + i * (tw + gap)
        parts.append(f'<rect x="{x:.1f}" y="{tile_y}" width="{tw:.1f}" height="{tile_h}" rx="10" fill="#101014" stroke="#1f1f24"/>')
        parts.append(f'<rect x="{x+1:.1f}" y="{tile_y+12}" width="2.5" height="{tile_h-24}" rx="1.2" fill="{c}"/>')
        parts.append(f'<text x="{x+16:.1f}" y="{tile_y+21}" font-family="{MONO}" font-size="9" letter-spacing="1.2" fill="#8a8a8a">{label}</text>')
        parts.append(f'<text x="{x+15:.1f}" y="{tile_y+50}" font-family="{SANS}" font-size="27" font-weight="700" fill="#f2f2f2">{esc(value)}'
                     + (f'<tspan font-size="12" fill="#8a8a8a" font-weight="400"> days</tspan>' if label == "DAY STREAK" else "")
                     + '</text>')
        parts.append(f'<text x="{x+16:.1f}" y="{tile_y+65}" font-family="{MONO}" font-size="9" fill="{c}" opacity="0.85">{esc(sub)}</text>')
        if label == "DAY STREAK" and d["current_streak"] > 0:
            parts.append(f'<circle cx="{x+tw-14:.1f}" cy="{tile_y+16}" r="2.6" fill="{c}" filter="url(#glow)">'
                         f'{breathe("opacity", "1;0.25;1", "1.4s")}</circle>')

    # ---- weekly chart card
    parts.append(f'<rect x="20" y="{chart_y}" width="{W-40}" height="{chart_h}" rx="10" fill="#0d0d10" stroke="#1f1f24"/>')
    parts.append(f'<text x="36" y="{chart_y+24}" font-family="{MONO}" font-size="10.5" font-weight="700" letter-spacing="1" fill="#e0e0e0">'
                 f'WEEKLY CONTRIBUTIONS</text>')
    parts.append(f'<text x="200" y="{chart_y+24}" font-family="{MONO}" font-size="9.5" fill="#666">· last 12 months · '
                 f'{d["active_days"]} active days of {d["n_days"]}</text>')
    pk = d["peak_week"]
    pk_total = d["week_totals"][pk]
    pk_date = d["weeks"][pk]["contributionDays"][0]["date"]
    parts.append(f'<text x="{W-36}" y="{chart_y+24}" text-anchor="end" font-family="{MONO}" font-size="9.5" fill="#666">'
                 f'peak week · <tspan fill="#f5a623" font-weight="700">{pk_total}</tspan> · week of {fmt_day(pk_date)}</text>')

    vmax = max(d["week_totals"]) or 1
    # gridlines at nice round values
    nice = next(v for v in (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000) if vmax / v <= 4)
    g = nice
    while g <= vmax:
        gy = base_y - (base_y - top_y) * g / vmax
        parts.append(f'<line x1="{cx0-6}" y1="{gy:.1f}" x2="{cx1}" y2="{gy:.1f}" stroke="#1c1c22" stroke-dasharray="2 4"/>')
        parts.append(f'<text x="{cx0-10}" y="{gy+3:.1f}" text-anchor="end" font-family="{MONO}" font-size="8" fill="#444">{g}</text>')
        g += nice
    parts.append(f'<line x1="{cx0-6}" y1="{base_y}" x2="{cx1}" y2="{base_y}" stroke="#2a2a30"/>')

    # bars — grow once, left to right, then hold (static renderers see the final bars)
    for i, v in enumerate(d["week_totals"]):
        x = cx0 + i * step + (step - bw) / 2
        h = max(2.0, (base_y - top_y) * v / vmax)
        y = base_y - h
        delay = 0.2 + i * 0.022
        grow = (f'<animate attributeName="height" values="0;0;{h:.1f}" keyTimes="0;{delay/(delay+0.7):.3f};1" '
                f'dur="{delay+0.7:.2f}s" fill="freeze" calcMode="spline" keySplines="{EASE};{EASE}"/>'
                f'<animate attributeName="y" values="{base_y};{base_y};{y:.1f}" keyTimes="0;{delay/(delay+0.7):.3f};1" '
                f'dur="{delay+0.7:.2f}s" fill="freeze" calcMode="spline" keySplines="{EASE};{EASE}"/>')
        if v == 0:
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="1" fill="#24242c"/>')
            continue
        op = 0.55 + 0.45 * (v / vmax) ** 0.6
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="2" fill="url(#barGrad)" opacity="{op:.2f}">{grow}</rect>')
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="2" fill="url(#barFade)">{grow}</rect>')

    # peak marker
    px = cx0 + pk * step + step / 2
    py = base_y - (base_y - top_y)
    parts.append(f'<circle cx="{px:.1f}" cy="{py-9:.1f}" r="3" fill="#f5a623" filter="url(#glow)">{breathe("opacity", "1;0.35;1", "1.6s")}</circle>')
    parts.append(f'<circle cx="{px:.1f}" cy="{py-9:.1f}" r="3" fill="none" stroke="#f5a623" stroke-width="1">'
                 f'{breathe("r", "3;10;10", "2.2s")}{breathe("opacity", "0.9;0;0", "2.2s")}</circle>')
    lbl_anchor = "end" if px > cx1 - 60 else "start"
    lbl_x = px - 8 if lbl_anchor == "end" else px + 8
    parts.append(f'<text x="{lbl_x:.1f}" y="{py-6:.1f}" text-anchor="{lbl_anchor}" font-family="{MONO}" font-size="9" '
                 f'font-weight="700" fill="#f5a623">PEAK {pk_total}</text>')

    # average line
    avg = sum(d["week_totals"]) / n
    ay = base_y - (base_y - top_y) * avg / vmax
    parts.append(f'<line x1="{cx0}" y1="{ay:.1f}" x2="{cx1}" y2="{ay:.1f}" stroke="#f5a623" stroke-width="1" '
                 f'stroke-dasharray="5 4" opacity="0.55"/>')
    parts.append(f'<rect x="{cx0-4}" y="{ay-15:.1f}" width="64" height="12" rx="3" fill="#0d0d10" opacity="0.92"/>')
    parts.append(f'<text x="{cx0}" y="{ay-6:.1f}" font-family="{MONO}" font-size="8.5" fill="#f5a623">avg {avg:.0f} / week</text>')

    # "now" marker on the latest week
    nx = cx0 + (n - 1) * step + step / 2
    parts.append(f'<circle cx="{nx:.1f}" cy="{base_y+6}" r="2.2" fill="#22c55e">{breathe("opacity", "1;0.2;1", "1.2s")}</circle>')

    # month axis
    last_x = -99
    prev_month = None
    for i, w in enumerate(d["weeks"]):
        first = d_of(w["contributionDays"][0]["date"])
        if first.month != prev_month:
            prev_month = first.month
            mx = cx0 + i * step
            if mx - last_x >= 34:
                lab = first.strftime("%b") + (first.strftime(" ’%y") if i == 0 or first.month == 1 else "")
                parts.append(f'<text x="{mx:.1f}" y="{base_y+20}" font-family="{MONO}" font-size="8.5" '
                             f'fill="{"#888" if first.month == 1 or i == 0 else "#555"}">{lab}</text>')
                last_x = mx + (24 if first.month == 1 or i == 0 else 0)
    parts.append(f'<text x="{cx1}" y="{base_y+20}" text-anchor="end" font-family="{MONO}" font-size="8.5" fill="#22c55e">now</text>')

    # ---- languages card
    parts.append(f'<rect x="20" y="{lang_y}" width="{W-40}" height="{lang_h}" rx="10" fill="#0d0d10" stroke="#1f1f24"/>')
    parts.append(f'<text x="36" y="{lang_y+24}" font-family="{MONO}" font-size="10.5" font-weight="700" letter-spacing="1" fill="#e0e0e0">LANGUAGES</text>')
    parts.append(f'<text x="118" y="{lang_y+24}" font-family="{MONO}" font-size="9.5" fill="#666">· by bytes of code across '
                 f'{d["repos"]} public repos · vendored files and notebooks excluded</text>')
    bx0, bx1, by = 36, W - 36, lang_y + 36
    bar_w = bx1 - bx0
    parts.append(f'<rect x="{bx0}" y="{by}" width="{bar_w}" height="12" rx="6" fill="#1a1a20"/>')
    # one clip-free trick for rounded ends: draw segments inside a rounded track
    cur = bx0
    seg_parts = []
    for i, (name, pct, color) in enumerate(d["langs"]):
        sw = bar_w * pct
        delay = 0.4 + i * 0.12
        seg_parts.append(f'<rect x="{cur:.1f}" y="{by}" width="{max(sw-1.5, 1):.1f}" height="12" fill="{color}">'
                         f'<animate attributeName="width" values="0;0;{max(sw-1.5, 1):.1f}" keyTimes="0;{delay/(delay+0.6):.3f};1" '
                         f'dur="{delay+0.6:.2f}s" fill="freeze" calcMode="spline" keySplines="{EASE};{EASE}"/></rect>')
        cur += sw
    parts.append(f'<g>{"".join(seg_parts)}</g>')
    # round the ends by masking corners with the card colour
    parts.append(f'<path d="M{bx0},{by} h6 a6,6 0 0 0 -6,6 Z M{bx0},{by+12} h6 a6,6 0 0 1 -6,-6 Z" fill="#0d0d10"/>')
    parts.append(f'<path d="M{bx1},{by} h-6 a6,6 0 0 1 6,6 Z M{bx1},{by+12} h-6 a6,6 0 0 0 6,-6 Z" fill="#0d0d10"/>')
    # legend
    lx = bx0
    for name, pct, color in d["langs"]:
        label = f"{name} {pct*100:.1f}%"
        parts.append(f'<circle cx="{lx+4}" cy="{lang_y+68}" r="4" fill="{color}"/>')
        parts.append(f'<text x="{lx+13}" y="{lang_y+71.5}" font-family="{MONO}" font-size="10" fill="#c9c9c9">{esc(name)} '
                     f'<tspan fill="#777">{pct*100:.1f}%</tspan></text>')
        lx += 13 + len(label) * 6.1 + 22

    parts.append('</svg>')
    return "\n".join(parts)


# ------------------------------------------------------------------ commit city
# The contribution calendar as a synthwave skyline: one building per day, its
# height the contributions that day, standing on a neon grid floor under a
# striped sun. Weeks run left to right; weekdays recede into the city (Sunday
# at the back, Saturday at the front), so the block is the real 53 x 7 grid.
CITY_H = 470
HORIZON = 262
DX = 13.4            # one week
FW = 9.4             # building footprint width
OX, OY = 4.6, 4.3    # one weekday deeper into the city: this far right and up
FD = 0.74            # footprint depth, as a share of one weekday row
HMAX = 118           # the peak day's height
GROUND = 357         # ground line of the front row (Saturday)
ROOF_STOPS = [(0.0, (0x4c, 0x1d, 0x95)), (0.22, (0x8b, 0x5c, 0xf6)), (0.48, (0xec, 0x48, 0x99)),
              (0.74, (0xfb, 0x92, 0x3c)), (1.0, (0xfd, 0xe0, 0x47))]


def _mix(c0, c1, k):
    return tuple(round(a + (b - a) * k) for a, b in zip(c0, c1))


def _hex(c):
    return "#" + "".join(f"{v:02x}" for v in c)


def roof_rgb(t):
    t = max(0.0, min(1.0, t))
    for (t0, c0), (t1, c1) in zip(ROOF_STOPS, ROOF_STOPS[1:]):
        if t <= t1:
            return _mix(c0, c1, (t - t0) / (t1 - t0))
    return ROOF_STOPS[-1][1]


def _pts(points):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def build_city(d):
    import random
    rnd = random.Random(2375)
    weeks = d["weeks"]
    ncol = len(weeks)
    H = CITY_H
    max_c = d["max_day"] or 1
    pdd = d["peak_day"]
    synced = d["synced"]
    block_w = ncol * DX + 6 * OX + FW
    gx0 = (W - block_w) / 2
    last_day = weeks[-1]["contributionDays"][-1]["date"]

    def base(col, weekday):
        k = 6 - weekday                      # 0 = front row
        return gx0 + col * DX + k * OX, GROUND - k * OY, k

    def ground_y(k):
        return GROUND - k * OY

    p = []
    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-labelledby="cityTitle cityDesc">')
    p.append('<title id="cityTitle">Commit City — twelve months of contributions as a skyline</title>')
    p.append(f'<desc id="cityDesc">The real GitHub contribution calendar for the last 12 months drawn as a synthwave '
             f'city: one building per day, its height the contributions that day, weeks running left to right and '
             f'weekdays receding into the city. {d["total"]:,} contributions over {d["active_days"]} active days; '
             f'the tallest tower is the peak day, {pdd["contributionCount"]} on {fmt_day(pdd["date"])}; longest streak '
             f'{d["longest_streak"]} days. The buildings rise from the grid, a striped sun sets behind them, the '
             f'floor scrolls toward the viewer and light trails cross the sky.</desc>')

    # ---------------------------------------------------------------- defs
    p.append(f'''<defs>
    <clipPath id="cityFrame"><rect x="0" y="0" width="{W}" height="{H}" rx="14"/></clipPath>
    <clipPath id="citySky"><rect x="0" y="0" width="{W}" height="{HORIZON}"/></clipPath>
    <linearGradient id="citySkyFill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#05020e"/><stop offset="0.55" stop-color="#12072b"/><stop offset="1" stop-color="#2b0d4d"/>
    </linearGradient>
    <linearGradient id="cityFloorFill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#1c0838"/><stop offset="0.35" stop-color="#0c0420"/><stop offset="1" stop-color="#04020a"/>
    </linearGradient>
    <linearGradient id="citySun" x1="0" y1="{HORIZON - 124}" x2="0" y2="{HORIZON}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#fff4b8"/><stop offset="0.32" stop-color="#ffc35a"/><stop offset="0.62" stop-color="#ff5c8d"/><stop offset="1" stop-color="#b5179e"/>
    </linearGradient>
    <radialGradient id="citySunGlow" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#ff4fa3" stop-opacity="0.55"/><stop offset="0.55" stop-color="#b5179e" stop-opacity="0.18"/><stop offset="1" stop-color="#b5179e" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="cityGridFade" x1="0" y1="{HORIZON}" x2="0" y2="{H}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#ff3fd8" stop-opacity="0"/><stop offset="0.25" stop-color="#ff3fd8" stop-opacity="0.35"/><stop offset="1" stop-color="#ff3fd8" stop-opacity="0.85"/>
    </linearGradient>
    <linearGradient id="cityBeam" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0" stop-color="#c4b5fd" stop-opacity="0.32"/><stop offset="1" stop-color="#c4b5fd" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="cityChrome" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#f0fbff"/><stop offset="0.46" stop-color="#7dd3fc"/><stop offset="0.5" stop-color="#1e1b4b"/>
      <stop offset="0.54" stop-color="#f0abfc"/><stop offset="1" stop-color="#fff1fb"/>
    </linearGradient>
    <linearGradient id="cityHudShade" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#04020a" stop-opacity="0"/><stop offset="1" stop-color="#04020a" stop-opacity="0.92"/>
    </linearGradient>
    <linearGradient id="cityHaze" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#2a0d4d" stop-opacity="0"/><stop offset="0.75" stop-color="#2a0d4d" stop-opacity="0.38"/><stop offset="1" stop-color="#12062a" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="cityPool" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#ff3fd8" stop-opacity="0.32"/><stop offset="1" stop-color="#ff3fd8" stop-opacity="0"/>
    </radialGradient>
    <pattern id="cityWinA" width="4.6" height="5" patternUnits="userSpaceOnUse">
      <rect x="1" y="1.2" width="1.5" height="1.9" fill="#ffe3a3" opacity="0.55"/>
    </pattern>
    <pattern id="cityWinB" width="4.6" height="5" patternUnits="userSpaceOnUse" x="2.3">
      <rect x="1" y="1.2" width="1.5" height="1.9" fill="#a5f3fc" opacity="0.45"/>
    </pattern>
    <filter id="cityBloom" x="-5%" y="-20%" width="110%" height="140%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="2.2" result="b"/>
      <feColorMatrix in="b" type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 0.9 0" result="g"/>
      <feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="cityGlow" x="-300%" y="-300%" width="700%" height="700%"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    {"".join(f'<clipPath id="cityRow{k}"><rect x="0" y="0" width="{W}" height="{ground_y(k) + 0.4:.1f}"/></clipPath>' for k in range(7))}
  </defs>''')

    p.append('<g clip-path="url(#cityFrame)">')
    # ---------------------------------------------------------------- sky
    p.append(f'<rect x="0" y="0" width="{W}" height="{HORIZON}" fill="url(#citySkyFill)"/>')
    for i in range(70):
        x, y = rnd.uniform(10, W - 10), rnd.uniform(8, HORIZON - 40)
        if abs(x - W / 2) < 150 and y > HORIZON - 150:
            continue
        r = rnd.choice((0.5, 0.6, 0.7, 0.9, 1.2))
        tw = ""
        if i % 3 == 0:
            tw = (f'<animate attributeName="opacity" values="0.9;0.15;0.9" dur="{rnd.uniform(2.2, 5.5):.1f}s" '
                  f'begin="{rnd.uniform(0, 4):.1f}s" repeatCount="indefinite"/>')
        p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="#f5e9ff" opacity="{rnd.uniform(0.35, 0.9):.2f}">{tw}</circle>')
    # shooting star, every ~11 s
    p.append('<g opacity="0"><animate attributeName="opacity" values="0;0;1;0;0" keyTimes="0;0.7;0.72;0.78;1" '
             'dur="11s" repeatCount="indefinite"/>'
             '<line x1="0" y1="0" x2="-38" y2="-10" stroke="#ffffff" stroke-width="1.2" stroke-linecap="round" opacity="0.8">'
             '<animateTransform attributeName="transform" type="translate" values="640,40;640,40;760,72;760,72" '
             'keyTimes="0;0.7;0.78;1" dur="11s" repeatCount="indefinite"/></line></g>')

    # searchlights sweeping behind the city
    for bx, d0, dur in ((150, -16, "9s"), (760, 14, "11s")):
        p.append(f'<path d="M{bx - 3},{GROUND - 30} L{bx - 34},{40} L{bx + 34},{40} L{bx + 3},{GROUND - 30} Z" '
                 f'fill="url(#cityBeam)" opacity="0.8">'
                 f'<animateTransform attributeName="transform" type="rotate" '
                 f'values="{d0} {bx} {GROUND - 30};{-d0} {bx} {GROUND - 30};{d0} {bx} {GROUND - 30}" '
                 f'keyTimes="0;0.5;1" calcMode="spline" keySplines="{EASE};{EASE}" dur="{dur}" repeatCount="indefinite"/></path>')

    # the sun, setting behind the skyline, with stripes that drift down into the horizon
    scx, sr = W / 2 + 40, 124
    p.append(f'<circle cx="{scx}" cy="{HORIZON - 8}" r="{sr + 70}" fill="url(#citySunGlow)"/>')
    bands = []
    n_bands = 8
    for i in range(n_bands):
        def band(j):
            f = j / n_bands
            y = HORIZON - sr * 0.56 + f * sr * 0.56
            return y, 0.6 + 6.2 * f
        (y0, h0), (y1, h1) = band(i), band(i + 1)
        bands.append(f'<rect x="{scx - sr - 2}" y="{y0:.1f}" width="{2 * sr + 4}" height="{h0:.1f}" fill="#000">'
                     f'<animate attributeName="y" values="{y0:.1f};{y1:.1f}" dur="2.6s" repeatCount="indefinite"/>'
                     f'<animate attributeName="height" values="{h0:.1f};{h1:.1f}" dur="2.6s" repeatCount="indefinite"/></rect>')
    p.append(f'<mask id="citySunMask" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{HORIZON}">'
             f'<rect x="0" y="0" width="{W}" height="{HORIZON}" fill="#fff"/>{"".join(bands)}</mask>')
    p.append(f'<g clip-path="url(#citySky)"><circle cx="{scx}" cy="{HORIZON - 8}" r="{sr}" fill="url(#citySun)" '
             f'mask="url(#citySunMask)"/></g>')

    # distant mountains on the horizon
    for layer, (amp, fill, stroke, so) in enumerate(((30, "#170830", "#8b5cf6", 0.55), (17, "#0f0524", "#e040fb", 0.4))):
        pts, x = [(0, HORIZON)], 0.0
        while x < W:
            x += rnd.uniform(18, 46)
            pts.append((min(x, W), HORIZON - rnd.uniform(0.15, 1.0) * amp * (0.55 if abs(x - scx) < 120 else 1)))
        pts.append((W, HORIZON))
        p.append(f'<polygon points="{_pts(pts)}" fill="{fill}"/>')
        p.append(f'<polyline points="{_pts(pts[1:-1])}" fill="none" stroke="{stroke}" stroke-width="0.8" opacity="{so}"/>')

    # ---------------------------------------------------------------- floor
    p.append(f'<rect x="0" y="{HORIZON}" width="{W}" height="{H - HORIZON}" fill="url(#cityFloorFill)"/>')
    p.append(f'<line x1="0" y1="{HORIZON}" x2="{W}" y2="{HORIZON}" stroke="#ff7ad9" stroke-width="1.2" opacity="0.9" filter="url(#cityGlow)"/>')
    vpx = W / 2
    for k in range(-16, 17):
        xb = vpx + k * 62
        p.append(f'<line x1="{vpx + k * 2.2:.1f}" y1="{HORIZON}" x2="{xb:.1f}" y2="{H}" stroke="url(#cityGridFade)" stroke-width="1"/>')
    # horizontal lines rushing toward the viewer, in true perspective
    C = H + 30 - HORIZON
    step_z, n_lines, period = 0.62, 15, 1.8
    for n in range(1, n_lines + 1):
        ys, ops = [], []
        for s in range(9):
            z = 1 + (n - s / 8) * step_z
            y = HORIZON + C / z
            ys.append(f"{y:.1f}")
            ops.append(f"{min(1.0, 2.2 / z):.2f}")
        vals, ov = ";".join(ys), ";".join(ops)
        p.append(f'<line x1="0" x2="{W}" y1="{ys[0]}" y2="{ys[0]}" stroke="#ff3fd8" stroke-width="1" opacity="{ops[0]}">'
                 f'<animate attributeName="y1" values="{vals}" dur="{period}s" repeatCount="indefinite"/>'
                 f'<animate attributeName="y2" values="{vals}" dur="{period}s" repeatCount="indefinite"/>'
                 f'<animate attributeName="opacity" values="{ov}" dur="{period}s" repeatCount="indefinite"/></line>')
    # the sun's reflection shimmering on the floor between the horizon and the city
    for i in range(7):
        ry = HORIZON + 5 + i * 7.5
        rw = (sr * 1.5) * (1 - i * 0.11)
        p.append(f'<rect x="{scx - rw / 2:.1f}" y="{ry:.1f}" width="{rw:.1f}" height="{2.2 - i * 0.18:.2f}" rx="1" '
                 f'fill="#ff9ccf" opacity="{0.34 - i * 0.04:.2f}">'
                 f'<animate attributeName="opacity" values="{0.34 - i * 0.04:.2f};{0.1 - i * 0.01:.2f};{0.34 - i * 0.04:.2f}" '
                 f'dur="{1.6 + i * 0.37:.2f}s" repeatCount="indefinite"/></rect>')
    # neon pool under the city
    p.append(f'<ellipse cx="{gx0 + block_w / 2:.1f}" cy="{GROUND - 12}" rx="{block_w * 0.56:.1f}" ry="34" fill="url(#cityPool)"/>')

    # ---------------------------------------------------------------- the city
    city, lit, tops = [], [], []
    peak_top = today_top = None
    for k in range(6, -1, -1):
        for col, w in enumerate(weeks):
            for day in w["contributionDays"]:
                if 6 - day["weekday"] != k:
                    continue
                x, y, _ = base(col, day["weekday"])
                c = day["contributionCount"]
                fl, fr = (x, y), (x + FW, y)
                br, bl = (x + FW + FD * OX, y - FD * OY), (x + FD * OX, y - FD * OY)
                if c == 0:
                    city.append(f'<polygon points="{_pts((fl, fr, br, bl))}" fill="#170b2e" stroke="#2c1452" stroke-width="0.5"/>')
                    if day["date"] == last_day:
                        today_top = (x + FW / 2 + FD * OX / 2, y - FD * OY / 2)
                    continue
                t = math.sqrt(c / max_c)
                h = max(3.0, HMAX * t)
                roof = roof_rgb(t)
                front = _hex(_mix(roof, (0x0b, 0x05, 0x18), 0.8))
                side = _hex(_mix(roof, (0x06, 0x03, 0x0e), 0.88))
                up = lambda q: (q[0], q[1] - h)  # noqa: E731
                faces = [
                    f'<polygon points="{_pts((fl, fr, up(fr), up(fl)))}" fill="{front}"/>',
                    f'<polygon points="{_pts((fr, br, up(br), up(fr)))}" fill="{side}"/>',
                    f'<polygon points="{_pts((up(fl), up(fr), up(br), up(bl)))}" fill="{_hex(roof)}"/>',
                    f'<line x1="{fl[0]:.1f}" y1="{fl[1] - h:.1f}" x2="{fr[0]:.1f}" y2="{fr[1] - h:.1f}" stroke="{_hex(_mix(roof, (255, 255, 255), 0.35))}" stroke-width="0.7"/>',
                ]
                if h > 16:
                    win = "cityWinA" if (col + k) % 2 else "cityWinB"
                    faces.insert(1, f'<rect x="{x + 0.8:.1f}" y="{y - h + 3:.1f}" width="{FW - 1.6:.1f}" height="{h - 5:.1f}" '
                                    f'fill="url(#{win})"/>')
                delay = 0.25 + col * 0.04 + (6 - k) * 0.03
                kk = delay / (delay + 0.9)
                city.append(f'<g clip-path="url(#cityRow{k})"><g>'
                            f'<animateTransform attributeName="transform" type="translate" values="0,{h + 2:.1f};0,{h + 2:.1f};0,0" '
                            f'keyTimes="0;{kk:.4f};1" dur="{delay + 0.9:.2f}s" fill="freeze" calcMode="spline" '
                            f'keySplines="{EASE};0.16 1 0.3 1"/>{"".join(faces)}</g></g>')
                if h > 34 and rnd.random() < 0.55:
                    for _ in range(rnd.randint(1, 3)):
                        wx = x + 1.8 + rnd.choice((0, 2.3, 4.6))
                        wy = y - h + 6 + rnd.uniform(0, h - 14)
                        lit.append(f'<rect x="{wx:.1f}" y="{wy:.1f}" width="1.6" height="2" fill="#fff3c4" opacity="0">'
                                   f'<animate attributeName="opacity" values="0;0;0.95;0.95;0" keyTimes="0;0.3;0.34;0.86;1" '
                                   f'dur="{rnd.uniform(3, 8):.1f}s" begin="{3 + rnd.uniform(0, 6):.1f}s" repeatCount="indefinite"/></rect>')
                tops.append((h, x + FW / 2 + FD * OX / 2, y - h - FD * OY / 2, day["date"]))
                if day["date"] == pdd["date"]:
                    peak_top = (x + FW / 2 + FD * OX / 2, y - h - FD * OY / 2)
                if day["date"] == last_day:
                    today_top = (x + FW / 2 + FD * OX / 2, y - h - FD * OY / 2)
    p.append(f'<g filter="url(#cityBloom)">{"".join(city)}</g>')
    p.append(f'<rect x="0" y="{GROUND - 34}" width="{W}" height="44" fill="url(#cityHaze)"/>')
    p.append(f'<g>{"".join(lit)}</g>')

    city_done = 0.25 + (len(weeks) - 1) * 0.04 + 6 * 0.03 + 0.9
    p.append(f'<g><animate attributeName="opacity" values="0;0;1" keyTimes="0;{city_done / (city_done + 0.6):.3f};1" '
             f'dur="{city_done + 0.6:.2f}s" fill="freeze"/>')
    # aviation lights on the tallest towers
    for i, (h, tx, ty, dt) in enumerate(sorted(tops, reverse=True)[:9]):
        if dt == pdd["date"]:
            continue
        p.append(f'<circle cx="{tx:.1f}" cy="{ty - 1.5:.1f}" r="1.4" fill="#ff4d4d" filter="url(#cityGlow)">'
                 f'<animate attributeName="opacity" values="1;1;0.08;0.08" keyTimes="0;0.5;0.55;1" '
                 f'dur="{1.1 + (i % 4) * 0.23:.2f}s" begin="{i * 0.31:.2f}s" repeatCount="indefinite"/></circle>')
    # peak-day tower: antenna, aviation light, callout
    if peak_top:
        tx, ty = peak_top
        p.append(f'<line x1="{tx:.1f}" y1="{ty:.1f}" x2="{tx:.1f}" y2="{ty - 16:.1f}" stroke="#fde68a" stroke-width="1.1"/>')
        p.append(f'<circle cx="{tx:.1f}" cy="{ty - 17:.1f}" r="2.3" fill="#ff3b3b" filter="url(#cityGlow)">'
                 f'<animate attributeName="opacity" values="1;1;0.1;0.1" keyTimes="0;0.45;0.5;1" dur="1.3s" repeatCount="indefinite"/></circle>')
        p.append(f'<circle cx="{tx:.1f}" cy="{ty - 17:.1f}" r="3" fill="none" stroke="#fde047" stroke-width="1">'
                 f'{breathe("r", "3;16;16", "2.4s")}{breathe("opacity", "0.9;0;0", "2.4s")}</circle>')
        lx, ly = tx + 18, ty - 50
        label = f"PEAK DAY · {pdd['contributionCount']} · {fmt_day(pdd['date']).upper()}"
        lw = len(label) * 6.75 + 16
        p.append(f'<polyline points="{tx:.1f},{ty - 22:.1f} {tx + 10:.1f},{ly + 6:.1f} {lx:.1f},{ly + 6:.1f}" fill="none" '
                 f'stroke="#fde047" stroke-width="0.8" opacity="0.8"/>')
        p.append(f'<rect x="{lx:.1f}" y="{ly - 7:.1f}" width="{lw:.1f}" height="17" rx="3" fill="#0b0418" stroke="#fde047" '
                 f'stroke-opacity="0.7"/>')
        p.append(f'<text x="{lx + 8:.1f}" y="{ly + 5:.1f}" font-family="{MONO}" font-size="9.5" letter-spacing="1" '
                 f'fill="#fde047">{label}</text>')
    if today_top:
        tx, ty = today_top
        p.append(f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="2.6" fill="#22c55e" filter="url(#cityGlow)"/>')
        p.append(f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="3" fill="none" stroke="#22c55e" stroke-width="1.1">'
                 f'{breathe("r", "3;12;12", "2s")}{breathe("opacity", "0.9;0;0", "2s")}</circle>')
        p.append(f'<text x="{tx + 8:.1f}" y="{ty - 8:.1f}" font-family="{MONO}" font-size="8.5" letter-spacing="1" '
                 f'fill="#4ade80">TODAY</text>')
    p.append('</g>')

    # light trails crossing the sky
    trails = [("M-30,150 C260,118 590,176 940,132", "#22d3ee", 9.5, 0),
              ("M940,205 C640,188 300,222 -30,196", "#ff7ad9", 7.5, -3),
              ("M-30,226 C220,214 640,236 940,220", "#fde047", 6.2, -1.2),
              ("M940,92 C620,76 300,118 -30,98", "#a78bfa", 12.5, -6),
              ("M60,60 C330,96 560,170 940,182", "#4ade80", 14, -9)]
    for i, (path, col_, dur, begin) in enumerate(trails):
        p.append(f'<linearGradient id="cityTrail{i}" gradientUnits="userSpaceOnUse" x1="-26" y1="0" x2="0" y2="0">'
                 f'<stop offset="0" stop-color="{col_}" stop-opacity="0"/><stop offset="1" stop-color="{col_}"/></linearGradient>')
        p.append(f'<g opacity="0"><set attributeName="opacity" to="1" begin="0s"/>'
                 f'<animateMotion path="{path}" dur="{dur}s" begin="{begin}s" rotate="auto" repeatCount="indefinite"/>'
                 f'<line x1="-26" y1="0" x2="0" y2="0" stroke="url(#cityTrail{i})" stroke-width="1.6" stroke-linecap="round"/>'
                 f'<circle r="1.7" fill="#ffffff" filter="url(#cityGlow)"/></g>')

    # month signs along the front edge
    prev_m, last_x = None, -99
    for col, w in enumerate(weeks):
        first = d_of(w["contributionDays"][0]["date"])
        if first.month != prev_m:
            prev_m = first.month
            mx = gx0 + col * DX
            if mx - last_x >= 30 and col > 0:
                p.append(f'<text x="{mx:.1f}" y="{GROUND + 16}" font-family="{MONO}" font-size="8.5" letter-spacing="0.8" '
                         f'fill="#f0abfc" opacity="0.75">{first.strftime("%b").upper()}</text>')
                last_x = mx

    # ---------------------------------------------------------------- HUD
    p.append(f'<rect x="0" y="{H - 64}" width="{W}" height="64" fill="url(#cityHudShade)"/>')
    p.append(f'<text x="24" y="32" font-family="{MONO}" font-size="10" letter-spacing="1.6" fill="#c4b5fd" opacity="0.85">'
             f'COMMIT CITY // LIVE</text>')
    p.append(f'<circle cx="{W - 24}" cy="28.5" r="3" fill="#22c55e" filter="url(#cityGlow)">{breathe("opacity", "1;0.3;1", "1.8s")}</circle>')
    p.append(f'<text x="{W - 34}" y="32" text-anchor="end" font-family="{MONO}" font-size="10" letter-spacing="1.4" '
             f'fill="#c4b5fd" opacity="0.85">LAST 12 MONTHS · SYNCED {synced.strftime("%d %b %H:%M").upper()} UTC</text>')
    p.append(f'<text x="22" y="92" font-family="{SANS}" font-size="52" font-weight="800" font-style="italic" '
             f'letter-spacing="-1" fill="url(#cityChrome)" stroke="#f0abfc" stroke-width="0.6">{d["total"]:,}</text>')
    p.append(f'<text x="25" y="112" font-family="{MONO}" font-size="10" letter-spacing="2.2" fill="#f0abfc">'
             f'CONTRIBUTIONS · {d["active_days"]} ACTIVE DAYS · {d["longest_streak"]}-DAY STREAK</text>')
    # legend: rooftop colour + height = that day's contributions
    lx, ly = 24, H - 22
    p.append(f'<text x="{lx}" y="{ly}" font-family="{MONO}" font-size="9" letter-spacing="1" fill="#a78bfa">ONE BUILDING = ONE DAY</text>')
    sx = lx + 168
    for t in (0.1, 0.3, 0.5, 0.75, 1.0):
        n_ = max(1, round(t * t * max_c))
        p.append(f'<rect x="{sx}" y="{ly - 8.5}" width="10" height="10" rx="1.5" fill="{_hex(roof_rgb(t))}"/>')
        p.append(f'<text x="{sx + 14}" y="{ly}" font-family="{MONO}" font-size="9" fill="#d8b4fe">{n_}</text>')
        sx += 22 + len(str(n_)) * 5.6
    p.append(f'<text x="{W - 24}" y="{ly}" text-anchor="end" font-family="{MONO}" font-size="9" letter-spacing="1" '
             f'fill="#a78bfa">HEIGHT = CONTRIBUTIONS · WEEKS → · SUNDAY AT THE BACK</text>')
    p.append('</g>')
    p.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="#2a1650"/>')
    p.append('</svg>')
    return "\n".join(p)


def main():
    try:
        data = parse(fetch(), fetch_public_calendar())
        dash = build_dashboard(data)
        city = build_city(data)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: signal generation failed, leaving existing files untouched: {e}", file=sys.stderr)
        return 0

    for path, svg in ((DASH_PATH, dash), (CITY_PATH, city)):
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(svg)
            print(f"Wrote {path}")
        except Exception as e:  # noqa: BLE001
            print(f"WARNING: failed to write {path}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
