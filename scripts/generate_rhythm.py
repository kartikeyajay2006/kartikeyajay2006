#!/usr/bin/env python3
"""Generate assets/build-rhythm.svg — the section 08 "Build Rhythm" board:
when the code actually gets written.

Built from every commit GH_LOGIN authored on the default branch of each
owned, public, non-fork repository, bucketed in IST:

  - a 24-hour commit clock: one rod per hour, its length the number of
    commits made in that hour, drawn over a sky that is night above the
    horizon (18:00 -> 06:00, through midnight) and day below it. A moon,
    which turns into a sun at dawn, crosses that sky once every 24 seconds
    and lights each hour's rod, and the same hour's column on the week grid,
    as it passes.
  - CHRONOTYPE, derived from the same data, never self-declared:
    NIGHT OWL if >= 30% of commits land 22:00-05:00, EARLY BIRD if >= 30%
    land 05:00-11:00, otherwise DAY SHIFT.
  - after-midnight share, the focus window (busiest three straight hours),
    weekend share and active days.
  - the deepest session: consecutive commits no more than 90 minutes apart,
    longest span wins, replayed on a track tinted by the hours it crossed.
  - a week x hour punch card: one dot per weekday-hour slot with its area
    proportional to commits, weekday totals beside it, and the busiest slot
    and the newest commit marked on it.

Stdlib-only (no pip install needed in CI). Reads GH_TOKEN (the same
GH_CONTRIB_PAT used by generate_signal.py) and GH_LOGIN from the environment.

SVG notes (see generate_signal.py): GitHub strips <script> and inline <style>,
so all motion is SMIL, and every animated element carries its own inline
values and paths (no <use>/<mpath>). Anything readable starts visible: rods
and dots grow from animations that freeze at their real size, so a renderer
that ignores SMIL shows the finished chart with the moon parked at midnight.

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
# Pin "now" for reproducible local previews (ISO timestamp); CI leaves it unset.
NOW = os.environ.get("RHYTHM_NOW", "")

TZ = timezone(timedelta(hours=5, minutes=30))
TZ_NAME = "IST"
SESSION_GAP = timedelta(minutes=90)
MAX_PAGES_PER_REPO = 20
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

W, H = 900, 702
EASE = "0.42 0 0.58 1"
OUT_EASE = "0.16 1 0.3 1"
MONO = "ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

INK = "#f4f4f5"      # primary text
INK2 = "#a1a1aa"     # secondary text
INK3 = "#71717a"     # labels
INK4 = "#52525b"     # quiet labels
LINE = "#1f1f25"     # hairlines

# ---- clock geometry (angles are degrees clockwise from 12 o'clock; hour h sits at h * 15)
CX, CY = 222, 222
R_HOLE = 41          # centre readout
R_BASE = 53          # where rods start
R_MAX = 128          # longest rod's end
R_ORB = 142          # path of the moon / sun
R_SKY = 156          # edge of the sky disc
R_LABEL = 168        # hour numerals
ROD_W = 8.5

ORBIT = 24           # seconds for one full day; one second per hour
ORBIT_BEGIN = 2.2    # let the rods finish growing first

# ---- week grid geometry
PC_X0, PC_DX = 82, 28.5      # first column centre, column pitch
PC_Y0, PC_DY = 482, 24.5     # first row centre, row pitch
DOT_MAX = 10.2               # radius of the busiest slot

# Time-of-day palette: night violet -> dawn rose -> day amber -> dusk rose -> night.
HOUR_STOPS = [(0, (0xa7, 0x8b, 0xfa)), (3, (0x81, 0x8c, 0xf8)), (5, (0x93, 0x9b, 0xf9)),
              (6.5, (0xf4, 0x72, 0xb6)), (8.5, (0xfb, 0x92, 0x3c)), (11, (0xfb, 0xbf, 0x24)),
              (15, (0xfb, 0xbf, 0x24)), (17, (0xfb, 0x92, 0x3c)), (18.5, (0xfb, 0x71, 0x85)),
              (20.5, (0xe8, 0x79, 0xf9)), (22.5, (0xc0, 0x84, 0xfc)), (24, (0xa7, 0x8b, 0xfa))]

# Long repository names read better as the product they ship.
DISPLAY = {
    "Multimodal-Data-Management-Pipeline-for-RAG-Ready-Systems": "Multimodal Evidence Console",
    "Sovereign-On_Premise-Agentic-AI-Workbench": "AEGIS",
    "Agent_that_act-Hackathon": "ForgeSRE",
    "Wispr_goa_task": "EraseOps",
    "multi-layer_orchestation": "Chakraview",
    "agent--flow": "AgentFlow OS",
    "Multimodel-governance-B2A": "B2A Governance",
    "RL-model-Negotiation": "DealForge",
    "2nd-Year-MERN-P_S": "ShopKart",
    "codecrafters-shell-java": "jsh",
    "Cardano-BlockPhantom": "BlockPhantom",
    "AI-Businesses": "AI Merchant Copilot",
    "AI-Video-Editor": "AI Video Studio",
    "jky-terminal": "JKY Terminal",
    "Kovidam-Skill-Graph": "Kovidam Skill Graph",
    "kovidam-AI-Interview": "Kovidam AI Interview",
    "Full-Agentic-AI-basics-to-advance-": "Agentic AI, basics to advanced",
}

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
        return sum(hours[h % 24] for h in hs) / n

    night, morning = share([22, 23, 0, 1, 2, 3, 4]), share(range(5, 11))
    if night >= 0.30:
        chrono = ("Night Owl", f"{pct(night)} of my commits land between 22:00 and 05:00 {TZ_NAME}.", "night")
    elif morning >= 0.30:
        chrono = ("Early Bird", f"{pct(morning)} of my commits land between 05:00 and 11:00 {TZ_NAME}.", "day")
    else:
        chrono = ("Day Shift", f"{pct(1 - night - morning)} of my commits land between 11:00 and 22:00 {TZ_NAME}.",
                  "day")

    focus = max(range(24), key=lambda h: (sum(hours[(h + k) % 24] for k in range(3)), -h))
    focus_n = sum(hours[(focus + k) % 24] for k in range(3))

    sessions, cur = [], [local[0]]
    for prev, c in zip(local, local[1:]):
        if c[0] - prev[0] <= SESSION_GAP:
            cur.append(c)
        else:
            sessions.append(cur)
            cur = [c]
    sessions.append(cur)
    deep = max(sessions, key=lambda s: (s[-1][0] - s[0][0], len(s)))

    latest = None
    for t, repo, msg in reversed(local):
        if repo == LOGIN or msg.startswith("Merge ") or "[skip ci]" in msg:
            continue
        latest = (t, repo, msg)
        break

    peak_hour = max(range(24), key=lambda h: hours[h])
    synced = datetime.fromisoformat(NOW).astimezone(TZ) if NOW else datetime.now(TZ)
    return {
        "n": n,
        "repos": len({r for _, r, _ in local}),
        "grid": grid,
        "hours": hours,
        "days": days,
        "chrono": chrono,
        "after_midnight": share(range(0, 5)),
        "weekend": (days[5] + days[6]) / n,
        "focus": focus,
        "focus_n": focus_n,
        "peak_hour": peak_hour,
        "peak_day": max(range(7), key=lambda d: days[d]),
        "peak_cell": max(((d, h) for d in range(7) for h in range(24)), key=lambda dh: grid[dh[0]][dh[1]]),
        "active_days": len({t.date() for t, _, _ in local}),
        "since": local[0][0],
        "deep": deep,
        "deep_repo": Counter(r for _, r, _ in deep).most_common(1)[0][0],
        "latest": latest,
        "synced": synced,
    }


# ------------------------------------------------------------------ helpers
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def clean(s, limit):
    s = "".join(ch for ch in str(s) if ch.isprintable() and ord(ch) <= 0xFFFF).strip()
    return s if len(s) <= limit else s[:limit - 1].rstrip() + "…"


def pct(x):
    return f"{x * 100:.0f}%" if x >= 0.1 else f"{x * 100:.1f}%"


def display(repo, limit=30):
    return clean(DISPLAY.get(repo, repo), limit)


def hour_rgb(h):
    h = h % 24
    for (h0, c0), (h1, c1) in zip(HOUR_STOPS, HOUR_STOPS[1:]):
        if h <= h1:
            k = (h - h0) / (h1 - h0)
            return tuple(round(a + (b - a) * k) for a, b in zip(c0, c1))
    return HOUR_STOPS[-1][1]


def hour_color(h):
    return "#" + "".join(f"{v:02x}" for v in hour_rgb(h))


def polar(r, a):
    rad = math.radians(a)
    return CX + r * math.sin(rad), CY - r * math.cos(rad)


def anim(attr, values, dur, begin="0s", key_times=None, repeat=True, freeze=False, splines=True):
    vals = values.split(";")
    kt = key_times or ";".join(f"{i / (len(vals) - 1):.4f}" for i in range(len(vals)))
    extra = f' calcMode="spline" keySplines="{";".join([EASE] * (len(vals) - 1))}"' if splines else ""
    tail = ' repeatCount="indefinite"' if repeat else ""
    tail += ' fill="freeze"' if freeze else ""
    return (f'<animate attributeName="{attr}" values="{values}" keyTimes="{kt}" dur="{dur}" '
            f'begin="{begin}"{extra}{tail}/>')


def grow(attr, start, end, delay, dur=0.7):
    """One-shot animation from start to end after `delay`, frozen at end."""
    k = delay / (delay + dur)
    return (f'<animate attributeName="{attr}" values="{start};{start};{end}" keyTimes="0;{k:.4f};1" '
            f'dur="{delay + dur:.3f}s" fill="freeze" calcMode="spline" keySplines="{EASE};{OUT_EASE}"/>')


def pulse(begin, peak, dur=ORBIT, attr="opacity"):
    """Light up as the moon/sun passes: ~0.3s up, ~1s down, dark for the rest of the day."""
    return (f'<animate attributeName="{attr}" values="0;{peak};0;0" keyTimes="0;0.0125;0.055;1" '
            f'dur="{dur}s" begin="{begin:.3f}s" repeatCount="indefinite"/>')


def text(x, y, s, size=10, fill=INK3, anchor="start", family=MONO, weight=400, spacing=None, extra=""):
    ls = f' letter-spacing="{spacing}"' if spacing is not None else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}"{ls}{extra}>{s}</text>')


def micro(x, y, s, fill=INK3, anchor="start", size=9.5):
    return text(x, y, esc(s), size=size, fill=fill, anchor=anchor, spacing=1.4)


def fmt_dur(td):
    mins = int(td.total_seconds() // 60)
    return f"{mins // 60}h {mins % 60:02d}m" if mins >= 60 else f"{mins}m"


def day_fmt(t, fmt):
    return t.strftime(fmt).replace(" 0", " ")


def crescent(r=7.0, cut=(3.4, -2.6), r_cut=6.2, steps=36):
    """Polygon for a crescent: the disc of radius r minus a disc of radius r_cut at `cut`."""
    bx, by = cut
    d = math.hypot(bx, by)
    lx = (r * r - r_cut * r_cut + d * d) / (2 * d)
    hy = math.sqrt(max(r * r - lx * lx, 0))
    ux, uy = bx / d, by / d
    p1 = (lx * ux - hy * uy, lx * uy + hy * ux)
    p2 = (lx * ux + hy * uy, lx * uy - hy * ux)

    def ang(p, c=(0, 0)):
        return math.atan2(p[1] - c[1], p[0] - c[0])

    pts = []
    a1, a2 = ang(p1), ang(p2)
    # outer arc: the long way round, away from the cut
    span = (a2 - a1) % (2 * math.pi)
    if span < math.pi:
        span -= 2 * math.pi
    for i in range(steps + 1):
        a = a1 + span * i / steps
        pts.append((r * math.cos(a), r * math.sin(a)))
    # inner arc: back along the cut circle, the part that lies inside the disc
    b2, b1 = ang(p2, cut), ang(p1, cut)
    span_b = (b1 - b2) % (2 * math.pi)
    mid = b2 + span_b / 2
    if math.hypot(bx + r_cut * math.cos(mid), by + r_cut * math.sin(mid)) > r:
        span_b -= 2 * math.pi
    for i in range(1, steps):
        a = b2 + span_b * i / steps
        pts.append((bx + r_cut * math.cos(a), by + r_cut * math.sin(a)))
    return "M" + "L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + "Z"


def moon(scale=1.0, fill="#ede9fe"):
    return f'<path d="{crescent(7.0 * scale, (3.4 * scale, -2.6 * scale), 6.2 * scale)}" fill="{fill}"/>'


def sun(scale=1.0):
    rays = []
    for k in range(8):
        a = math.radians(k * 45)
        x0, y0 = 6.6 * scale * math.sin(a), -6.6 * scale * math.cos(a)
        x1, y1 = 9.4 * scale * math.sin(a), -9.4 * scale * math.cos(a)
        rays.append(f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" stroke="#fbbf24" '
                    f'stroke-width="{1.5 * scale:.2f}" stroke-linecap="round"/>')
    return f'<circle r="{4.6 * scale:.2f}" fill="#fde68a"/>' + "".join(rays)


# ------------------------------------------------------------------ render
def build(d):
    grid, hours, days = d["grid"], d["hours"], d["days"]
    n = d["n"]
    max_hour = max(hours) or 1
    max_cell = max(max(row) for row in grid) or 1
    max_day = max(days) or 1
    ph, pk_day, (pc_d, pc_h) = d["peak_hour"], d["peak_day"], d["peak_cell"]
    chrono_name, chrono_why, chrono_kind = d["chrono"]
    synced = d["synced"]
    deep = d["deep"]
    p = []

    # ---------------------------------------------------------------- document
    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-labelledby="rhyTitle rhyDesc">')
    p.append('<title id="rhyTitle">Build rhythm — when the code actually ships</title>')
    focus = d["focus"]
    desc = [
        f"{n} commits across {d['repos']} public repositories, bucketed by hour and weekday in {TZ_NAME}.",
        f"Chronotype {chrono_name}: {chrono_why}",
        f"Peak hour {ph:02d}:00 with {hours[ph]} commits.",
        f"Focus window {focus:02d}:00 to {(focus + 3) % 24:02d}:00 with {d['focus_n']} commits.",
        f"{pct(d['after_midnight'])} after midnight, {pct(d['weekend'])} on weekends.",
        f"Busiest weekday {DAYS[pk_day]} with {days[pk_day]} commits; busiest slot {DAYS[pc_d]} {pc_h:02d}:00 "
        f"with {grid[pc_d][pc_h]} commits.",
        f"{d['active_days']} active days since {d['since'].strftime('%B %Y')}.",
        f"Deepest session {fmt_dur(deep[-1][0] - deep[0][0])} with {len(deep)} commits, mostly in "
        f"{display(d['deep_repo'], 60)}.",
    ]
    if d["latest"]:
        lt, lr, lm = d["latest"]
        desc.append(f"Newest commit: {display(lr, 60)}, \"{clean(lm, 120)}\", "
                    f"{lt.strftime('%d %b %Y %H:%M')} {TZ_NAME}.")
    desc.append(f"Synced {synced.strftime('%Y-%m-%d %H:%M')} {TZ_NAME}.")
    p.append(f'<desc id="rhyDesc">{esc(" ".join(desc))}</desc>')

    night_hi, night_lo = "#16143a", "#0d0c19"
    day_hi, day_lo = "#2a1c08", "#0e0c09"
    p.append(f'''<defs>
    <pattern id="rhyDots" width="26" height="26" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="0.9" fill="#151518"/></pattern>
    <filter id="rhyGlow" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="rhySoft" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="7"/></filter>
    <linearGradient id="rhyNight" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{night_hi}"/><stop offset="1" stop-color="{night_lo}"/></linearGradient>
    <linearGradient id="rhyDay" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{day_lo}"/><stop offset="1" stop-color="{day_hi}"/></linearGradient>
    <linearGradient id="rhyTitleInk" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#f5f3ff"/><stop offset="0.55" stop-color="#c4b5fd"/><stop offset="1" stop-color="#818cf8"/></linearGradient>
    <linearGradient id="rhyDayInk" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fffbeb"/><stop offset="0.55" stop-color="#fcd34d"/><stop offset="1" stop-color="#fb923c"/></linearGradient>
    <linearGradient id="rhyRule" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#27272a" stop-opacity="0"/><stop offset="0.15" stop-color="#27272a"/><stop offset="0.85" stop-color="#27272a"/><stop offset="1" stop-color="#27272a" stop-opacity="0"/></linearGradient>
  </defs>''')

    # ---------------------------------------------------------------- frame + header
    p.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="#0a0a0a" stroke="#1f1f1f"/>')
    p.append(f'<rect x="14" y="14" width="{W - 28}" height="{H - 28}" fill="url(#rhyDots)"/>')
    p.append(micro(22, 30, "RHYTHM // LIVE", "#5a5a63", size=10))
    p.append(f'<circle cx="{W - 26}" cy="26.5" r="3" fill="#22c55e" filter="url(#rhyGlow)">'
             f'{anim("opacity", "1;0.3;1", "1.8s")}</circle>')
    p.append(micro(W - 36, 30, f'{n:,} COMMITS · {d["repos"]} PUBLIC REPOS · SYNCED '
                               f'{synced.strftime("%d %b %H:%M").upper()} {TZ_NAME}', "#5a5a63", "end", 10))

    # ---------------------------------------------------------------- the sky
    xl, xr = CX - R_SKY, CX + R_SKY
    p.append(f'<path d="M{xl},{CY} A{R_SKY},{R_SKY} 0 0 1 {xr},{CY} Z" fill="url(#rhyNight)"/>')
    p.append(f'<path d="M{xl},{CY} A{R_SKY},{R_SKY} 0 0 0 {xr},{CY} Z" fill="url(#rhyDay)"/>')
    p.append(f'<defs><clipPath id="rhySkyClip"><circle cx="{CX}" cy="{CY}" r="{R_SKY - 1}"/></clipPath></defs>')
    p.append(f'<g clip-path="url(#rhySkyClip)"><ellipse cx="{CX}" cy="{CY + R_SKY - 6}" rx="{R_SKY * 0.7:.0f}" '
             f'ry="46" fill="#f59e0b" opacity="0.13" filter="url(#rhySoft)"/></g>')
    p.append(f'<circle cx="{CX}" cy="{CY}" r="{R_SKY}" fill="none" stroke="#202029"/>')
    # stars live in the night band between the rods and the rim
    star_spots = [(-72, 0.62), (-58, 0.86), (-41, 0.74), (-28, 0.93), (-12, 0.69), (9, 0.88), (23, 0.71),
                  (37, 0.95), (52, 0.66), (66, 0.83), (78, 0.72), (-84, 0.9), (-50, 0.55), (31, 0.52)]
    for i, (a, k) in enumerate(star_spots):
        r = R_MAX + 7 + (R_SKY - R_MAX - 13) * k
        x, y = polar(r, a)
        size = 0.65 + 0.45 * ((i * 7) % 5) / 4
        tw = anim("opacity", "0.9;0.15;0.9", f"{2.1 + (i % 5) * 0.55:.2f}s", f"{(i * 0.37) % 2:.2f}s") if i % 2 == 0 else ""
        p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{size:.2f}" fill="#e0e7ff" opacity="0.75">{tw}</circle>')

    # horizon, with dusk / dawn at its ends
    p.append(f'<line x1="{xl - 4}" y1="{CY}" x2="{xr + 4}" y2="{CY}" stroke="#2c2c36" stroke-dasharray="1 3"/>')
    # rim ticks: every hour, longer every three
    for h in range(24):
        a = h * 15
        inner = R_SKY - (6 if h % 3 == 0 else 3)
        (x0, y0), (x1, y1) = polar(inner, a), polar(R_SKY, a)
        p.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="#34343f" stroke-width="1"/>')
    for h in range(0, 24, 3):
        if h in (6, 18):
            continue
        x, y = polar(R_LABEL, h * 15)
        hot = h == ph
        fill = INK if hot else (INK2 if h in (0, 12) else INK4)
        p.append(text(x, y + 3.5, f"{h:02d}", size=10, fill=fill, anchor="middle", weight=700 if hot else 400))
    if ph % 3 and ph not in (6, 18):
        x, y = polar(R_LABEL, ph * 15)
        p.append(text(x, y + 3.5, f"{ph:02d}", size=10, fill=INK, anchor="middle", weight=700))
    p.append(text(xr + 10, CY + 3.5, "06", size=10, fill=INK2))
    p.append(text(xr + 10, CY + 16, "DAWN", size=7.5, fill="#f472b6", spacing=1.5, extra=' opacity="0.8"'))
    p.append(text(xl - 10, CY + 3.5, "18", size=10, fill=INK2, anchor="end"))
    p.append(text(xl - 8.5, CY + 16, "DUSK", size=7.5, fill="#fb7185", anchor="end", spacing=1.5,
                  extra=' opacity="0.8"'))

    # ---------------------------------------------------------------- rods
    rod_len = R_MAX - R_BASE
    for h in range(24):
        a = h * 15
        bx, by = polar(R_BASE, a)
        tx, ty = polar(R_MAX, a)
        p.append(f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" stroke="#15151c" '
                 f'stroke-width="{ROD_W}" stroke-linecap="round"/>')
    for h in range(24):
        v = hours[h]
        if not v:
            continue
        a = h * 15
        t = v / max_hour
        bx, by = polar(R_BASE, a)
        ex, ey = polar(R_BASE + max(3.0, rod_len * t), a)
        col = hour_color(h)
        delay = 0.15 + h * 0.045
        hot = h == ph
        if hot:
            p.append(f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{col}" '
                     f'stroke-width="{ROD_W + 6}" stroke-linecap="round" opacity="0.35" filter="url(#rhySoft)">'
                     f'{anim("opacity", "0.25;0.6;0.25", "3.2s")}</line>')
        # each rod is a beam: dim at the base, full colour at the tip
        p.append(f'<defs><linearGradient id="rhyRod{h}" gradientUnits="userSpaceOnUse" x1="{bx:.1f}" y1="{by:.1f}" '
                 f'x2="{ex:.1f}" y2="{ey:.1f}"><stop offset="0" stop-color="{col}" stop-opacity="0.38"/>'
                 f'<stop offset="1" stop-color="{col}"/></linearGradient></defs>')
        p.append(f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="url(#rhyRod{h})" '
                 f'stroke-width="{ROD_W}" stroke-linecap="round" stroke-opacity="{0.62 + 0.38 * t ** 0.7:.2f}">'
                 f'{grow("x2", f"{bx:.1f}", f"{ex:.1f}", delay)}{grow("y2", f"{by:.1f}", f"{ey:.1f}", delay)}</line>')
        # flash as the moon / sun passes overhead
        p.append(f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#ffffff" '
                 f'stroke-width="{ROD_W}" stroke-linecap="round" opacity="0">'
                 f'{pulse(ORBIT_BEGIN + h - 0.3, 0.55)}</line>')
    # peak readout at the tip of the longest rod
    tip_x, tip_y = polar(R_MAX + 0.5, ph * 15)
    p.append(f'<circle cx="{tip_x:.1f}" cy="{tip_y:.1f}" r="2.2" fill="#ffffff" filter="url(#rhyGlow)"/>')

    # ---------------------------------------------------------------- moon / sun on its orbit
    r = R_ORB
    orbit_path = (f"M0,0 A{r},{r} 0 0 1 {r},{r} A{r},{r} 0 0 1 0,{2 * r} "
                  f"A{r},{r} 0 0 1 {-r},{r} A{r},{r} 0 0 1 0,0")
    night_vis = ("1;1;0;0;1;1", "0;0.245;0.255;0.745;0.755;1")
    day_vis = ("0;0;1;1;0;0", "0;0.245;0.255;0.745;0.755;1")
    p.append(f'<g transform="translate({CX},{CY - r})">'
             f'<animateMotion path="{orbit_path}" dur="{ORBIT}s" begin="{ORBIT_BEGIN}s" repeatCount="indefinite"/>'
             f'<g opacity="1"><animate attributeName="opacity" values="{night_vis[0]}" keyTimes="{night_vis[1]}" '
             f'dur="{ORBIT}s" begin="{ORBIT_BEGIN}s" repeatCount="indefinite"/>'
             f'<circle r="11" fill="#a78bfa" opacity="0.35" filter="url(#rhySoft)"/>{moon(0.95)}</g>'
             f'<g opacity="0"><animate attributeName="opacity" values="{day_vis[0]}" keyTimes="{day_vis[1]}" '
             f'dur="{ORBIT}s" begin="{ORBIT_BEGIN}s" repeatCount="indefinite"/>'
             f'<circle r="12" fill="#f59e0b" opacity="0.45" filter="url(#rhySoft)"/>{sun(0.9)}</g>'
             f'</g>')

    # ---------------------------------------------------------------- centre readout
    p.append(f'<circle cx="{CX}" cy="{CY}" r="{R_HOLE}" fill="#09090c" stroke="#2a2840"/>')
    p.append(f'<circle cx="{CX}" cy="{CY}" r="{R_HOLE}" fill="none" stroke="#a78bfa" stroke-width="1" opacity="0.3">'
             f'{anim("opacity", "0.45;0.08;0.45", "3.4s")}</circle>')
    p.append(micro(CX, CY - 15, "PEAK HOUR", INK3, "middle", 7.5))
    p.append(text(CX, CY + 7.5, f"{ph:02d}:00", size=21, fill=INK, anchor="middle", family=SANS, weight=700))
    p.append(micro(CX, CY + 22, f"{hours[ph]} commits", INK2, "middle", 8))

    # ---------------------------------------------------------------- readout panel
    x0, x1 = 432, W - 24
    pw = x1 - x0
    is_night = chrono_kind == "night"
    p.append(micro(x0, 70, "CHRONOTYPE", "#a78bfa" if is_night else "#fbbf24"))
    p.append(micro(x0 + len("CHRONOTYPE") * (9.5 * 0.6 + 1.4) + 6, 70,
                   f"· DERIVED FROM {n:,} COMMITS, NOT SELF-DECLARED", INK4))
    p.append(text(x0 - 2, 121, esc(chrono_name), size=50, fill=f"url(#{'rhyTitleInk' if is_night else 'rhyDayInk'})",
                  family=SANS, weight=800, spacing=-1))
    p.append(text(x0, 150, esc(chrono_why), size=14.5, fill=INK2, family=SANS))
    ix, iy = x1 - 30, 98
    if is_night:
        p.append(f'<circle cx="{ix}" cy="{iy}" r="26" fill="#8b5cf6" opacity="0.28" filter="url(#rhySoft)"/>')
        p.append(f'<g transform="translate({ix},{iy}) scale(2.3)">{moon(1.0, "#f5f3ff")}</g>')
        for sx, sy, dur in ((-28, -16, "2.3s"), (20, 20, "3.1s"), (-24, 18, "2.7s"), (24, -22, "3.6s")):
            p.append(f'<circle cx="{ix + sx}" cy="{iy + sy}" r="1.2" fill="#e0e7ff">'
                     f'{anim("opacity", "1;0.1;1", dur)}</circle>')
    else:
        p.append(f'<circle cx="{ix}" cy="{iy}" r="26" fill="#f59e0b" opacity="0.32" filter="url(#rhySoft)"/>')
        p.append(f'<g transform="translate({ix},{iy}) scale(2.1)">{sun(1.0)}</g>')

    # four headline numbers, separated by hairlines rather than boxed
    fw = pw / 4
    metrics = [
        ("AFTER MIDNIGHT", pct(d["after_midnight"]), f"00:00–05:00 {TZ_NAME}", "#818cf8"),
        ("FOCUS WINDOW", f"{focus:02d}–{(focus + 3) % 24:02d}", f'{d["focus_n"]} commits',
         "#c084fc"),
        ("WEEKEND", pct(d["weekend"]), "Sat + Sun share", "#fb7185"),
        ("ACTIVE DAYS", f'{d["active_days"]}', f'since {d["since"].strftime("%b %Y")}', "#fbbf24"),
    ]
    my = 186
    for i, (lab, val, sub, col) in enumerate(metrics):
        mx = x0 + i * fw + (0 if i == 0 else 16)
        if i:
            p.append(f'<line x1="{x0 + i * fw:.1f}" y1="{my - 8}" x2="{x0 + i * fw:.1f}" y2="{my + 50}" stroke="{LINE}"/>')
        p.append(f'<circle cx="{mx + 3:.1f}" cy="{my - 3.2:.1f}" r="2.6" fill="{col}"/>')
        p.append(micro(mx + 11, my, lab, INK3, size=8.5))
        p.append(text(mx - 1, my + 30, esc(val), size=27, fill=INK, family=SANS, weight=700, spacing=-0.5))
        p.append(text(mx, my + 47, esc(sub), size=9.5, fill=INK3))

    # deepest session on a track tinted by the hours it crossed
    sy = 268
    span = deep[-1][0] - deep[0][0]
    t_a, t_b = deep[0][0], deep[-1][0]
    p.append(f'<line x1="{x0}" y1="{sy - 18}" x2="{x1}" y2="{sy - 18}" stroke="url(#rhyRule)"/>')
    p.append(micro(x0, sy + 6, "DEEPEST SESSION", INK3, size=8.5))
    p.append(micro(x1, sy + 6, "no gap over 90 min", INK4, "end", 8.5))
    p.append(f'<text x="{x0 - 1}" y="{sy + 38}" font-family="{SANS}" font-size="27" font-weight="700" fill="{INK}" '
             f'letter-spacing="-0.5">{fmt_dur(span)}<tspan dx="10" font-size="13.5" font-weight="400" fill="{INK2}" '
             f'letter-spacing="0">{len(deep)} commits · {esc(display(d["deep_repo"], 34))}</tspan></text>')
    p.append(text(x0, sy + 56, esc(f'{day_fmt(t_a, "%a %d %b %Y")} · {t_a.strftime("%H:%M")} → '
                                   f'{t_b.strftime("%H:%M")} {TZ_NAME}'), size=10, fill=INK3))
    ty = sy + 78
    secs = max(span.total_seconds(), 1)
    stops = []
    cursor = t_a
    while cursor <= t_b:
        off = (cursor - t_a).total_seconds() / secs
        hh = cursor.hour + cursor.minute / 60
        stops.append(f'<stop offset="{off:.4f}" stop-color="{hour_color(hh)}"/>')
        cursor = (cursor + timedelta(minutes=30)).replace(second=0, microsecond=0)
    stops.append(f'<stop offset="1" stop-color="{hour_color(t_b.hour + t_b.minute / 60)}"/>')
    p.append(f'<defs><linearGradient id="rhyTrack" x1="{x0}" y1="0" x2="{x1}" y2="0" gradientUnits="userSpaceOnUse">'
             f'{"".join(stops)}</linearGradient></defs>')
    p.append(f'<rect x="{x0}" y="{ty - 3}" width="{pw}" height="6" rx="3" fill="url(#rhyTrack)" opacity="0.28"/>')
    for t, _, _ in deep:
        tx = x0 + pw * (t - t_a).total_seconds() / secs
        p.append(f'<line x1="{tx:.1f}" y1="{ty - 7}" x2="{tx:.1f}" y2="{ty + 7}" stroke="url(#rhyTrack)" '
                 f'stroke-width="1.6" stroke-linecap="round"/>')
    # mark midnight and sunrise if the session crossed them
    for mark_h, glyph in ((0, "moon"), (6, "sun")):
        mark = t_a.replace(hour=mark_h, minute=0, second=0, microsecond=0)
        if mark <= t_a:
            mark += timedelta(days=1)
        if t_a < mark < t_b:
            mx = x0 + pw * (mark - t_a).total_seconds() / secs
            p.append(f'<line x1="{mx:.1f}" y1="{ty + 10}" x2="{mx:.1f}" y2="{ty + 16}" stroke="{INK4}"/>')
            icon = moon(0.55, "#c4b5fd") if glyph == "moon" else sun(0.5)
            p.append(f'<g transform="translate({mx:.1f},{ty + 24})">{icon}</g>')
            p.append(text(mx + 10, ty + 27.5, f"{mark_h:02d}:00", size=8.5, fill=INK4))
    p.append(f'<circle cx="{x0}" cy="{ty}" r="3.4" fill="#ffffff" filter="url(#rhyGlow)">'
             f'<animate attributeName="cx" values="{x0};{x1}" dur="5s" repeatCount="indefinite"/>'
             f'{anim("opacity", "0;1;1;0", "5s", key_times="0;0.08;0.9;1", splines=False)}</circle>')

    # ---------------------------------------------------------------- week x hour punch card
    gy = 422
    p.append(f'<line x1="22" y1="{gy - 14}" x2="{W - 22}" y2="{gy - 14}" stroke="url(#rhyRule)"/>')
    p.append(micro(22, gy + 14, "WEEK × HOUR", INK2, size=10))
    p.append(micro(22 + len("WEEK × HOUR") * (10 * 0.6 + 1.4) + 6, gy + 14,
                   "· all 168 hours of the week · dot area = commits", INK4, size=9.5))
    # size legend
    lx = W - 24
    for v in sorted({max_cell, max(1, round(max_cell / 2)), max(1, round(max_cell / 8))}, reverse=True):
        rr = DOT_MAX * math.sqrt(v / max_cell)
        p.append(text(lx, gy + 14, str(v), size=9, fill=INK4, anchor="end"))
        lx -= 6 + 5.4 * len(str(v))
        p.append(f'<circle cx="{lx - rr:.1f}" cy="{gy + 10.5}" r="{rr:.1f}" fill="#3f3f46"/>')
        lx -= 2 * rr + 12

    # sky strip: the clock's colours laid flat over the hours
    for h in range(24):
        cx = PC_X0 + h * PC_DX
        p.append(f'<rect x="{cx - PC_DX / 2 + 2:.1f}" y="{PC_Y0 - 27}" width="{PC_DX - 4:.1f}" height="3" rx="1.5" '
                 f'fill="{hour_color(h)}" opacity="0.55"/>')
    # column glow that follows the moon / sun
    for h in range(24):
        cx = PC_X0 + h * PC_DX
        p.append(f'<rect x="{cx - PC_DX / 2 + 1:.1f}" y="{PC_Y0 - 18}" width="{PC_DX - 2:.1f}" '
                 f'height="{PC_DY * 6 + 36:.1f}" rx="7" fill="{hour_color(h)}" opacity="0">'
                 f'{pulse(ORBIT_BEGIN + h - 0.3, 0.14)}</rect>')
    for day in range(7):
        y = PC_Y0 + day * PC_DY
        hot_day = day == pk_day
        p.append(text(56, y + 3.5, DAYS[day][:3], size=10, fill=INK if hot_day else INK3, anchor="end",
                      weight=700 if hot_day else 400))
        for h in range(24):
            cx = PC_X0 + h * PC_DX
            v = grid[day][h]
            if not v:
                p.append(f'<circle cx="{cx:.1f}" cy="{y:.1f}" r="1.1" fill="#2a2a31"/>')
                continue
            k = math.sqrt(v / max_cell)
            rr = max(1.8, DOT_MAX * k)
            delay = 0.35 + h * 0.035 + day * 0.03
            p.append(f'<circle cx="{cx:.1f}" cy="{y:.1f}" r="{rr:.2f}" fill="{hour_color(h)}" '
                     f'fill-opacity="{0.42 + 0.58 * k:.2f}">{grow("r", "0", f"{rr:.2f}", delay, 0.5)}</circle>')
        # weekday totals
        bw = 62 * days[day] / max_day
        bx0 = PC_X0 + 23 * PC_DX + 26
        p.append(f'<rect x="{bx0:.1f}" y="{y - 3:.1f}" width="62" height="6" rx="3" fill="#16161c"/>')
        p.append(f'<rect x="{bx0:.1f}" y="{y - 3:.1f}" width="{bw:.1f}" height="6" rx="3" '
                 f'fill="{"#e4e4e7" if hot_day else "#52525b"}">{grow("width", "0", f"{bw:.1f}", 0.6 + day * 0.05)}</rect>')
        p.append(text(bx0 + 70, y + 3.5, f"{days[day]}", size=10, fill=INK if hot_day else INK3,
                      weight=700 if hot_day else 400))
    # hour numerals under the grid
    for h in range(24):
        cx = PC_X0 + h * PC_DX
        y = PC_Y0 + 6 * PC_DY + 24
        if h % 3 == 0:
            p.append(text(cx, y, f"{h:02d}", size=9.5, fill=INK2 if h in (0, 12) else INK4, anchor="middle"))
        else:
            p.append(f'<circle cx="{cx:.1f}" cy="{y - 3.5:.1f}" r="0.9" fill="#3a3a44"/>')

    # busiest slot
    bx, by = PC_X0 + pc_h * PC_DX, PC_Y0 + pc_d * PC_DY
    p.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="{DOT_MAX + 3.5:.1f}" fill="none" stroke="#ffffff" '
             f'stroke-width="1.3" opacity="0.9"/>')
    # newest commit
    if d["latest"]:
        lt = d["latest"][0]
        lx_, ly_ = PC_X0 + lt.hour * PC_DX, PC_Y0 + lt.weekday() * PC_DY
        p.append(f'<circle cx="{lx_:.1f}" cy="{ly_:.1f}" r="3.2" fill="#22c55e" stroke="#0a0a0a" stroke-width="1.2"/>')
        p.append(f'<circle cx="{lx_:.1f}" cy="{ly_:.1f}" r="4" fill="none" stroke="#22c55e" stroke-width="1.3">'
                 f'{anim("r", "4;15;15", "2.2s")}{anim("opacity", "0.9;0;0", "2.2s")}</circle>')

    # ---------------------------------------------------------------- footer
    fy = H - 22
    p.append(f'<circle cx="27" cy="{fy - 3.5}" r="3.2" fill="#22c55e"/>')
    if d["latest"]:
        lt, lr, lm = d["latest"]
        p.append(f'<text x="37" y="{fy}" font-family="{MONO}" font-size="9.5" fill="{INK3}">LATEST '
                 f'<tspan fill="{INK}" font-weight="700">{esc(display(lr, 26))}</tspan>'
                 f'<tspan fill="{INK3}"> · {esc(clean(lm, 46))} · {lt.strftime("%d %b %H:%M").lstrip("0")} '
                 f'{TZ_NAME}</tspan></text>')
    p.append(f'<circle cx="{W - 222}" cy="{fy - 3.5}" r="4.4" fill="none" stroke="#ffffff" stroke-width="1.2"/>')
    p.append(f'<text x="{W - 212}" y="{fy}" font-family="{MONO}" font-size="9.5" fill="{INK3}">BUSIEST '
             f'<tspan fill="{INK}" font-weight="700">{DAYS[pc_d][:3]} {pc_h:02d}:00</tspan> · '
             f'{grid[pc_d][pc_h]} commits</text>')

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
