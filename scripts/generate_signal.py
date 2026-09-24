#!/usr/bin/env python3
"""Generate the two live "signal" assets at the top of the README from real
GitHub data, in one fetch:

  assets/signal-dashboard.svg  — last-12-months stat tiles, weekly
                                 contribution bars (peak + average marked),
                                 and a languages-by-bytes bar.
  assets/pacman-contributions.svg — the real 12-month contribution grid with
                                 pac-man eating it row by row, ghosts in
                                 pursuit, and the peak day as a power pellet.

Stdlib-only (no pip install needed in CI). Reads GH_TOKEN (a PAT with
read:user scope — the default GITHUB_TOKEN cannot read
contributionsCollection) and GH_LOGIN from the environment.

What's live vs. derived, so nothing here is a self-reported number:
  - contributions / commits / pull requests: contributionsCollection over
    the trailing 12 months (the widest window that API allows).
  - public repos: owned, public, non-fork repositories.
  - streaks, active days, peak week/day, weekly average: computed from the
    same contribution calendar.
  - languages: bytes per language summed across those repositories, as
    GitHub's linguist reports them (vendored and generated files are
    already excluded by linguist). Jupyter Notebook is left out because a
    notebook's bytes are mostly stored cell output, not code.

SVG notes (see also generate_atlas.py): GitHub strips <script> and inline
<style>, so all motion is SMIL. GitHub's image proxy (camo) strips internal
href/xlink:href fragment references, which silently collapses <use>/<mpath>
motion paths to a static point — so every animated element carries its own
inline path/values. Anything that must be readable starts visible (bars
grow via animations that freeze at their final size, grid cells are opaque
by default); only pac-man and the ghosts start hidden, so a renderer that
ignores SMIL shows a clean static graph instead of sprites in a corner.

Local preview without the API: set SIGNAL_FIXTURE to a saved GraphQL
response (the raw JSON of QUERY) and the script renders from that file.

Never-fail contract: this script always exits 0. Any problem is logged to
stderr and both output files are left exactly as they were — output is
only written after both SVGs have rendered successfully.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

LOGIN = os.environ.get("GH_LOGIN", "kartikeyajay2006")
TOKEN = os.environ.get("GH_TOKEN", "")
FIXTURE = os.environ.get("SIGNAL_FIXTURE", "")
DASH_PATH = os.environ.get("DASH_PATH", "assets/signal-dashboard.svg")
PACMAN_PATH = os.environ.get("PACMAN_PATH", "assets/pacman-contributions.svg")

W = 900
EASE = "0.42 0 0.58 1"
MONO = "Consolas, 'SF Mono', monospace"
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


def parse(payload):
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
        "total": cal["totalContributions"],
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
    <linearGradient id="sweep" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0"/><stop offset="50%" stop-color="#ffffff" stop-opacity="0.045"/>
      <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
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

    # periodic light sweep over the chart
    parts.append(f'<rect x="{cx0-80}" y="{top_y-10}" width="80" height="{base_y-top_y+10}" fill="url(#sweep)">'
                 f'<animateTransform attributeName="transform" type="translate" values="0,0;{cx1-cx0+80},0;{cx1-cx0+80},0" '
                 f'keyTimes="0;0.35;1" dur="9s" begin="2s" repeatCount="indefinite"/></rect>')

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


# ------------------------------------------------------------------ pac-man
PAC_OPEN = "M0,0 L5.3,-3.7 A6.5,6.5 0 1 0 5.3,3.7 Z"
PAC_SHUT = "M0,0 L6.5,-0.25 A6.5,6.5 0 1 0 6.5,0.25 Z"
GHOST_BODY = "M-6,6 L-6,-1 A6,6 0 0 1 6,-1 L6,6 L4,4 L2,6 L0,4 L-2,6 L-4,4 Z"
GHOSTS = [("#ff5c5c", 0.035), ("#f472b6", 0.06), ("#22d3ee", 0.085), ("#fb923c", 0.11)]


def build_pacman(d):
    weeks = d["weeks"]
    ncol = len(weeks)
    cell, gap = 12, 3
    step = cell + gap
    gx0 = 50
    gy0 = 64
    grid_w = ncol * step - gap
    H = gy0 + 7 * step + 58
    T = 30.0                      # full loop, seconds
    s, e = 0.8 / T, 25.0 / T      # pac-man move window within the loop
    n_steps = 7 * ncol - 1        # serpentine: every cell centre is one step apart

    def centre(col, row):
        return gx0 + col * step + cell / 2, gy0 + row * step + cell / 2

    def arrival(col, row):
        idx = row * ncol + (col if row % 2 == 0 else ncol - 1 - col)
        return s + (e - s) * idx / n_steps

    pts = []
    for row in range(7):
        a, b = (0, ncol - 1) if row % 2 == 0 else (ncol - 1, 0)
        pts.append(centre(a, row))
        pts.append(centre(b, row))
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
                 f'aria-labelledby="pacTitle pacDesc">')
    parts.append('<title id="pacTitle">Pac-man eats the last 12 months of contributions</title>')
    pdd = d["peak_day"]
    parts.append(f'<desc id="pacDesc">The real GitHub contribution grid for the last 12 months — {d["total"]} contributions '
                 f'over {d["active_days"]} active days, peak day {pdd["contributionCount"]} on {fmt_day(pdd["date"])} — '
                 f'with an animated pac-man eating it row by row while four ghosts give chase.</desc>')
    parts.append(f'<defs>{COMMON_DEFS}</defs>')
    synced = d["synced"]
    parts.append(frame(H, "SIGNAL // CONTRIB", f'{d["total"]:,} CONTRIBUTIONS · SYNCED {synced.strftime("%d %b %H:%M").upper()} UTC'))
    parts.append(f'<g transform="translate(166,24.5)"><path d="{PAC_OPEN}" fill="#facc15" transform="scale(0.72)"/></g>'
                 f'<circle cx="177" cy="24.5" r="1.2" fill="#facc15"/><circle cx="183" cy="24.5" r="1.2" fill="#facc15" opacity="0.7"/>'
                 f'<circle cx="189" cy="24.5" r="1.2" fill="#facc15" opacity="0.4"/>'
                 f'<text x="198" y="28" font-family="{MONO}" font-size="10" letter-spacing="1" fill="#facc15">'
                 f'PAC-MAN EATS THE LAST 12 MONTHS</text>')

    # weekday + month labels
    for row, lab in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        parts.append(f'<text x="{gx0-8}" y="{gy0 + row*step + 9.5}" text-anchor="end" font-family="{MONO}" '
                     f'font-size="8.5" fill="#555">{lab}</text>')
    prev_m, last_x = None, -99
    for col, w in enumerate(weeks):
        first = d_of(w["contributionDays"][0]["date"])
        if first.month != prev_m:
            prev_m = first.month
            mx = gx0 + col * step
            if mx - last_x >= 30 and col > 0:
                parts.append(f'<text x="{mx}" y="{gy0-8}" font-family="{MONO}" font-size="8.5" fill="#555">{first.strftime("%b")}</text>')
                last_x = mx

    # respawn wave in the last stretch of the loop, left to right
    def respawn_t(col):
        return 26.2 / T + (col / max(ncol - 1, 1)) * (2.6 / T)

    peak_cell = None
    for col, w in enumerate(weeks):
        for day in w["contributionDays"]:
            row = day["weekday"]
            x, y = gx0 + col * step, gy0 + row * step
            parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{DARK_BY_LEVEL[0]}"/>')
            t_eat, t_back = arrival(col, row), respawn_t(col)
            anim = (f'<animate attributeName="opacity" values="1;1;0;0;1;1" '
                    f'keyTimes="0;{t_eat:.4f};{t_eat+0.002:.4f};{t_back:.4f};{min(t_back+0.012, 0.999):.4f};1" '
                    f'dur="{T}s" repeatCount="indefinite"/>')
            lvl = level(day, d["max_day"])
            if lvl > 0:
                parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{DARK_BY_LEVEL[lvl]}">{anim}</rect>')
                if day["date"] == pdd["date"]:
                    peak_cell = (x + cell / 2, y + cell / 2, t_eat)
            else:
                cx, cy = x + cell / 2, y + cell / 2
                parts.append(f'<circle cx="{cx}" cy="{cy}" r="1.3" fill="#3a3a44">{anim}</circle>')

    # power pellet on the peak day
    if peak_cell:
        px, py, _ = peak_cell
        parts.append(f'<circle cx="{px}" cy="{py}" r="4" fill="none" stroke="#facc15" stroke-width="1.2">'
                     f'{breathe("r", "4;11;11", "1.6s")}{breathe("opacity", "0.9;0;0", "1.6s")}</circle>')

    # ghosts — trail pac-man along the same serpentine; turn blue for a few
    # seconds after he eats the power pellet
    t_pellet = peak_cell[2] if peak_cell else None
    for color, lag in GHOSTS:
        gs, ge = s + lag, min(e + lag, 0.985)
        vis = (f'<animate attributeName="opacity" values="0;0;1;1;0;0" '
               f'keyTimes="0;{gs:.4f};{gs+0.01:.4f};{ge-0.01:.4f};{ge:.4f};1" dur="{T}s" repeatCount="indefinite"/>')
        motion = (f'<animateMotion dur="{T}s" repeatCount="indefinite" path="{path}" calcMode="linear" '
                  f'keyPoints="0;0;1;1" keyTimes="0;{gs:.4f};{ge:.4f};1"/>')
        body_fill = ""
        if t_pellet is not None:
            f0, f1 = t_pellet, min(t_pellet + 5.0 / T, 0.97)
            flick = f1 - 1.2 / T
            body_fill = (f'<animate attributeName="fill" values="{color};{color};#3b5bff;#3b5bff;#e6e6ff;#3b5bff;{color};{color}" '
                         f'keyTimes="0;{f0:.4f};{f0+0.002:.4f};{flick:.4f};{flick+0.01:.4f};{flick+0.02:.4f};{f1:.4f};1" '
                         f'calcMode="discrete" dur="{T}s" repeatCount="indefinite"/>')
        parts.append(
            f'<g opacity="0">{vis}{motion}'
            f'<path d="{GHOST_BODY}" fill="{color}">{body_fill}</path>'
            f'<circle cx="-2.2" cy="-1.4" r="1.9" fill="#ffffff"/><circle cx="2.2" cy="-1.4" r="1.9" fill="#ffffff"/>'
            f'<circle cx="-1.6" cy="-1.2" r="0.95" fill="#1e3a8a"/><circle cx="2.8" cy="-1.2" r="0.95" fill="#1e3a8a"/>'
            f'</g>')

    # pac-man
    parts.append(
        f'<g opacity="0">'
        f'<animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes="0;{s-0.005:.4f};{s:.4f};{e:.4f};{e+0.01:.4f};1" '
        f'dur="{T}s" repeatCount="indefinite"/>'
        f'<animateMotion dur="{T}s" repeatCount="indefinite" path="{path}" rotate="auto" calcMode="linear" '
        f'keyPoints="0;0;1;1" keyTimes="0;{s:.4f};{e:.4f};1"/>'
        f'<path d="{PAC_OPEN}" fill="#facc15" filter="url(#glow)">'
        f'<animate attributeName="d" values="{PAC_OPEN};{PAC_SHUT};{PAC_OPEN}" dur="0.28s" repeatCount="indefinite"/></path>'
        f'</g>')

    # footer: legend + facts
    fy = gy0 + 7 * step + 26
    parts.append(f'<line x1="20" y1="{fy-14}" x2="{W-20}" y2="{fy-14}" stroke="#1a1a1f"/>')
    parts.append(f'<text x="{gx0}" y="{fy+4}" font-family="{MONO}" font-size="9" fill="#666">Less</text>')
    for i in range(5):
        parts.append(f'<rect x="{gx0 + 30 + i*14}" y="{fy-6}" width="11" height="11" rx="2.5" fill="{DARK_BY_LEVEL[i]}"/>')
    parts.append(f'<text x="{gx0 + 30 + 5*14 + 4}" y="{fy+4}" font-family="{MONO}" font-size="9" fill="#666">More</text>')
    facts = (f'<tspan fill="#facc15">●</tspan> power pellet = peak day · {pdd["contributionCount"]} on {fmt_day(pdd["date"])}'
             f'   <tspan fill="#555">|</tspan>   {d["active_days"]} active days'
             f'   <tspan fill="#555">|</tspan>   longest streak {d["longest_streak"]} days')
    parts.append(f'<text x="{gx0 + grid_w}" y="{fy+4}" text-anchor="end" font-family="{MONO}" font-size="9" fill="#888">{facts}</text>')

    parts.append('</svg>')
    return "\n".join(parts)


def main():
    try:
        data = parse(fetch())
        dash = build_dashboard(data)
        pac = build_pacman(data)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: signal generation failed, leaving existing files untouched: {e}", file=sys.stderr)
        return 0

    for path, svg in ((DASH_PATH, dash), (PACMAN_PATH, pac)):
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
