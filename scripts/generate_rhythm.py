#!/usr/bin/env python3
"""Generate assets/build-rhythm.svg — the section 08 "Build Rhythm" board:
when the code actually gets written.

Built from every commit GH_LOGIN authored on the default branch of each
owned, public, non-fork repository, bucketed in IST:

  - a 24-hour radar clock: 7 heat rings (Mon inside -> Sun outside) x 24
    hour sectors, an outer radial histogram of commits per hour, a sweep
    that lights up each hour's real cells as it passes, and a ping on the
    cell holding the latest commit.
  - CHRONOTYPE, derived from the same data, never self-declared:
    NIGHT OWL if >= 30% of commits land 22:00-05:00, EARLY BIRD if >= 30%
    land 05:00-11:00, otherwise DAY SHIFT.
  - after-midnight share, peak weekday, weekend share, active days.
  - the deepest session: consecutive commits no more than 90 minutes apart,
    longest span wins.
  - the newest commit in each of the three most recently touched repos,
    outside this profile repo (merges and [skip ci] commits skipped).

Stdlib-only (no pip install needed in CI). Reads GH_TOKEN (the same
GH_CONTRIB_PAT used by generate_signal.py) and GH_LOGIN from the environment.

SVG notes (see generate_signal.py): GitHub strips <script> and inline <style>,
so all motion is SMIL, and camo strips internal href references, so every
animated element carries its own inline values. Anything readable starts
visible; the sweep flashes start at opacity 0, so a renderer that ignores
SMIL shows a clean static clock.

Local preview without the API: set RHYTHM_FIXTURE to a JSON list of
{"repo", "at", "msg"} commits and the script renders from that file. Set
RHYTHM_DUMP to a path to save the fetched commits in that same format.

Never-fail contract: this script always exits 0. Any problem is logged to
stderr and the output file is left exactly as it was.
"""
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

LOGIN = os.environ.get("GH_LOGIN", "kartikeyajay2006")
TOKEN = os.environ.get("GH_TOKEN", "")
FIXTURE = os.environ.get("RHYTHM_FIXTURE", "")
DUMP = os.environ.get("RHYTHM_DUMP", "")
OUT_PATH = os.environ.get("OUT_PATH", "assets/build-rhythm.svg")

TZ = timezone(timedelta(hours=5, minutes=30))
TZ_NAME = "IST"
SESSION_GAP = timedelta(minutes=90)
MAX_PAGES_PER_REPO = 20
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

W, H = 900, 548
EASE = "0.42 0 0.58 1"
MONO = "Consolas, 'SF Mono', monospace"
SANS = "Helvetica, Arial, sans-serif"

# clock geometry — angles are degrees clockwise from 12 o'clock
CX, CY = 262, 290
R0 = 60                      # inner hole
RW = 16.5                    # one weekday ring
R1 = R0 + 7 * RW             # outer edge of the heat rings
RH0 = R1 + 7                 # histogram base
RH_LEN = 34                  # longest histogram bar
R_BAND = RH0 + RH_LEN + 4    # day / night band
R_LABEL = R_BAND + 15.5      # hour labels
SWEEP = 9                    # seconds per revolution

# one hue, dark -> light: magnitude reads as brightness on the dark card
RAMP = [(0.0, (0x2a, 0x1d, 0x3f)), (0.55, (0x8b, 0x5c, 0xf6)),
        (0.85, (0xc0, 0x84, 0xfc)), (1.0, (0xf3, 0xe8, 0xff))]
EMPTY = "#141419"

HISTORY = ("history(first: 100, after: $after, author: {id: $id}) "
           "{ pageInfo { hasNextPage endCursor } nodes { authoredDate messageHeadline } }")
USER_Q = "query($login: String!) { user(login: $login) { id } }"
REPOS_Q = """
query($login: String!, $id: ID!, $cursor: String, $after: String) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 10, after: $cursor,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes { name defaultBranchRef { target { ... on Commit { %s } } } }
    }
  }
}""" % HISTORY
MORE_Q = """
query($owner: String!, $name: String!, $id: ID!, $after: String) {
  repository(owner: $owner, name: $name) { defaultBranchRef { target { ... on Commit { %s } } } }
}""" % HISTORY


class FetchError(Exception):
    pass


# ------------------------------------------------------------------ data
def gql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    last_err = None
    for attempt in range(3):
        req = urllib.request.Request(
            "https://api.github.com/graphql", data=body, method="POST",
            headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json",
                     "User-Agent": f"{LOGIN}-rhythm-generator"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("errors"):
                raise FetchError(f"GraphQL returned errors: {payload['errors']}")
            return payload["data"]
        except urllib.error.HTTPError as e:
            last_err = FetchError(f"HTTP {e.code} from GitHub GraphQL: {e.read().decode('utf-8', 'replace')[:300]}")
        except urllib.error.URLError as e:
            last_err = FetchError(f"network failure reaching GitHub GraphQL: {e}")
        except (TimeoutError, json.JSONDecodeError, KeyError) as e:
            last_err = FetchError(f"bad response from GitHub GraphQL: {e}")
        except FetchError as e:
            last_err = e
        print(f"WARNING: attempt {attempt + 1}/3 failed: {last_err}", file=sys.stderr)
        if attempt < 2:
            time.sleep(2 * (attempt + 1))
    raise last_err


def _history(repo_node):
    ref = repo_node.get("defaultBranchRef") if repo_node else None
    return ((ref or {}).get("target") or {}).get("history")


def fetch():
    if FIXTURE:
        with open(FIXTURE, encoding="utf-8") as f:
            return [{"repo": c["repo"], "at": parse_ts(c["at"]), "msg": c["msg"]} for c in json.load(f)]
    if not TOKEN:
        raise FetchError("GH_TOKEN is not set. Add a PAT as the GH_CONTRIB_PAT repo secret.")

    user = gql(USER_Q, {"login": LOGIN}).get("user")
    if not user:
        raise FetchError(f"user '{LOGIN}' not found")
    uid = user["id"]

    commits, cursor = [], None
    while True:
        repos = gql(REPOS_Q, {"login": LOGIN, "id": uid, "cursor": cursor})["user"]["repositories"]
        for node in repos["nodes"]:
            hist = _history(node)
            pages = 1
            while hist:
                commits += [{"repo": node["name"], "at": parse_ts(c["authoredDate"]), "msg": c["messageHeadline"]}
                            for c in hist["nodes"]]
                if not hist["pageInfo"]["hasNextPage"] or pages >= MAX_PAGES_PER_REPO:
                    break
                more = gql(MORE_Q, {"owner": LOGIN, "name": node["name"], "id": uid,
                                    "after": hist["pageInfo"]["endCursor"]})
                hist = _history(more.get("repository"))
                pages += 1
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]

    if DUMP:
        with open(DUMP, "w", encoding="utf-8") as f:
            json.dump([{"repo": c["repo"], "at": c["at"].strftime("%Y-%m-%dT%H:%M:%SZ"), "msg": c["msg"]}
                       for c in commits], f, indent=1)
    return commits


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def analyse(commits):
    if len(commits) < 20:
        raise FetchError(f"only {len(commits)} commits came back — too few to draw a rhythm")
    local = sorted((c["at"].astimezone(TZ), c["repo"], c["msg"]) for c in commits)
    n = len(local)

    grid = [[0] * 24 for _ in range(7)]
    for t, _, _ in local:
        grid[t.weekday()][t.hour] += 1
    hours = [sum(grid[d][h] for d in range(7)) for h in range(24)]
    days = [sum(row) for row in grid]

    def share(hs):
        return sum(hours[h] for h in hs) / n

    night, morning = share([22, 23, 0, 1, 2, 3, 4]), share(range(5, 11))
    if night >= 0.30:
        chrono = ("NIGHT OWL", f"{pct(night)} of commits land between 22:00 and 05:00 {TZ_NAME}")
    elif morning >= 0.30:
        chrono = ("EARLY BIRD", f"{pct(morning)} of commits land between 05:00 and 11:00 {TZ_NAME}")
    else:
        chrono = ("DAY SHIFT", f"{pct(1 - night - morning)} of commits land between 11:00 and 22:00 {TZ_NAME}")

    sessions, cur = [], [local[0]]
    for prev, c in zip(local, local[1:]):
        if c[0] - prev[0] <= SESSION_GAP:
            cur.append(c)
        else:
            sessions.append(cur)
            cur = [c]
    sessions.append(cur)
    deep = max(sessions, key=lambda s: (s[-1][0] - s[0][0], len(s)))

    feed, seen = [], set()
    for t, repo, msg in reversed(local):
        if repo == LOGIN or repo in seen or msg.startswith("Merge ") or "[skip ci]" in msg:
            continue
        seen.add(repo)
        feed.append((t, repo, msg))
        if len(feed) == 3:
            break

    peak_hour = max(range(24), key=lambda h: hours[h])
    peak_day = max(range(7), key=lambda d: days[d])
    return {
        "n": n,
        "repos": len({r for _, r, _ in local}),
        "grid": grid,
        "hours": hours,
        "days": days,
        "chrono": chrono,
        "after_midnight": share(range(0, 5)),
        "weekend": (days[5] + days[6]) / n,
        "peak_hour": peak_hour,
        "peak_day": peak_day,
        "peak_cell": max(((d, h) for d in range(7) for h in range(24)), key=lambda dh: grid[dh[0]][dh[1]]),
        "active_days": len({t.date() for t, _, _ in local}),
        "since": local[0][0],
        "deep": deep,
        "deep_repo": Counter(r for _, r, _ in deep).most_common(1)[0][0],
        "feed": feed,
        "synced": datetime.now(TZ),
    }


# ------------------------------------------------------------------ helpers
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def clean(s, limit):
    s = "".join(ch for ch in str(s) if ch.isprintable() and ord(ch) <= 0xFFFF).strip()
    return s if len(s) <= limit else s[:limit - 1].rstrip() + "…"


def pct(x):
    return f"{x * 100:.0f}%" if x >= 0.1 else f"{x * 100:.1f}%"


def ramp(t):
    t = max(0.0, min(1.0, t))
    for (t0, c0), (t1, c1) in zip(RAMP, RAMP[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            return "#" + "".join(f"{round(a + (b - a) * k):02x}" for a, b in zip(c0, c1))
    return "#f3e8ff"


def polar(r, a):
    rad = math.radians(a)
    return CX + r * math.sin(rad), CY - r * math.cos(rad)


def sector(r0, r1, a0, a1):
    large = 1 if a1 - a0 > 180 else 0
    (x0, y0), (x1, y1) = polar(r1, a0), polar(r1, a1)
    (x2, y2), (x3, y3) = polar(r0, a1), polar(r0, a0)
    return (f"M{x0:.1f},{y0:.1f}A{r1:.1f},{r1:.1f} 0 {large} 1 {x1:.1f},{y1:.1f}"
            f"L{x2:.1f},{y2:.1f}A{r0:.1f},{r0:.1f} 0 {large} 0 {x3:.1f},{y3:.1f}Z")


def arc(r, a0, a1):
    large = 1 if a1 - a0 > 180 else 0
    (x0, y0), (x1, y1) = polar(r, a0), polar(r, a1)
    return f"M{x0:.1f},{y0:.1f}A{r:.1f},{r:.1f} 0 {large} 1 {x1:.1f},{y1:.1f}"


def breathe(attr, values, dur, begin="0s"):
    n = len(values.split(";"))
    kt = ";".join(f"{i / (n - 1):.3f}" for i in range(n))
    return (f'<animate attributeName="{attr}" values="{values}" keyTimes="{kt}" calcMode="spline" '
            f'keySplines="{";".join([EASE] * (n - 1))}" dur="{dur}" begin="{begin}" repeatCount="indefinite"/>')


def reveal(delay, dur=0.5):
    k = delay / (delay + dur)
    return (f'<animate attributeName="opacity" values="0;0;1" keyTimes="0;{k:.3f};1" dur="{delay + dur:.2f}s" '
            f'fill="freeze" calcMode="spline" keySplines="{EASE};{EASE}"/>')


def card(x, y, w, h, accent=None):
    out = f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{h}" rx="10" fill="#101014" stroke="#1f1f24"/>'
    if accent:
        out += f'<rect x="{x + 1:.1f}" y="{y + 12}" width="2.5" height="{h - 24}" rx="1.2" fill="{accent}"/>'
    return out


def label(x, y, text, fill="#8a8a8a", anchor="start", size=9):
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{MONO}" font-size="{size}" '
            f'letter-spacing="1.2" fill="{fill}">{esc(text)}</text>')


def fmt_dur(td):
    mins = int(td.total_seconds() // 60)
    return f"{mins // 60}h {mins % 60:02d}m" if mins >= 60 else f"{mins}m"


# ------------------------------------------------------------------ render
def build(d):
    grid, hours = d["grid"], d["hours"]
    max_cell = max(max(row) for row in grid) or 1
    max_hour = max(hours) or 1
    synced = d["synced"]
    chrono_name, chrono_why = d["chrono"]
    ph = d["peak_hour"]
    deep = d["deep"]
    p = []

    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-labelledby="rhyTitle rhyDesc">')
    p.append('<title id="rhyTitle">Build rhythm — when the code actually ships</title>')
    feed_txt = "; ".join(f"{r}: {m} ({t.strftime('%d %b %H:%M')} {TZ_NAME})" for t, r, m in d["feed"])
    p.append(f'<desc id="rhyDesc">{d["n"]} commits across {d["repos"]} public repositories, bucketed by hour and '
             f'weekday in {TZ_NAME}. Chronotype {chrono_name}: {esc(chrono_why)}. Peak hour {ph:02d}:00 with '
             f'{hours[ph]} commits; peak day {DAYS[d["peak_day"]]}; {pct(d["after_midnight"])} after midnight; '
             f'{pct(d["weekend"])} on weekends; {d["active_days"]} active days since {d["since"].strftime("%b %Y")}. '
             f'Deepest session {fmt_dur(deep[-1][0] - deep[0][0])} with {len(deep)} commits in {esc(d["deep_repo"])}. '
             f'Latest: {esc(feed_txt)}. Synced {synced.strftime("%Y-%m-%d %H:%M")} {TZ_NAME}.</desc>')
    p.append(f'''<defs>
    <pattern id="dotgrid" width="28" height="28" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#141414"/></pattern>
    <filter id="glow" x="-250%" y="-250%" width="600%" height="600%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="bigGlow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="9"/></filter>
    <radialGradient id="core" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#8b5cf6" stop-opacity="0.28"/><stop offset="100%" stop-color="#8b5cf6" stop-opacity="0"/>
    </radialGradient>
  </defs>''')

    # ---- frame
    p.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="#0a0a0a" stroke="#1f1f1f"/>')
    p.append(f'<rect x="14" y="14" width="{W - 28}" height="{H - 28}" fill="url(#dotgrid)"/>')
    p.append(label(20, 28, "RHYTHM // LIVE", "#555", size=10))
    p.append(f'<circle cx="{W - 24}" cy="24.5" r="3" fill="#22c55e" filter="url(#glow)">{breathe("opacity", "1;0.3;1", "1.8s")}</circle>')
    p.append(label(W - 34, 28, f'{d["n"]:,} COMMITS · {d["repos"]} REPOS · SYNCED '
                               f'{synced.strftime("%d %b %H:%M").upper()} {TZ_NAME}', "#555", "end", 10))

    # ---- clock: backdrop, guides, day/night band, hour labels
    p.append(f'<circle cx="{CX}" cy="{CY}" r="{R_BAND + 6}" fill="#0c0c10" stroke="#18181e"/>')
    p.append(f'<circle cx="{CX}" cy="{CY}" r="{R1 + 30}" fill="url(#core)" opacity="0.5"/>')
    for rr in (RH0 + RH_LEN / 2, RH0 + RH_LEN):
        p.append(f'<circle cx="{CX}" cy="{CY}" r="{rr:.1f}" fill="none" stroke="#17171d" stroke-dasharray="2 4"/>')
    for h in range(0, 24, 3):
        (x0, y0), (x1, y1) = polar(RH0 - 2, h * 15), polar(RH0 + RH_LEN, h * 15)
        p.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="#1b1b22"/>')
    p.append(f'<path d="{arc(R_BAND, 270, 450)}" fill="none" stroke="#818cf8" stroke-width="2" stroke-linecap="round" opacity="0.55"/>')
    p.append(f'<path d="{arc(R_BAND, 90, 270)}" fill="none" stroke="#f5a623" stroke-width="2" stroke-linecap="round" opacity="0.45"/>')
    for h in range(24):
        x, y = polar(R_LABEL, h * 15)
        if h % 3:
            p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1" fill="#2c2c34"/>')
            continue
        fill = "#e9d5ff" if h == ph else ("#9a9a9a" if h in (0, 12) else "#666")
        p.append(f'<text x="{x:.1f}" y="{y + 3.2:.1f}" text-anchor="middle" font-family="{MONO}" font-size="9" '
                 f'font-weight="{700 if h == ph else 400}" fill="{fill}">{h:02d}</text>')
    for word, a, color in (("NIGHT", 337.5, "#818cf8"), ("DAY", 157.5, "#f5a623")):
        x, y = polar(R_LABEL, a)
        p.append(f'<text x="{x:.1f}" y="{y + 3:.1f}" text-anchor="middle" font-family="{MONO}" font-size="7.5" '
                 f'letter-spacing="1.5" fill="{color}" opacity="0.8">{word}</text>')

    # ---- heat rings, revealed clockwise
    for h in range(24):
        a0, a1 = h * 15 + 0.6, h * 15 + 15 - 0.6
        cells = []
        for day in range(7):
            c = grid[day][h]
            r0, r1 = R0 + day * RW + 0.8, R0 + (day + 1) * RW - 0.8
            fill = ramp((c / max_cell) ** 0.55) if c else EMPTY
            cells.append(f'<path d="{sector(r0, r1, a0, a1)}" fill="{fill}"/>')
        p.append(f'<g>{reveal(0.1 + h * 0.055)}{"".join(cells)}</g>')

    # ---- radial histogram of commits per hour
    for h in range(24):
        v = hours[h]
        if not v:
            continue
        t = v / max_hour
        a0, a1 = h * 15 + 4, h * 15 + 11
        full = sector(RH0, RH0 + max(2.0, RH_LEN * t), a0, a1)
        start = sector(RH0, RH0 + 0.1, a0, a1)
        delay = 1.0 + h * 0.03
        k = delay / (delay + 0.7)
        extra = ' filter="url(#glow)"' if h == ph else ""
        p.append(f'<path d="{full}" fill="{ramp(0.2 + 0.7 * t)}"{extra}>'
                 f'<animate attributeName="d" values="{start};{start};{full}" keyTimes="0;{k:.3f};1" '
                 f'dur="{delay + 0.7:.2f}s" fill="freeze" calcMode="spline" keySplines="{EASE};{EASE}"/></path>')

    # ---- sweep: each hour's real cells flash as the beam passes them
    for h in range(24):
        a0, a1 = h * 15 + 0.6, h * 15 + 15 - 0.6
        flashes = []
        for day in range(7):
            c = grid[day][h]
            if c:
                r0, r1 = R0 + day * RW + 0.8, R0 + (day + 1) * RW - 0.8
                flashes.append(f'<path d="{sector(r0, r1, a0, a1)}" fill="#f5eaff" '
                               f'fill-opacity="{0.12 + 0.6 * (c / max_cell) ** 0.55:.2f}"/>')
        if flashes:
            p.append(f'<g opacity="0"><animate attributeName="opacity" values="0;1;0;0" keyTimes="0;0.03;0.16;1" '
                     f'dur="{SWEEP}s" begin="{SWEEP * h / 24:.3f}s" repeatCount="indefinite"/>{"".join(flashes)}</g>')
    beam = []
    for i in range(12):
        beam.append(f'<path d="{sector(R0, R_BAND - 3, -2.5 * (i + 1), -2.5 * i)}" fill="#a78bfa" '
                    f'fill-opacity="{0.16 * (1 - i / 12):.3f}"/>')
    (bx0, by0), (bx1, by1) = polar(R0, 0), polar(R_BAND - 3, 0)
    beam.append(f'<line x1="{bx0:.1f}" y1="{by0:.1f}" x2="{bx1:.1f}" y2="{by1:.1f}" stroke="#ddd6fe" stroke-width="1.2" opacity="0.8"/>')
    beam.append(f'<circle cx="{bx1:.1f}" cy="{by1:.1f}" r="2.4" fill="#f5f3ff" filter="url(#glow)"/>')
    p.append(f'<g><animateTransform attributeName="transform" type="rotate" from="0 {CX} {CY}" to="360 {CX} {CY}" '
             f'dur="{SWEEP}s" repeatCount="indefinite"/>{"".join(beam)}</g>')

    # ---- peak cell + latest-commit ping
    pd, phr = d["peak_cell"]
    p.append(f'<path d="{sector(R0 + pd * RW + 0.8, R0 + (pd + 1) * RW - 0.8, phr * 15 + 0.6, phr * 15 + 14.4)}" '
             f'fill="none" stroke="#f5f3ff" stroke-width="1.3" filter="url(#glow)"/>')
    if d["feed"]:
        lt = d["feed"][0][0]
        lx, ly = polar(R0 + (lt.weekday() + 0.5) * RW, lt.hour * 15 + 7.5)
        p.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3" fill="#22c55e" stroke="#0a0a0a" stroke-width="1" filter="url(#glow)"/>')
        p.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3" fill="none" stroke="#22c55e" stroke-width="1.2">'
                 f'{breathe("r", "3;13;13", "2s")}{breathe("opacity", "0.9;0;0", "2s")}</circle>')

    # ---- core
    p.append(f'<circle cx="{CX}" cy="{CY}" r="{R0 - 5}" fill="#0a0a0d" stroke="#2a2140"/>')
    p.append(f'<circle cx="{CX}" cy="{CY}" r="{R0 - 5}" fill="none" stroke="#a78bfa" stroke-width="1" opacity="0.4">'
             f'{breathe("opacity", "0.5;0.1;0.5", "3s")}</circle>')
    p.append(label(CX, CY - 19, "PEAK HOUR", "#8a8a8a", "middle", 7.5))
    p.append(f'<text x="{CX}" y="{CY + 7}" text-anchor="middle" font-family="{SANS}" font-size="24" font-weight="700" '
             f'fill="#f2f2f2">{ph:02d}:00</text>')
    p.append(label(CX, CY + 23, f"{hours[ph]} COMMITS", "#8a8a8a", "middle", 7.5))

    # ---- clock legend (corners)
    p.append(label(22, 52, "RING = WEEKDAY", "#666", size=8))
    p.append(label(22, 64, "Mon in → Sun out", "#555", size=8))
    p.append(label(22, 76, f"hours in {TZ_NAME}", "#555", size=8))
    p.append(label(22, 510, "BARS = COMMITS / HOUR", "#666", size=8))
    p.append(label(22, 526, "fewer", "#555", size=8))
    for i in range(6):
        p.append(f'<rect x="{56 + i * 13}" y="{518}" width="11" height="10" rx="2" '
                 f'fill="{EMPTY if i == 0 else ramp(i / 5)}"/>')
    p.append(label(136, 526, "more", "#555", size=8))
    p.append(f'<circle cx="412" cy="508" r="3" fill="#22c55e"/>')
    p.append(label(422, 511, "latest commit", "#555", size=8))
    p.append(f'<rect x="408.5" y="519.5" width="8" height="8" rx="1" fill="none" stroke="#f5f3ff" stroke-width="1.2"/>')
    p.append(label(422, 527, "busiest slot", "#555", size=8))

    # ---- readout panel
    x0, pw = 522, W - 20 - 522

    # chronotype
    cy0 = 44
    p.append(card(x0, cy0, pw, 84, "#a78bfa"))
    p.append(label(x0 + 16, cy0 + 21, "CHRONOTYPE · DERIVED FROM COMMITS"))
    p.append(f'<text x="{x0 + 15}" y="{cy0 + 52}" font-family="{SANS}" font-size="27" font-weight="700" '
             f'letter-spacing="0.5" fill="#f2f2f2">{esc(chrono_name)}</text>')
    p.append(f'<text x="{x0 + 16}" y="{cy0 + 70}" font-family="{MONO}" font-size="9" fill="#9a9a9a">{esc(chrono_why)}</text>')
    ix, iy = x0 + pw - 40, cy0 + 38
    if chrono_name == "NIGHT OWL":
        p.append(f'<circle cx="{ix}" cy="{iy}" r="22" fill="#a78bfa" opacity="0.35" filter="url(#bigGlow)"/>')
        p.append(f'<circle cx="{ix}" cy="{iy}" r="14" fill="#ede9fe"/>')
        p.append(f'<circle cx="{ix + 7}" cy="{iy - 5}" r="12.5" fill="#101014"/>')
        for sx, sy, dur in ((-18, -14, "2.2s"), (12, 14, "3.1s"), (-22, 10, "2.7s")):
            p.append(f'<circle cx="{ix + sx}" cy="{iy + sy}" r="1.2" fill="#ede9fe">{breathe("opacity", "1;0.15;1", dur)}</circle>')
    else:
        p.append(f'<circle cx="{ix}" cy="{iy}" r="22" fill="#f5a623" opacity="0.35" filter="url(#bigGlow)"/>')
        p.append(f'<circle cx="{ix}" cy="{iy}" r="9" fill="#fcd34d"/>')
        for k in range(8):
            (ax, ay), (bx, by) = [(ix + r * math.sin(math.radians(k * 45)), iy - r * math.cos(math.radians(k * 45)))
                                  for r in (13, 18)]
            p.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="#fcd34d" stroke-width="2" stroke-linecap="round"/>')

    # stat tiles
    tiles = [
        ("AFTER MIDNIGHT", pct(d["after_midnight"]), f"00:00–05:00 {TZ_NAME}", "#818cf8"),
        ("PEAK DAY", DAYS[d["peak_day"]], f'{d["days"][d["peak_day"]]} commits', "#22d3ee"),
        ("WEEKEND", pct(d["weekend"]), "Sat + Sun share", "#ec4899"),
        ("ACTIVE DAYS", f'{d["active_days"]}', f'since {d["since"].strftime("%b %Y")}', "#22c55e"),
    ]
    tw, th, gap = (pw - 10) / 2, 62, 10
    for i, (lab, val, sub, c) in enumerate(tiles):
        tx, ty = x0 + (i % 2) * (tw + gap), 138 + (i // 2) * (th + gap)
        p.append(card(tx, ty, tw, th, c))
        p.append(label(f"{tx + 16:.1f}", ty + 18, lab, size=8.5))
        p.append(f'<text x="{tx + 15:.1f}" y="{ty + 40}" font-family="{SANS}" font-size="19" font-weight="700" '
                 f'fill="#f2f2f2">{esc(val)}</text>')
        p.append(f'<text x="{tx + 16:.1f}" y="{ty + 54}" font-family="{MONO}" font-size="8.5" '
                 f'fill="#8a8a8a">{esc(sub)}</text>')

    # deepest session, replayed along its own timeline
    sy0 = 282
    span = deep[-1][0] - deep[0][0]
    p.append(card(x0, sy0, pw, 88, "#f5a623"))
    p.append(label(x0 + 16, sy0 + 21, "DEEPEST SESSION"))
    p.append(label(x0 + pw - 14, sy0 + 21, "gaps ≤ 90 min", "#555", "end", 8.5))
    p.append(f'<text x="{x0 + 15}" y="{sy0 + 46}" font-family="{SANS}" font-size="21" font-weight="700" fill="#f2f2f2">'
             f'{fmt_dur(span)}<tspan font-size="11" font-weight="400" fill="#8a8a8a">  ·  {len(deep)} commits · '
             f'{esc(clean(d["deep_repo"], 26))}</tspan></text>')
    t_a, t_b = deep[0][0], deep[-1][0]
    p.append(f'<text x="{x0 + 16}" y="{sy0 + 62}" font-family="{MONO}" font-size="9" fill="#9a9a9a">'
             f'{t_a.strftime("%a %d %b %Y").replace(" 0", " ")} · {t_a.strftime("%H:%M")} → {t_b.strftime("%H:%M")} {TZ_NAME}</text>')
    lx0, lx1, ly = x0 + 16, x0 + pw - 16, sy0 + 74
    p.append(f'<line x1="{lx0}" y1="{ly}" x2="{lx1}" y2="{ly}" stroke="#24242c" stroke-width="2" stroke-linecap="round"/>')
    secs = max(span.total_seconds(), 1)
    for t, _, _ in deep:
        tx = lx0 + (lx1 - lx0) * (t - t_a).total_seconds() / secs
        p.append(f'<line x1="{tx:.1f}" y1="{ly - 5}" x2="{tx:.1f}" y2="{ly + 5}" stroke="#f5a623" stroke-width="1.4" opacity="0.8"/>')
    p.append(f'<circle cx="{lx0}" cy="{ly}" r="3.2" fill="#fde68a" filter="url(#glow)">'
             f'<animate attributeName="cx" values="{lx0};{lx1}" dur="4s" repeatCount="indefinite"/>'
             f'{breathe("opacity", "0;1;1;0", "4s")}</circle>')

    # latest ships
    fy0 = 380
    p.append(card(x0, fy0, pw, H - 20 - fy0, "#22c55e"))
    p.append(label(x0 + 16, fy0 + 21, "LATEST SHIPS"))
    p.append(f'<text x="{x0 + pw - 14}" y="{fy0 + 21}" text-anchor="end" font-family="{MONO}" font-size="8.5" fill="#555">'
             f'newest commit per repo <tspan fill="#22c55e">▌{breathe("opacity", "1;0;1", "1.1s")}</tspan></text>')
    for i, (t, repo, msg) in enumerate(d["feed"]):
        ey = fy0 + 44 + i * 36
        dot = '#22c55e" filter="url(#glow)' if i == 0 else "#3a3a44"
        p.append(f'<g>{reveal(0.5 + i * 0.25)}'
                 f'<circle cx="{x0 + 19}" cy="{ey - 3.5}" r="2.6" fill="{dot}"/>'
                 f'<text x="{x0 + 29}" y="{ey}" font-family="{MONO}" font-size="9.5" font-weight="700" fill="#e0e0e0">'
                 f'{esc(clean(repo, 36))}</text>'
                 f'<text x="{x0 + pw - 14}" y="{ey}" text-anchor="end" font-family="{MONO}" font-size="8.5" fill="#777">'
                 f'{t.strftime("%d %b · %H:%M").lstrip("0")} {TZ_NAME}</text>'
                 f'<text x="{x0 + 29}" y="{ey + 15}" font-family="{SANS}" font-size="11" fill="#a8a8a8">'
                 f'{esc(clean(msg, 54))}</text></g>')

    p.append("</svg>")
    return "\n".join(p)


def main():
    try:
        svg = build(analyse(fetch()))
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: rhythm generation failed, leaving the existing file untouched: {e}", file=sys.stderr)
        return 0
    try:
        os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"Wrote {OUT_PATH}")
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: failed to write {OUT_PATH}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
