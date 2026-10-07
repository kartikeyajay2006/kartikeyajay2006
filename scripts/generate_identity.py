#!/usr/bin/env python3
"""Generate assets/identity-core.svg — the section 02 "Identity" plate: a
fingerprint grown from the work itself, beside a short bio and the rules the
work keeps.

The print is a real ridge pattern, not a drawing of one. Ridges are the zero
set of cos(psi) (the AM-FM fingerprint model of Larkin & Fletcher, 2007):
psi = a whorl-over-arches phase field + one spiral phase singularity per
public repository. A spiral singularity is exactly what a minutia is (the
point where a ridge ends or forks), so every circled point on the print is a
ridge ending that only exists because that repository does.

  - one minutia per owned, public, non-fork repository, ordered by the date
    of its oldest commit on the default branch (falling back to the repo's
    creation date) and placed on a sunflower spiral: the first commit sits at
    the core, the newest repository at the rim. Ridge spacing, the flow field
    and every existing minutia's position are fixed, so a new repository adds
    one ending near the rim and the ridges re-flow slightly around it.
  - a light pulse travels from the core to the rim on a loop, and each
    minutia flashes as it passes — the repositories light up in the order
    they were started.
  - the named callouts are curated (FLAGSHIPS below), but their positions
    come from the same data as every other point.
  - the header numbers (repositories, bytes of code) are live.

The bio and the four rules are curated copy. Every rule names the
repositories it was shipped in; nothing there is a number or a claim the
repositories do not back up.

SVG notes (see generate_signal.py): GitHub strips <script> and inline <style>,
so all motion is SMIL, and camo strips internal href references, so nothing
uses <use>/<mpath>. url(#id) paint, mask and filter references are fine (every
other asset here relies on them). Everything readable starts visible; the
reveal and pulse only add light, so a renderer that ignores SMIL shows the
finished plate.

Local preview without the API: set IDENTITY_FIXTURE to a JSON list of
{"name", "first", "bytes"} repositories and the script renders from that file.
Set IDENTITY_DUMP to a path to save the fetched list in that same format.

Never-fail contract: this script always exits 0. Any problem is logged to
stderr and the output file is left exactly as it was.
"""
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

LOGIN = os.environ.get("GH_LOGIN", "kartikeyajay2006")
TOKEN = os.environ.get("GH_TOKEN", "")
FIXTURE = os.environ.get("IDENTITY_FIXTURE", "")
DUMP = os.environ.get("IDENTITY_DUMP", "")
OUT_PATH = os.environ.get("OUT_PATH", "assets/identity-core.svg")

TZ = timezone(timedelta(hours=5, minutes=30))
TZ_NAME = "IST"

W, H = 900, 800
MONO = "Consolas, 'SF Mono', monospace"
SANS = "Helvetica, Arial, sans-serif"
EASE = "0.42 0 0.58 1"
EASE_REVEAL = "0.45 0.05 0.35 1"

# ---- the print (core-relative coordinates, y down)
CX, CY = 450, 266
BX, BTOP, BBOT = 172, 214, 182     # silhouette half-width, reach above / below the core
LAM = 5.8                          # ridge period
STEP = 0.7                         # contour grid step
TILT = math.radians(-6)            # prints are rarely square to the frame
ASPECT = 1.08                      # pulse / reveal ellipse, matches the whorl
M_R0, M_RMAX, M_SLOTS = 28, 143, 48  # minutiae: first ring, last ring, capacity before rescaling
LABEL_GAP = 48                     # minimum distance between two callouts in one column
GOLD = math.pi * (3 - math.sqrt(5))

# ---- motion
REVEAL_AT, REVEAL_DUR, REVEAL_R = 0.2, 3.0, 250
PULSE_AT, PULSE_EVERY, PULSE_SWEEP = 4.0, 7.5, 3.6
PULSE_CREST = 0.94                 # where the band is brightest, as a fraction of its radius
EASE_PULSE = "0.2 0.55 0.45 1"     # decelerates like a ripple; repos light at a near-steady beat

# ---- time axis under the print
TL_Y, TL_X0, TL_X1 = 480, 290, 610
INK = ("#a5b4fc", "#a78bfa", "#e879f9")

# Named minutiae. Positions still come from the data; only the labels are curated.
FLAGSHIPS = {
    "Wispr_goa_task": ("EraseOps", "provable data erasure"),
    "Agent_that_act-Hackathon": ("ForgeSRE", "SRE agent with a human gate"),
    "Sovereign-On_Premise-Agentic-AI-Workbench": ("AEGIS", "on-prem agent workbench"),
    "jky-terminal": ("JKY Terminal", "local-first AI terminal"),
    "Kovidam-Skill-Graph": ("Kovidam", "AI talent intelligence"),
    "multi-layer_orchestation": ("Chakraview", "agent orchestration control plane"),
}

LEAD = ["I build AI agents", "that act — and prove it."]
BIO = [
    "AI/ML engineer and co-founder of Kovidam, an AI",
    "talent-intelligence platform. I build systems end to end:",
    "the model, the agents that use it, the backend underneath",
    "and the product on top.",
    "",
    "Architected, not prompted — real data pipelines, real",
    "evaluation, and a person in charge of anything that",
    "can’t be undone.",
]
RULES = [
    ("Prove it worked", "#a78bfa",
     ["ForgeSRE checks recovery against", "thresholds; EraseOps rescans until", "nothing personal is left."]),
    ("A human signs off", "#ec4899",
     ["ForgeSRE stops before a production", "rollback; EraseOps waits for approval", "of one exact plan hash."]),
    ("Show the source", "#22d3ee",
     ["The evidence console links every", "answer to the exact video second or", "PDF page it came from."]),
    ("Run where the data lives", "#22c55e",
     ["AEGIS runs on one machine with no", "outbound calls; JKY Terminal and", "my-localmcp are local-first."]),
]

REPOS_Q = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 50, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name createdAt
        languages(first: 25, orderBy: {field: SIZE, direction: DESC}) { totalSize edges { size node { name } } }
        defaultBranchRef { target { ... on Commit { oid history(first: 1) { totalCount nodes { authoredDate } } } } }
      }
    }
  }
}"""
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
SAFE_OID = re.compile(r"^[0-9a-f]{40}$")


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
                     "User-Agent": f"{LOGIN}-identity-generator"},
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


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def code_bytes(langs):
    """Bytes of code as linguist counts them, minus notebooks (mostly stored output) —
    the same rule the signal dashboard uses."""
    total = langs.get("totalSize", 0)
    for e in langs.get("edges") or []:
        if (e.get("node") or {}).get("name") == "Jupyter Notebook":
            total -= e.get("size", 0)
    return max(0, total)


def oldest_commits(repos):
    """Date of the oldest commit on each default branch, two queries for the lot.

    GraphQL history only pages forward, but its cursors are "<head oid> <offset>",
    so asking for the first commit after offset (count - 2) returns the root commit.
    Anything this can't answer keeps its creation date."""
    out = {}
    todo = [r for r in repos if r["count"] > 1 and SAFE_NAME.match(r["name"]) and SAFE_OID.match(r["oid"] or "")]
    for i in range(0, len(todo), 25):
        batch = todo[i:i + 25]
        fields = " ".join(
            f'r{j}: repository(owner: "{LOGIN}", name: "{r["name"]}") {{ defaultBranchRef {{ target {{ '
            f'... on Commit {{ history(first: 1, after: "{r["oid"]} {r["count"] - 2}") {{ nodes {{ authoredDate }} }} }} }} }} }}'
            for j, r in enumerate(batch))
        try:
            data = gql(f"query {{ {fields} }}", {})
        except FetchError as e:
            print(f"WARNING: oldest-commit lookup failed for a batch, using creation dates: {e}", file=sys.stderr)
            continue
        for j, r in enumerate(batch):
            try:
                node = data[f"r{j}"]["defaultBranchRef"]["target"]["history"]["nodes"][0]
                out[r["name"]] = parse_ts(node["authoredDate"])
            except (KeyError, IndexError, TypeError):
                pass
    return out


def fetch():
    if FIXTURE:
        with open(FIXTURE, encoding="utf-8") as f:
            return [{"name": r["name"], "first": parse_ts(r["first"]), "bytes": int(r.get("bytes", 0))}
                    for r in json.load(f)]
    if not TOKEN:
        raise FetchError("GH_TOKEN is not set. Add a PAT as the GH_CONTRIB_PAT repo secret.")

    repos, cursor = [], None
    while True:
        user = gql(REPOS_Q, {"login": LOGIN, "cursor": cursor}).get("user")
        if not user:
            raise FetchError(f"user '{LOGIN}' not found")
        page = user["repositories"]
        for node in page["nodes"]:
            target = ((node.get("defaultBranchRef") or {}).get("target") or {})
            hist = target.get("history") or {}
            head = (hist.get("nodes") or [{}])[0].get("authoredDate")
            repos.append({
                "name": node["name"],
                "created": parse_ts(node["createdAt"]),
                "head": parse_ts(head) if head else None,
                "oid": target.get("oid"),
                "count": hist.get("totalCount", 0),
                "bytes": code_bytes(node.get("languages") or {}),
            })
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    roots = oldest_commits(repos)
    out = []
    for r in repos:
        first = roots.get(r["name"]) or (r["head"] if r["count"] == 1 else None) or r["created"]
        out.append({"name": r["name"], "first": first, "bytes": r["bytes"]})

    if DUMP:
        with open(DUMP, "w", encoding="utf-8") as f:
            json.dump([{"name": r["name"], "first": r["first"].strftime("%Y-%m-%dT%H:%M:%SZ"), "bytes": r["bytes"]}
                       for r in out], f, indent=1)
    return out


# ------------------------------------------------------------------ the print
def layout(repos):
    """Sunflower placement: rank i (oldest first) sits at radius ~ sqrt(i), so the
    pulse meets the repositories in the order they were started. The spiral's
    rotation is the one that best splits the named minutiae between the two
    label columns and keeps them clear of the top and bottom of the print."""
    slots = max(M_SLOTS, len(repos))
    k = (M_RMAX - M_R0) / math.sqrt(slots - 0.5)
    named = [i for i, r in enumerate(repos) if r["name"] in FLAGSHIPS or i == 0]

    def place(off):
        pts = []
        for i in range(len(repos)):
            rho = M_R0 + k * math.sqrt(i + 0.5)
            th = off + i * GOLD
            pts.append((rho * math.cos(th), rho * math.sin(th) * ASPECT))  # pulse meets them in rank order
        return pts

    def score(pts):
        left = [pts[i] for i in named if pts[i][0] < 0]
        right = [pts[i] for i in named if pts[i][0] >= 0]
        s = 4 * abs(len(left) - len(right))
        for x, y in left + right:
            s += abs(y) / (abs(x) + abs(y) + 1e-9)          # prefer the flanks
        for side in (left, right):
            ys = sorted(y for _, y in side)
            s += sum(max(0, LABEL_GAP - (b - a)) / LABEL_GAP for a, b in zip(ys, ys[1:]))
        return s

    best = min((place(step * math.pi / 36) for step in range(72)), key=score)
    for r, (x, y), i in zip(repos, best, range(len(repos))):
        r["mx"], r["my"] = x, y
        r["pol"] = 1 if i % 2 == 0 else -1
    return repos


def base_phase(x, y):
    """Distance-like flow: an elliptical whorl around the core that straightens into
    horizontal ridges below it. Where the two meet, two deltas form on their own."""
    c, s = math.cos(TILT), math.sin(TILT)
    xr, yr = x * c - y * s, x * s + y * c
    x2 = xr + 4.5 * math.sin(0.019 * yr + 0.6) + 2.6 * math.sin(0.011 * (xr + yr) + 2.1)
    y2 = yr + 3.6 * math.sin(0.017 * xr + 1.7) + 2.2 * math.sin(0.023 * (xr - yr) + 0.4)
    aspect = 1.05 - 0.07 * math.tanh(y2 / 24)                # taller above the core than below
    r = math.hypot(x2, y2 / aspect)
    w = 1 / (1 + math.exp(-(y2 - 70) / 22)) / (1 + math.exp(-(r - 60) / 14))
    return r * (1 - w) + (0.78 * y2 + 34) * w


def inside(x, y, slack=1.0):
    by = BTOP if y < 0 else BBOT
    return (x / BX) ** 2 + (y / by) ** 2 <= slack


def ridges(repos):
    """Centrelines of the ridges: marching squares on sin(psi) = 0 where cos(psi) > 0,
    chained into polylines, clipped to the silhouette and simplified."""
    mins = [(r["mx"], r["my"], r["pol"]) for r in repos]
    kk = 2 * math.pi / LAM
    x0, x1, y0, y1 = -BX - 6, BX + 6, -BTOP - 6, BBOT + 6
    nx, ny = int((x1 - x0) / STEP) + 1, int((y1 - y0) / STEP) + 1
    atan2, sin, cos = math.atan2, math.sin, math.cos
    S, C = [], []
    for j in range(ny):
        y = y0 + j * STEP
        srow, crow = [], []
        for i in range(nx):
            x = x0 + i * STEP
            psi = kk * base_phase(x, y)
            for mx, my, p in mins:
                psi += p * atan2(y - my, x - mx)
            srow.append(sin(psi))
            crow.append(cos(psi))
        S.append(srow)
        C.append(crow)

    cases = {1: ((3, 0),), 2: ((0, 1),), 3: ((3, 1),), 4: ((1, 2),), 5: ((3, 0), (1, 2)), 6: ((0, 2),),
             7: ((3, 2),), 8: ((2, 3),), 9: ((0, 2),), 10: ((0, 1), (2, 3)), 11: ((1, 2),), 12: ((1, 3),),
             13: ((0, 1),), 14: ((3, 0),)}
    adj = {}
    for j in range(ny - 1):
        s0, s1, c0, c1 = S[j], S[j + 1], C[j], C[j + 1]
        for i in range(nx - 1):
            a, b, c, d = s0[i], s0[i + 1], s1[i + 1], s1[i]
            idx = (a > 0) | (b > 0) << 1 | (c > 0) << 2 | (d > 0) << 3
            if idx in (0, 15) or c0[i] + c0[i + 1] + c1[i + 1] + c1[i] <= 0:
                continue
            edges = ((i, j, 0), (i + 1, j, 1), (i, j + 1, 0), (i, j, 1))  # top right bottom left
            for e1, e2 in cases[idx]:
                adj.setdefault(edges[e1], []).append(edges[e2])
                adj.setdefault(edges[e2], []).append(edges[e1])

    def point(e):
        i, j, vertical = e
        if vertical:
            a, b = S[j][i], S[j + 1][i]
            return x0 + i * STEP, y0 + (j + a / (a - b)) * STEP
        a, b = S[j][i], S[j][i + 1]
        return x0 + (i + a / (a - b)) * STEP, y0 + j * STEP

    seen, chains = set(), []
    for ends_only in (True, False):
        for start in adj:
            if start in seen or (ends_only and len(adj[start]) != 1):
                continue
            chain, cur = [start], start
            seen.add(start)
            while True:
                nxt = [e for e in adj[cur] if e not in seen]
                if not nxt:
                    break
                cur = nxt[0]
                seen.add(cur)
                chain.append(cur)
            if not ends_only:
                chain.append(start)
            chains.append([point(e) for e in chain])

    out = []
    for pts in chains:
        run = []
        for p in pts + [None]:
            if p is not None and inside(*p, 1.03):
                run.append(p)
                continue
            if len(run) > 2 and sum(math.dist(a, b) for a, b in zip(run, run[1:])) > 4:
                out.append(simplify(run, 0.16))
            run = []
    return out


def simplify(pts, eps):
    """Ramer-Douglas-Peucker, iterative (chains run to thousands of points); a closed
    run, whose ends coincide, is measured from its start point."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        lo, hi = stack.pop()
        (x1, y1), (x2, y2) = pts[lo], pts[hi]
        dx, dy = x2 - x1, y2 - y1
        span = math.hypot(dx, dy)
        best, idx = 0.0, 0
        for q in range(lo + 1, hi):
            px, py = pts[q]
            d = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / span if span > 1e-6 else math.hypot(px - x1, py - y1)
            if d > best:
                best, idx = d, q
        if best > eps:
            keep[idx] = True
            stack += [(lo, idx), (idx, hi)]
    return [p for p, k in zip(pts, keep) if k]


def num(v):
    s = f"{v:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    if s in ("-0", "0"):
        return "0"
    return s.replace("0.", ".", 1) if s.startswith(("0.", "-0.")) else s


def path_data(polylines):
    """Compact relative path data: absolute moveto, then implicit relative linetos."""
    out = []
    for pts in polylines:
        px, py = round(CX + pts[0][0], 1), round(CY + pts[0][1], 1)
        seg = [f"M{num(px)} {num(py)}l"]
        first = True
        for x, y in pts[1:]:
            ax, ay = round(CX + x, 1), round(CY + y, 1)
            ddx, ddy = num(ax - px), num(ay - py)
            if ddx == "0" and ddy == "0":
                continue
            sep = "" if first else ("" if ddx.startswith("-") else " ")
            seg.append(f"{sep}{ddx}{'' if ddy.startswith('-') else ' '}{ddy}")
            px, py, first = ax, ay, False
        if not first:
            out.append("".join(seg))
    return "".join(out)


# ------------------------------------------------------------------ motion helpers
def bezier_time(progress, spline):
    """Time fraction at which a keySplines-eased animation reaches `progress`."""
    x1, y1, x2, y2 = (float(v) for v in spline.split())

    def bez(t, a, b):
        return 3 * a * t * (1 - t) ** 2 + 3 * b * t * t * (1 - t) + t ** 3

    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if bez(mid, y1, y2) < progress:
            lo = mid
        else:
            hi = mid
    return bez((lo + hi) / 2, x1, x2)


def ell_r(x, y):
    return math.hypot(x, y / ASPECT)


def reveal_time(x, y):
    """When the developing edge of the print reaches (x, y)."""
    p = min(1.0, ell_r(x, y) / (0.95 * REVEAL_R))
    return REVEAL_AT + REVEAL_DUR * bezier_time(p, EASE_REVEAL)


def pulse_end(repos):
    """The pulse runs from the first commit to the newest repository and dissolves
    there: the ridges beyond the last minutia are room to grow, not history."""
    return (max(ell_r(r["mx"], r["my"]) for r in repos) + 14) / PULSE_CREST


def pulse_phase(x, y, r_end):
    """Fraction of each pulse cycle at which the band's crest passes (x, y)."""
    p = min(1.0, ell_r(x, y) / (PULSE_CREST * r_end))
    return PULSE_SWEEP * bezier_time(p, EASE_PULSE) / PULSE_EVERY


def appear(at, dur=0.45):
    k = at / (at + dur)
    return (f'<animate attributeName="opacity" values="0;0;1" keyTimes="0;{k:.4f};1" dur="{at + dur:.2f}s" '
            f'fill="freeze" calcMode="spline" keySplines="{EASE};{EASE}"/>')


def flash(attr, rest, peak, phase, width=0.07):
    """A blip at `phase` of every pulse cycle, after the reveal has finished."""
    a = max(0.0005, phase - width * 0.25)
    b = min(0.998, phase)
    c = min(0.999, phase + width)
    return (f'<animate attributeName="{attr}" values="{rest};{rest};{peak};{rest};{rest}" '
            f'keyTimes="0;{a:.4f};{b:.4f};{c:.4f};1" dur="{PULSE_EVERY}s" begin="{PULSE_AT}s" '
            f'repeatCount="indefinite"/>')


def breathe(attr, values, dur, begin="0s"):
    n = len(values.split(";"))
    kt = ";".join(f"{i / (n - 1):.3f}" for i in range(n))
    return (f'<animate attributeName="{attr}" values="{values}" keyTimes="{kt}" calcMode="spline" '
            f'keySplines="{";".join([EASE] * (n - 1))}" dur="{dur}" begin="{begin}" repeatCount="indefinite"/>')


# ------------------------------------------------------------------ drawing helpers
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def label(x, y, text, fill="#8a8a8a", anchor="start", size=9):
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{MONO}" font-size="{size}" '
            f'letter-spacing="1.2" fill="{fill}">{esc(text)}</text>')


def card(x, y, w, h, accent=None):
    out = f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{h}" rx="10" fill="#101014" stroke="#1f1f24"/>'
    if accent:
        out += f'<rect x="{x + 1:.1f}" y="{y + 12}" width="2.5" height="{h - 24}" rx="1.2" fill="{accent}"/>'
    return out


def spread(ys, lo, hi, gap):
    """Nudge label baselines apart (keeping their order) so none are closer than `gap`."""
    out = list(ys)
    for i in range(1, len(out)):
        out[i] = max(out[i], out[i - 1] + gap)
    if out and out[-1] > hi:
        out[-1] = hi
        for i in range(len(out) - 2, -1, -1):
            out[i] = min(out[i], out[i + 1] - gap)
    if out and out[0] < lo:
        out[0] = lo
        for i in range(1, len(out)):
            out[i] = max(out[i], out[i - 1] + gap)
    return out


# ------------------------------------------------------------------ render
def build(repos, synced):
    n = len(repos)
    total_mb = sum(r["bytes"] for r in repos) / 1_000_000
    oldest, newest = repos[0], repos[-1]
    lines = ridges(repos)
    r_end = pulse_end(repos)
    sweep = PULSE_SWEEP / PULSE_EVERY
    last = pulse_phase(repos[-1]["mx"], repos[-1]["my"], r_end)
    gone = min(sweep, last + 0.5 / PULSE_EVERY)

    def band_fade(peak):
        """The band dissolves as soon as it has passed the newest repository."""
        return (f'<animate attributeName="stop-opacity" values="{peak};{peak};0;0" '
                f'keyTimes="0;{last:.4f};{gone:.4f};1" dur="{PULSE_EVERY}s" begin="{PULSE_AT}s" '
                f'repeatCount="indefinite"/>')

    d = path_data(lines)
    p = []

    named = [(i, r) for i, r in enumerate(repos) if r["name"] in FLAGSHIPS or i == 0]
    callouts = []
    for i, r in named:
        if i == 0:
            title, what = "First commit", r["name"]
        else:
            title, what = FLAGSHIPS[r["name"]]
        callouts.append({"i": i, "r": r, "title": title, "what": what})

    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-labelledby="idTitle idDesc">')
    p.append('<title id="idTitle">Identity — a fingerprint grown from the work</title>')
    names = ", ".join(f'{c["title"]} ({c["r"]["first"].strftime("%b %Y")})' for c in callouts)
    desc = (f'Kartikeya Yadav, AI/ML engineer and co-founder of Kovidam. A fingerprint whose {n} minutiae are '
            f'his {n} public repositories, oldest at the core ({oldest["first"].strftime("%b %Y")}) and newest at '
            f'the rim ({newest["first"].strftime("%b %Y")}); a light pulse travels outward and lights each one in '
            f'the order it was started. Named points: {names}. {" ".join(LEAD)} {" ".join(l for l in BIO if l)} '
            f'Rules: {"; ".join(t + " — " + " ".join(proof) for t, _, proof in RULES)}. {total_mb:.1f} MB of code. '
            f'Synced {synced.strftime("%Y-%m-%d %H:%M")} {TZ_NAME}.')
    p.append(f'<desc id="idDesc">{esc(desc)}</desc>')

    # ---- defs
    vy = CY - (BTOP - BBOT) / 2
    vr = (BTOP + BBOT) / 2
    mask_box = f'maskUnits="userSpaceOnUse" x="{CX - BX - 20}" y="{CY - BTOP - 20}" width="{2 * BX + 40}" height="{BTOP + BBOT + 40}"'
    p.append(f'''<defs>
    <pattern id="idDots" width="28" height="28" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#141414"/></pattern>
    <filter id="idGlow" x="-250%" y="-250%" width="600%" height="600%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="idSoft" x="-5%" y="-5%" width="110%" height="110%"><feGaussianBlur stdDeviation="1.6" result="b"/><feComponentTransfer in="b" result="g"><feFuncA type="linear" slope="0.55"/></feComponentTransfer><feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="idBloom" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <linearGradient id="idInk" gradientUnits="userSpaceOnUse" x1="{CX - BX}" y1="{CY - BTOP}" x2="{CX + BX}" y2="{CY + BBOT}">
      <stop offset="0" stop-color="{INK[0]}"/><stop offset="0.5" stop-color="{INK[1]}"/><stop offset="1" stop-color="{INK[2]}"/>
    </linearGradient>
    <radialGradient id="idVigGrad" gradientUnits="userSpaceOnUse" cx="{CX}" cy="{vy}" r="{vr}"
      gradientTransform="translate({CX} {vy}) scale({BX / vr:.4f} 1) translate({-CX} {-vy})">
      <stop offset="0.72" stop-color="#fff"/><stop offset="1" stop-color="#000"/>
    </radialGradient>
    <radialGradient id="idRevealGrad"><stop offset="0.9" stop-color="#fff"/><stop offset="1" stop-color="#000"/></radialGradient>
    <radialGradient id="idPulse" gradientUnits="userSpaceOnUse" cx="{CX}" cy="{CY}" r="{REVEAL_R}"
      gradientTransform="translate({CX} {CY}) scale(1 {ASPECT}) translate({-CX} {-CY})">
      <stop offset="0" stop-color="#ede9fe" stop-opacity="0"/><stop offset="0.76" stop-color="#ede9fe" stop-opacity="0"/>
      <stop offset="0.91" stop-color="#f5f3ff" stop-opacity="0.8">{band_fade(0.8)}</stop>
      <stop offset="{PULSE_CREST}" stop-color="#fff" stop-opacity="1">{band_fade(1)}</stop>
      <stop offset="1" stop-color="#fff" stop-opacity="0"/>
      {reveal_r_anim("r", 0, REVEAL_R)}
      <animate attributeName="r" values="0;{r_end:.1f};{r_end:.1f}" keyTimes="0;{sweep:.4f};1" calcMode="spline"
        keySplines="{EASE_PULSE};0 0 1 1" dur="{PULSE_EVERY}s" begin="{PULSE_AT}s" repeatCount="indefinite"/>
    </radialGradient>
    <radialGradient id="idCore"><stop offset="0" stop-color="#a78bfa" stop-opacity="0.35"/><stop offset="1" stop-color="#a78bfa" stop-opacity="0"/></radialGradient>
    <mask id="idRidges" {mask_box}><path d="{d}" fill="none" stroke="#fff" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round"/></mask>
    <mask id="idVig" {mask_box}><rect x="{CX - BX - 20}" y="{CY - BTOP - 20}" width="{2 * BX + 40}" height="{BTOP + BBOT + 40}" fill="url(#idVigGrad)"/></mask>
    <mask id="idReveal" {mask_box}><circle cx="{CX}" cy="{CY}" r="{REVEAL_R}" fill="url(#idRevealGrad)" transform="translate({CX} {CY}) scale(1 {ASPECT}) translate({-CX} {-CY})">{reveal_r_anim("r", 0, REVEAL_R)}</circle></mask>
  </defs>''')

    # ---- frame + header
    p.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="#0a0a0a" stroke="#1f1f1f"/>')
    p.append(f'<rect x="14" y="14" width="{W - 28}" height="{H - 28}" fill="url(#idDots)"/>')
    p.append(label(20, 28, "IDENTITY // LIVE", "#555", size=10))
    p.append(f'<circle cx="{W - 24}" cy="24.5" r="3" fill="#22c55e" filter="url(#idGlow)">{breathe("opacity", "1;0.3;1", "1.8s")}</circle>')
    p.append(label(W - 34, 28, f'{n} PUBLIC REPOS · {total_mb:.1f} MB OF CODE · SYNCED '
                               f'{synced.strftime("%d %b %H:%M").upper()} {TZ_NAME}', "#555", "end", 10))

    # ---- the print
    p.append(f'<ellipse cx="{CX}" cy="{CY}" rx="70" ry="76" fill="url(#idCore)">{breathe("opacity", "0.6;1;0.6", "5s")}</ellipse>')
    # ink and pulse are separate layers so the (static) ink never repaints while the pulse runs
    box = f'x="{CX - BX - 20}" y="{CY - BTOP - 20}" width="{2 * BX + 40}" height="{BTOP + BBOT + 40}"'
    p.append(f'<g mask="url(#idVig)"><g mask="url(#idReveal)"><g filter="url(#idSoft)">'
             f'<rect {box} fill="url(#idInk)" mask="url(#idRidges)" opacity="0.92"/></g></g></g>')
    p.append(f'<g mask="url(#idVig)"><g filter="url(#idBloom)">'
             f'<rect {box} fill="url(#idPulse)" mask="url(#idRidges)"/></g></g>')

    # ---- minutiae: every public repository, lit as the pulse passes
    named_idx = {c["i"] for c in callouts}
    for i, r in enumerate(repos):
        x, y = r["mx"], r["my"]
        sx, sy = CX + x, CY + y
        big = i in named_idx
        ring = 3.4 if big else 2.3
        p.append(f'<g>{appear(reveal_time(x, y), 0.35)}'
                 f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{ring}" fill="#0a0a0a" fill-opacity="0.55" '
                 f'stroke="{"#f5f3ff" if big else "#ddd6fe"}" stroke-width="{1.1 if big else 0.8}" '
                 f'stroke-opacity="{0.95 if big else 0.55}"/>'
                 f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{ring}" fill="none" stroke="#fff" stroke-width="1" opacity="0">'
                 f'{flash("opacity", 0, 0.9, pulse_phase(x, y, r_end))}{flash("r", ring, ring + 5, pulse_phase(x, y, r_end))}</circle>'
                 + (f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="1.2" fill="#fff"/>' if big else "") + '</g>')

    # ---- callouts: two label columns, ordered by height so leaders never cross
    sides = {"L": [], "R": []}
    for c in callouts:
        sides["L" if c["r"]["mx"] < 0 else "R"].append(c)
    for side, items in sides.items():
        items.sort(key=lambda c: c["r"]["my"])
        ys = spread([CY + c["r"]["my"] + 4 for c in items], 100, 440, LABEL_GAP)
        for c, ly in zip(items, ys):
            r = c["r"]
            mx, my = CX + r["mx"], CY + r["my"]
            at = reveal_time(r["mx"], r["my"])
            if side == "L":
                kx, ax, tx, anchor = CX - BX - 18, CX - BX - 30, CX - BX - 38, "end"
            else:
                kx, ax, tx, anchor = CX + BX + 18, CX + BX + 30, CX + BX + 38, "start"
            ang = math.atan2(ly - 4 - my, kx - mx)
            ox, oy = mx + 4.6 * math.cos(ang), my + 4.6 * math.sin(ang)
            phase = pulse_phase(r["mx"], r["my"], r_end)
            length = math.dist((ox, oy), (kx, ly - 4)) + abs(kx - ax) + 1
            p.append(f'<path d="M{ox:.1f},{oy:.1f} L{kx:.1f},{ly - 4:.1f} L{ax:.1f},{ly - 4:.1f}" fill="none" '
                     f'stroke="#c4b5fd" stroke-width="0.8" stroke-opacity="0.55" stroke-dasharray="{length:.1f} {length:.1f}">'
                     f'<animate attributeName="stroke-dashoffset" values="{length:.1f};{length:.1f};0" '
                     f'keyTimes="0;{at / (at + 0.6):.4f};1" '
                     f'dur="{at + 0.6:.2f}s" fill="freeze" calcMode="spline" keySplines="{EASE};{EASE}"/>'
                     f'{flash("stroke-opacity", 0.55, 1, phase, 0.1)}</path>')
            p.append(f'<circle cx="{ax:.1f}" cy="{ly - 4:.1f}" r="1.6" fill="#c4b5fd">{appear(at + 0.45, 0.3)}</circle>')
            when = r["first"].strftime("%b %Y").upper()
            p.append(f'<g>{appear(at + 0.35, 0.5)}'
                     f'<text x="{tx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-family="{SANS}" font-size="12.5" '
                     f'font-weight="700" fill="#ededed">{esc(c["title"])}<tspan font-family="{MONO}" font-size="8.5" '
                     f'font-weight="400" letter-spacing="1" fill="#6b6b75">  {when}'
                     f'{flash("fill", "#6b6b75", "#c4b5fd", phase, 0.12)}</tspan></text>'
                     f'<text x="{tx:.1f}" y="{ly + 15:.1f}" text-anchor="{anchor}" font-family="{SANS}" font-size="10.5" '
                     f'fill="#8a8a93">{esc(c["what"])}</text></g>')

    # ---- legend (corners, like the rhythm clock's)
    p.append(label(22, 52, "POINT = PUBLIC REPO", "#666", size=8))
    p.append(label(22, 64, "first commit at the core", "#555", size=8))
    p.append(label(22, 76, "newest at the rim", "#555", size=8))
    p.append(label(W - 22, 52, "PULSE = TIME", "#666", "end", 8))
    p.append(label(W - 22, 64, "replays every repo", "#555", "end", 8))
    p.append(label(W - 22, 76, "in the order it began", "#555", "end", 8))

    # ---- time axis: the same pulse, read as dates
    t0 = datetime(oldest["first"].year, oldest["first"].month, 1, tzinfo=timezone.utc)
    t1 = month_after(newest["first"])
    span = (t1 - t0).total_seconds()

    def at_x(dt):
        return TL_X0 + (TL_X1 - TL_X0) * (dt - t0).total_seconds() / span

    p.append(f'<line x1="{TL_X0}" y1="{TL_Y}" x2="{TL_X1}" y2="{TL_Y}" stroke="#26262e"/>')
    m = t0
    while m <= t1:
        x, jan = at_x(m), m.month == 1
        p.append(f'<line x1="{x:.1f}" y1="{TL_Y}" x2="{x:.1f}" y2="{TL_Y + (5 if jan else 2.5)}" '
                 f'stroke="{"#4a4a55" if jan else "#2e2e37"}"/>')
        if jan:
            p.append(label(f"{x:.1f}", TL_Y + 15, str(m.year), "#555", "middle", 7.5))
        m = month_after(m)
    p.append(label(TL_X0 - 8, TL_Y + 3, oldest["first"].strftime("%b %Y").upper(), "#666", "end", 7.5))
    p.append(label(TL_X1 + 8, TL_Y + 3, newest["first"].strftime("%b %Y").upper(), "#666", "start", 7.5))
    stops = []
    for i, r in enumerate(repos):
        x, big = at_x(r["first"]), i in named_idx
        ph = pulse_phase(r["mx"], r["my"], r_end)
        stops.append((ph, x))
        rest = 0.9 if big else 0.5
        p.append(f'<line x1="{x:.1f}" y1="{TL_Y - (10 if big else 6)}" x2="{x:.1f}" y2="{TL_Y - 1.5}" '
                 f'stroke="{"#ddd6fe" if big else "#8b5cf6"}" stroke-width="1.1" stroke-opacity="{rest}">'
                 f'{flash("stroke-opacity", rest, 1, ph)}</line>')
    # the cursor glides from date to date exactly as the pulse meets each minutia
    phs = [ph for ph, _ in stops]
    for q in range(1, len(phs)):
        phs[q] = max(phs[q], phs[q - 1] + 0.0005)
    xs = [x for _, x in stops]
    kt = ";".join(f"{v:.4f}" for v in [0] + phs + [1])
    vals = ";".join(f"{v:.1f}" for v in [xs[0]] + xs + [xs[-1]])
    p.append(f'<circle cx="{xs[0]:.1f}" cy="{TL_Y}" r="2.6" fill="#f5f3ff" filter="url(#idGlow)" opacity="0">'
             f'<animate attributeName="cx" values="{vals}" keyTimes="{kt}" dur="{PULSE_EVERY}s" begin="{PULSE_AT}s" '
             f'repeatCount="indefinite"/>'
             f'<animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes="0;{max(0.0001, phs[0] - 0.02):.4f};'
             f'{phs[0]:.4f};{phs[-1]:.4f};{min(0.9999, phs[-1] + 0.05):.4f};1" dur="{PULSE_EVERY}s" '
             f'begin="{PULSE_AT}s" repeatCount="indefinite"/></circle>')

    # ---- words
    ty = 528
    p.append(f'<line x1="20" y1="{ty - 18}" x2="{W - 20}" y2="{ty - 18}" stroke="#18181d"/>')
    for k, line in enumerate(LEAD):
        p.append(f'<text x="40" y="{ty + 30 + k * 33}" font-family="{SANS}" font-size="27" font-weight="700" '
                 f'letter-spacing="-0.3" fill="#f2f2f2">{esc(line)}</text>')
    by = ty + 100
    for line in BIO:
        if line:
            p.append(f'<text x="40" y="{by}" font-family="{SANS}" font-size="13.5" fill="#a1a1aa">{esc(line)}</text>')
        by += 20 if line else 10

    gx, gy, gw, gh, gap = 452, ty + 6, (W - 20 - 452 - 10) / 2, 100, 10
    for k, (title, accent, proof) in enumerate(RULES):
        x, y = gx + (k % 2) * (gw + gap), gy + (k // 2) * (gh + gap)
        p.append(card(x, y, gw, gh, accent))
        p.append(f'<text x="{x + 16:.1f}" y="{y + 24}" font-family="{SANS}" font-size="13" font-weight="700" '
                 f'fill="#f2f2f2">{esc(title)}</text>')
        for q, line in enumerate(proof):
            p.append(f'<text x="{x + 16:.1f}" y="{y + 47 + q * 14.5}" font-family="{SANS}" font-size="10.5" '
                     f'fill="#8a8a93">{esc(line)}</text>')

    p.append("</svg>")
    return "\n".join(p)


def month_after(dt):
    return datetime(dt.year + (dt.month == 12), dt.month % 12 + 1, 1, tzinfo=timezone.utc)


def reveal_r_anim(attr, frm, to):
    """The print develops outward from the core once, then holds."""
    end = REVEAL_AT + REVEAL_DUR
    return (f'<animate attributeName="{attr}" values="{frm};{frm};{to}" keyTimes="0;{REVEAL_AT / end:.4f};1" '
            f'calcMode="spline" keySplines="0 0 1 1;{EASE_REVEAL}" dur="{end:.2f}s" fill="freeze"/>')


def main():
    try:
        repos = fetch()
        if len(repos) < 3:
            raise FetchError(f"only {len(repos)} public repositories came back — too few to draw a print")
        repos.sort(key=lambda r: (r["first"], r["name"].lower()))
        svg = build(layout(repos), datetime.now(TZ))
    except Exception as e:  # noqa: BLE001 - deliberate: never let this step fail the job
        print(f"WARNING: identity generation failed, leaving the existing file untouched: {e}", file=sys.stderr)
        return 0
    if "<svg" not in svg or "</svg>" not in svg:
        print("WARNING: generated SVG failed a basic sanity check. Leaving existing file untouched.", file=sys.stderr)
        return 0
    tmp_path = OUT_PATH + ".tmp"
    try:
        os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(svg)
        os.replace(tmp_path, OUT_PATH)
        print(f"Wrote {OUT_PATH} ({len(svg):,} bytes)")
    except OSError as e:
        print(f"WARNING: could not write {OUT_PATH}: {e}", file=sys.stderr)
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
