#!/usr/bin/env python3
"""Generate assets/identity-core.svg — the section 02 "Identity" plate: the
Kartikeya System, a solar system grown from the work itself, above a short
bio and the four rules the work keeps.

Everything in orbit is real:

  - one planet per owned, public, non-fork repository. Its orbit is the
    period its oldest commit on the default branch falls in (falling back to
    the repo's creation date): earlier years each get a ring, and the
    current year gets one ring per quarter, so the newest work is on the
    outer rings. Its size is its bytes of code on a log scale, and its
    colour is the kind of system it is (curated below, slate if unknown).
  - planets are born in the order their repositories were started, then
    keep orbiting. Orbits are tilted ellipses; a planet is drawn behind the
    star on the far half of its orbit and in front of it on the near half,
    and grows slightly as it comes toward the viewer.
  - the named flagships carry their names on the near half of the orbit.
  - the header numbers (worlds, bytes of code, first commit) are live.

The bio and the four rules are curated copy. Every rule names the
repositories it was shipped in; nothing there is a number or a claim the
repositories do not back up.

SVG notes (see generate_signal.py): GitHub strips <script> and inline <style>,
so all motion is SMIL, and nothing uses <use>/<mpath>: every orbit carries
its own path. url(#id) paint, mask and filter references are fine. Anything
readable starts visible, and every moving body sits at its real starting
position, so a renderer that ignores SMIL shows a finished still frame.

Local preview without the API: set IDENTITY_FIXTURE to a JSON list of
{"name", "first", "bytes"} repositories and the script renders from that file.
Set IDENTITY_DUMP to a path to save the fetched list in that same format.

Never-fail contract: this script always exits 0. Any problem is logged to
stderr and the output file is left exactly as it was.
"""
import json
import math
import os
import random
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
# Pin "now" for reproducible local previews (ISO timestamp); CI leaves it unset.
NOW = os.environ.get("IDENTITY_NOW", "")

TZ = timezone(timedelta(hours=5, minutes=30))
TZ_NAME = "IST"

W, H = 900, 700
MONO = "ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace"
SANS = "-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif"
EASE = "0.42 0 0.58 1"

# ---- the system
CX, CY = 450, 206           # the star
TILT = 0.30                 # orbit ellipses: ry = rx * TILT
RX_IN, RX_OUT = 96, 386     # innermost and outermost orbit
PERIODS = [15, 21, 28, 36, 45, 55]   # seconds per orbit, inside out
MAX_RINGS = 6
DEPTH_STEPS = 24

KINDS = {
    "agentic": ("#22d3ee", "agentic systems"),
    "intel": ("#a78bfa", "intelligence & ML"),
    "tools": ("#fbbf24", "developer tools"),
    "product": ("#f472b6", "products & web"),
    "meta": ("#e2e8f0", "this profile"),
    "other": ("#94a3b8", "other"),
}
KIND = {
    "Sovereign-On_Premise-Agentic-AI-Workbench": "agentic", "Agent_that_act-Hackathon": "agentic",
    "Wispr_goa_task": "agentic", "multi-layer_orchestation": "agentic", "agent--flow": "agentic",
    "Multimodel-governance-B2A": "agentic",
    "Multimodal-Data-Management-Pipeline-for-RAG-Ready-Systems": "intel", "Kovidam-Skill-Graph": "intel",
    "kovidam-AI-Interview": "intel", "RL-model-Negotiation": "intel", "Financial-Health-Score": "intel",
    "ai-image-classifier": "intel", "AI-Video-Editor": "intel", "Reinforce_Club-SST": "intel",
    "Math-EDA": "intel", "Full-Agentic-AI-basics-to-advance-": "intel",
    "JKY-Radar": "tools", "jky-terminal": "tools", "my-localmcp": "tools", "codecrafters-shell-java": "tools",
    "Linux-Lab-Assignment-BITS": "tools", "bits-cli-assignment": "tools",
    "JKY-Folder": "product", "2nd-Year-MERN-P_S": "product", "AI-Businesses": "product", "GitVeda": "product",
    "Agentra-Website": "product", "blood-group-donor": "product", "Cardano-BlockPhantom": "product",
    "Weather-App": "product", "Student-Dost": "product", "Soundboard": "product", "kartikeya-portfolio": "product",
    "Portfolio": "product", "Scaler-1st-Year-Assignments": "product", "Scaler-OSC-Projects": "product",
    "project_ideas--AI-ML-CLUB": "product",
    "kartikeyajay2006": "meta",
}
# Named planets. Positions still come from the data; only the names are curated.
FLAGSHIPS = {
    "Sovereign-On_Premise-Agentic-AI-Workbench": "AEGIS",
    "Agent_that_act-Hackathon": "ForgeSRE",
    "Wispr_goa_task": "EraseOps",
    "jky-terminal": "JKY Terminal",
    "JKY-Radar": "JKY-Radar",
    "Kovidam-Skill-Graph": "Kovidam",
    "multi-layer_orchestation": "Chakraview",
    "JKY-Folder": "JKY-Folder",
    "Multimodal-Data-Management-Pipeline-for-RAG-Ready-Systems": "Evidence Console",
}

LEAD = ["I build AI agents", "that act — and prove it."]
BIO = [
    "AI/ML engineer and co-founder of Kovidam, an AI talent-intelligence",
    "platform. I build systems end to end: the model, the agents that",
    "use it, the backend underneath and the product on top.",
    "",
    "Architected, not prompted — real data pipelines, real evaluation,",
    "and a person in charge of anything that can’t be undone.",
]
RULES = [
    ("Prove it worked", "#a78bfa",
     ["ForgeSRE checks recovery against thresholds; EraseOps", "rescans until nothing personal is left."]),
    ("A human signs off", "#f472b6",
     ["ForgeSRE stops before a production rollback; EraseOps", "waits for approval of one exact plan hash."]),
    ("Show the source", "#22d3ee",
     ["The evidence console links every answer to the exact", "video second or PDF page it came from."]),
    ("Run where the data lives", "#4ade80",
     ["AEGIS runs on one machine with no outbound calls;", "JKY Terminal and my-localmcp are local-first."]),
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


# ------------------------------------------------------------------ the system
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def breathe(attr, values, dur, begin="0s"):
    n = len(values.split(";"))
    kt = ";".join(f"{i / (n - 1):.3f}" for i in range(n))
    return (f'<animate attributeName="{attr}" values="{values}" keyTimes="{kt}" calcMode="spline" '
            f'keySplines="{";".join([EASE] * (n - 1))}" dur="{dur}" begin="{begin}" repeatCount="indefinite"/>')


def _mix(hex_a, hex_b, k):
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * k):02x}" for x, y in zip(a, b))


def rings_for(repos):
    """Earlier years get one ring each; the newest year gets one ring per quarter
    up to the newest repository. Oldest rings merge if there are more than MAX_RINGS."""
    newest = max(r["first"] for r in repos)
    y = newest.year
    rings = []
    for yy in sorted({r["first"].year for r in repos if r["first"].year < y}):
        rings.append({"label": str(yy), "lo": datetime(yy, 1, 1, tzinfo=timezone.utc),
                      "hi": datetime(yy + 1, 1, 1, tzinfo=timezone.utc)})
    for q in range(1, (newest.month - 1) // 3 + 2):
        lo = datetime(y, 3 * q - 2, 1, tzinfo=timezone.utc)
        hi = datetime(y + (q == 4), 1 if q == 4 else 3 * q + 1, 1, tzinfo=timezone.utc)
        rings.append({"label": f"Q{q} ’{y % 100:02d}", "lo": lo, "hi": hi})
    while len(rings) > MAX_RINGS:
        a, b = rings[0], rings[1]
        rings[:2] = [{"label": f"≤ {b['label']}", "lo": a["lo"], "hi": b["hi"]}]
    k = len(rings)
    for i, ring in enumerate(rings):
        ring["rx"] = RX_IN + (RX_OUT - RX_IN) * (i / (k - 1) if k > 1 else 0.5)
        ring["ry"] = ring["rx"] * TILT
        ring["T"] = PERIODS[min(i, len(PERIODS) - 1)]
        ring["members"] = [r for r in repos if ring["lo"] <= r["first"] < ring["hi"]]
    rings[0]["members"] = [r for r in repos if r["first"] < rings[0]["hi"]]  # anything older lands inside
    return rings


def ellipse_track(rx, ry, steps=720):
    """Points along the orbit, starting at the right-hand end and running clockwise on
    screen (near half first), with cumulative arc length — so motion keyed by time can
    be matched to animateMotion's constant-speed ("paced") travel."""
    pts, cum = [], [0.0]
    for i in range(steps + 1):
        t = 2 * math.pi * i / steps
        pts.append((CX + rx * math.cos(t), CY + ry * math.sin(t)))
        if i:
            cum.append(cum[-1] + math.dist(pts[-1], pts[-2]))
    return pts, cum


def at_fraction(pts, cum, f):
    target = (f % 1.0) * cum[-1]
    lo, hi = 0, len(cum) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    i = max(1, lo)
    seg = cum[i] - cum[i - 1] or 1.0
    k = (target - cum[i - 1]) / seg
    (x0, y0), (x1, y1) = pts[i - 1], pts[i]
    return x0 + (x1 - x0) * k, y0 + (y1 - y0) * k


def orbit_path(rx, ry, ox, oy):
    """Four quarter arcs from the right-hand end, clockwise, shifted by (-ox, -oy) so the
    planet's own translate(ox, oy) puts it on the orbit even without SMIL."""
    def pt(x, y):
        return f"{x - ox:.1f},{y - oy:.1f}"
    return (f"M{pt(CX + rx, CY)} A{rx:.1f},{ry:.1f} 0 0 1 {pt(CX, CY + ry)} "
            f"A{rx:.1f},{ry:.1f} 0 0 1 {pt(CX - rx, CY)} A{rx:.1f},{ry:.1f} 0 0 1 {pt(CX, CY - ry)} "
            f"A{rx:.1f},{ry:.1f} 0 0 1 {pt(CX + rx, CY)}")


def planet_r(nbytes):
    return min(9.5, 2.3 + 1.75 * max(0.0, math.log10(max(nbytes, 1)) - 3))


def build(repos, synced):
    rnd = random.Random(38)
    n = len(repos)
    total_mb = sum(r["bytes"] for r in repos) / 1_000_000
    oldest = repos[0]
    rings = rings_for(repos)
    biggest = max(repos, key=lambda r: r["bytes"])["name"]
    birth_rank = {r["name"]: i for i, r in enumerate(repos)}
    p = []

    named = [FLAGSHIPS[r["name"]] for r in repos if r["name"] in FLAGSHIPS]
    rules_txt = "; ".join(t + ": " + " ".join(lines) for t, _, lines in RULES)
    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-labelledby="idTitle idDesc">')
    p.append('<title id="idTitle">Identity — the Kartikeya System</title>')
    p.append(f'<desc id="idDesc">A solar system grown from Kartikeya Yadav\'s public work: {n} public repositories '
             f'({total_mb:.1f} MB of code) orbit a central star, one planet each, sized by code and coloured by kind. '
             f'Orbits are the periods the work began in, from {esc(rings[0]["label"])} on the innermost ring to '
             f'{esc(rings[-1]["label"])} on the outermost; the planets are born in the order their repositories were '
             f'started and then keep orbiting. Named: {esc(", ".join(named))}. Below: {esc(" ".join(LEAD))} '
             f'{esc(" ".join(l for l in BIO if l))} Four rules: '
             f'{esc(rules_txt)}.</desc>')

    grads = []
    for kind, (col, _) in KINDS.items():
        grads.append(f'<radialGradient id="pl_{kind}" cx="0.5" cy="0.5" r="0.5" fx="0.32" fy="0.28">'
                     f'<stop offset="0" stop-color="{_mix(col, "#ffffff", 0.6)}"/>'
                     f'<stop offset="0.45" stop-color="{col}"/>'
                     f'<stop offset="1" stop-color="{_mix(col, "#05010d", 0.78)}"/></radialGradient>')
    p.append(f'''<defs>
    <clipPath id="idFrame"><rect x="0" y="0" width="{W}" height="{H}" rx="14"/></clipPath>
    <linearGradient id="idSpace" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#04020c"/><stop offset="0.55" stop-color="#0a0518"/><stop offset="1" stop-color="#06030f"/></linearGradient>
    <radialGradient id="idNebA" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#7c3aed" stop-opacity="0.32"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>
    <radialGradient id="idNebB" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#0ea5e9" stop-opacity="0.22"/><stop offset="1" stop-color="#0ea5e9" stop-opacity="0"/></radialGradient>
    <radialGradient id="idNebC" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#db2777" stop-opacity="0.2"/><stop offset="1" stop-color="#db2777" stop-opacity="0"/></radialGradient>
    <radialGradient id="idDisc" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#8b5cf6" stop-opacity="0.2"/><stop offset="0.55" stop-color="#6d28d9" stop-opacity="0.07"/><stop offset="1" stop-color="#6d28d9" stop-opacity="0"/></radialGradient>
    <radialGradient id="idGlow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#c4b5fd" stop-opacity="0.55"/><stop offset="0.4" stop-color="#8b5cf6" stop-opacity="0.2"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>
    <radialGradient id="idCorona" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#ffffff" stop-opacity="0.95"/><stop offset="0.38" stop-color="#ede9fe" stop-opacity="0.75"/><stop offset="0.7" stop-color="#a78bfa" stop-opacity="0.32"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>
    <radialGradient id="idCore" cx="0.5" cy="0.5" r="0.5" fx="0.4" fy="0.36"><stop offset="0" stop-color="#ffffff"/><stop offset="0.7" stop-color="#f5f3ff"/><stop offset="1" stop-color="#c4b5fd"/></radialGradient>
    <linearGradient id="idFlare" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff" stop-opacity="0"/><stop offset="0.5" stop-color="#ffffff" stop-opacity="0.45"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient>
    <linearGradient id="idRule" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#8b5cf6" stop-opacity="0"/><stop offset="0.2" stop-color="#8b5cf6" stop-opacity="0.55"/><stop offset="0.8" stop-color="#22d3ee" stop-opacity="0.55"/><stop offset="1" stop-color="#22d3ee" stop-opacity="0"/></linearGradient>
    <linearGradient id="idLeadInk" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff"/><stop offset="0.55" stop-color="#ddd6fe"/><stop offset="1" stop-color="#67e8f9"/></linearGradient>
    <linearGradient id="idTail" gradientUnits="userSpaceOnUse" x1="-70" y1="0" x2="0" y2="0"><stop offset="0" stop-color="#c4b5fd" stop-opacity="0"/><stop offset="1" stop-color="#ffffff"/></linearGradient>
    <filter id="idSoft" x="-150%" y="-150%" width="400%" height="400%"><feGaussianBlur stdDeviation="3"/></filter>
    <filter id="idGlowF" x="-150%" y="-150%" width="400%" height="400%"><feGaussianBlur stdDeviation="1.8" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    {"".join(grads)}
  </defs>''')
    p.append('<g clip-path="url(#idFrame)">')
    p.append(f'<rect width="{W}" height="{H}" fill="url(#idSpace)"/>')

    # ---- deep space: nebulae drifting, stars twinkling, comets
    for gid, ex, ey, erx, ery, dx in (("idNebA", 170, 110, 260, 130, 14), ("idNebB", 760, 150, 230, 140, -12),
                                      ("idNebC", 260, 340, 260, 90, 10), ("idNebA", 700, 360, 220, 80, -8)):
        p.append(f'<ellipse cx="{ex}" cy="{ey}" rx="{erx}" ry="{ery}" fill="url(#{gid})">'
                 f'<animateTransform attributeName="transform" type="translate" values="0,0;{dx},{dx / 3:.1f};0,0" '
                 f'dur="{24 + abs(dx)}s" calcMode="spline" keyTimes="0;0.5;1" keySplines="{EASE};{EASE}" '
                 f'repeatCount="indefinite"/></ellipse>')
    for i in range(110):
        x, y = rnd.uniform(8, W - 8), rnd.uniform(8, 392)
        r = rnd.choice((0.45, 0.55, 0.7, 0.85, 1.1))
        tw = ""
        if i % 3 == 0:
            tw = (f'<animate attributeName="opacity" values="0.9;0.12;0.9" dur="{rnd.uniform(2.2, 6):.1f}s" '
                  f'begin="{rnd.uniform(0, 5):.1f}s" repeatCount="indefinite"/>')
        tint = rnd.choice(("#ffffff", "#e0e7ff", "#fce7f3", "#cffafe"))
        p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{tint}" opacity="{rnd.uniform(0.3, 0.85):.2f}">{tw}</circle>')
    for path, dur, begin in (("M-60,46 C260,76 600,14 980,64", 11, -2), ("M980,338 C660,306 300,368 -60,322", 15, -9)):
        p.append(f'<g opacity="0"><set attributeName="opacity" to="1" begin="0s"/>'
                 f'<animateMotion path="{path}" dur="{dur}s" begin="{begin}s" rotate="auto" repeatCount="indefinite"/>'
                 f'<line x1="-70" y1="0" x2="0" y2="0" stroke="url(#idTail)" stroke-width="2" stroke-linecap="round"/>'
                 f'<circle r="2.3" fill="#ffffff" filter="url(#idGlowF)"/></g>')

    # ---- the orbital plane
    p.append(f'<ellipse cx="{CX}" cy="{CY}" rx="{RX_OUT + 46}" ry="{(RX_OUT + 46) * TILT:.1f}" fill="url(#idDisc)"/>')
    for ring in rings:  # far halves of the orbits, behind everything
        rx, ry = ring["rx"], ring["ry"]
        p.append(f'<path d="M{CX + rx:.1f},{CY} A{rx:.1f},{ry:.1f} 0 0 0 {CX - rx:.1f},{CY}" fill="none" '
                 f'stroke="#7c3aed" stroke-width="1" stroke-dasharray="2 5" opacity="0.45"/>')

    # ---- planets, built once per orbit and drawn twice: far copies under the star, near copies over it
    far, near = [], []
    for ri, ring in enumerate(rings):
        members = sorted(ring["members"], key=lambda r: r["first"])
        if not members:
            continue
        rx, ry, T = ring["rx"], ring["ry"], ring["T"]
        pts, cum = ellipse_track(rx, ry)
        depth = []
        for s in range(DEPTH_STEPS + 1):
            _, y = at_fraction(pts, cum, s / DEPTH_STEPS)
            depth.append((y - CY) / ry)            # -1 far, +1 near
        kt = ";".join(f"{s / DEPTH_STEPS:.4f}" for s in range(DEPTH_STEPS + 1))
        for j, repo in enumerate(members):
            phase = ((j + 0.5) / len(members) + ri * 0.137) % 1.0
            x0, y0 = at_fraction(pts, cum, phase)
            kind = KIND.get(repo["name"], "other")
            col = KINDS[kind][0]
            r0 = planet_r(repo["bytes"])
            radii = ";".join(f"{r0 * (0.8 + 0.2 * (d + 1) / 2):.2f}" for d in depth)
            r_now = r0 * (0.8 + 0.2 * ((y0 - CY) / ry + 1) / 2)
            begin = f"{-phase * T:.3f}s"
            birth = 0.35 + 3.4 * birth_rank[repo["name"]] / max(1, n - 1)
            path = orbit_path(rx, ry, x0, y0)
            name = FLAGSHIPS.get(repo["name"])

            def body(is_near):
                b = []
                if name:
                    b.append(f'<circle r="{r0 * 2.3:.1f}" fill="{col}" opacity="0.28" filter="url(#idSoft)"/>')
                if repo["name"] == biggest:  # the heaviest world wears a ring
                    b.append(f'<ellipse rx="{r0 * 2.15:.1f}" ry="{r0 * 0.6:.1f}" fill="none" stroke="{_mix(col, "#ffffff", 0.45)}" '
                             f'stroke-width="1.3" opacity="0.75" transform="rotate(-16)"/>')
                b.append(f'<circle r="{r_now:.2f}" fill="url(#pl_{kind})">'
                         f'<animate attributeName="r" values="{radii}" keyTimes="{kt}" dur="{T}s" begin="{begin}" '
                         f'repeatCount="indefinite"/></circle>')
                if repo["name"] == biggest:
                    b.append(f'<path d="M{-r0 * 2.07:.1f},{r0 * 0.6:.1f} A{r0 * 2.15:.1f},{r0 * 0.6:.1f} 0 0 0 {r0 * 2.07:.1f},{-r0 * 0.6:.1f}" '
                             f'fill="none" stroke="{_mix(col, "#ffffff", 0.45)}" stroke-width="1.3" opacity="0.85" '
                             f'transform="rotate(-16)"/>')
                # birth flash, once, in the order the work began
                b.append(f'<circle r="0" fill="none" stroke="{col}" stroke-width="1.4" opacity="0">'
                         f'<animate attributeName="r" values="{r0:.1f};{r0 + 18:.1f}" dur="1s" begin="{birth:.2f}s" fill="freeze"/>'
                         f'<animate attributeName="opacity" values="0.95;0" dur="1s" begin="{birth:.2f}s" fill="freeze"/></circle>')
                if name and is_near:
                    b.append(f'<text x="{r0 + 6:.1f}" y="3.6" font-family="{SANS}" font-size="10.5" font-weight="700" '
                             f'fill="#f5f3ff" stroke="#05010d" stroke-width="3" stroke-linejoin="round" '
                             f'paint-order="stroke">{esc(name)}</text>')
                return "".join(b)

            near_now = (y0 - CY) >= 0
            for is_near in (False, True):
                inner = body(is_near) if is_near else '<g opacity="0.78">' + body(is_near) + '</g>'
                vis = "1;0" if is_near else "0;1"
                base_vis = 1 if near_now == is_near else 0
                g = (f'<g><animate attributeName="opacity" values="0;0;1" '
                     f'keyTimes="0;{birth / (birth + 0.5):.3f};1" dur="{birth + 0.5:.2f}s" fill="freeze"/>'
                     f'<g transform="translate({x0:.1f},{y0:.1f})" opacity="{base_vis}">'
                     f'<animate attributeName="opacity" values="{vis}" keyTimes="0;0.5" calcMode="discrete" '
                     f'dur="{T}s" begin="{begin}" repeatCount="indefinite"/>'
                     f'<animateMotion path="{path}" dur="{T}s" begin="{begin}" repeatCount="indefinite"/>'
                     f'{inner}</g></g>')
                (near if is_near else far).append((ri, g))
    for _, g in sorted(far, key=lambda t: -t[0]):   # farthest orbit first
        p.append(g)

    # ---- the star
    p.append(f'<circle cx="{CX}" cy="{CY}" r="128" fill="url(#idGlow)">{breathe("r", "120;134;120", "6s")}</circle>')
    p.append(f'<g><animateTransform attributeName="transform" type="rotate" from="0 {CX} {CY}" to="360 {CX} {CY}" '
             f'dur="70s" repeatCount="indefinite"/>'
             f'<ellipse cx="{CX}" cy="{CY}" rx="124" ry="1.3" fill="url(#idFlare)"/>'
             f'<ellipse cx="{CX}" cy="{CY}" rx="82" ry="1.3" fill="url(#idFlare)" transform="rotate(90 {CX} {CY})" opacity="0.8"/>'
             f'<ellipse cx="{CX}" cy="{CY}" rx="74" ry="1" fill="url(#idFlare)" transform="rotate(45 {CX} {CY})" opacity="0.6"/>'
             f'<ellipse cx="{CX}" cy="{CY}" rx="74" ry="1" fill="url(#idFlare)" transform="rotate(-45 {CX} {CY})" opacity="0.6"/></g>')
    p.append(f'<circle cx="{CX}" cy="{CY}" r="38" fill="url(#idCorona)">{breathe("r", "35;41;35", "3.6s")}</circle>')
    p.append(f'<circle cx="{CX}" cy="{CY}" r="17" fill="url(#idCore)"/>')
    p.append(f'<text x="{CX}" y="{CY + 4.3}" text-anchor="middle" font-family="{SANS}" font-size="12" font-weight="800" '
             f'letter-spacing="0.5" fill="#3b0764">KY</text>')
    # a pulse rippling out across the orbital plane
    for begin in ("0s", "3s"):
        p.append(f'<ellipse cx="{CX}" cy="{CY}" rx="20" ry="6" fill="none" stroke="#c4b5fd" stroke-width="1.2" opacity="0">'
                 f'<animate attributeName="rx" values="20;{RX_OUT + 40}" dur="6s" begin="{begin}" repeatCount="indefinite"/>'
                 f'<animate attributeName="ry" values="6;{(RX_OUT + 40) * TILT:.1f}" dur="6s" begin="{begin}" repeatCount="indefinite"/>'
                 f'<animate attributeName="opacity" values="0.6;0" dur="6s" begin="{begin}" repeatCount="indefinite"/></ellipse>')

    # near halves of the orbits, then the near planets over everything
    for ring in rings:
        rx, ry = ring["rx"], ring["ry"]
        p.append(f'<path d="M{CX - rx:.1f},{CY} A{rx:.1f},{ry:.1f} 0 0 0 {CX + rx:.1f},{CY}" fill="none" '
                 f'stroke="#a78bfa" stroke-width="1.1" opacity="0.55"/>')
    for _, g in sorted(near, key=lambda t: t[0]):   # nearest orbit last
        p.append(g)
    for ring in rings:
        p.append(f'<text x="{CX + ring["rx"] + 6:.1f}" y="{CY + 3.5}" font-family="{MONO}" font-size="8.5" '
                 f'letter-spacing="0.8" fill="#c4b5fd" opacity="0.8">{esc(ring["label"])}</text>')

    # ---- HUD
    p.append(f'<text x="24" y="32" font-family="{MONO}" font-size="10" letter-spacing="1.6" fill="#c4b5fd" opacity="0.9">'
             f'IDENTITY // THE KARTIKEYA SYSTEM</text>')
    p.append(f'<circle cx="{W - 24}" cy="28.5" r="3" fill="#22c55e" filter="url(#idGlowF)">{breathe("opacity", "1;0.3;1", "1.8s")}</circle>')
    p.append(f'<text x="{W - 34}" y="32" text-anchor="end" font-family="{MONO}" font-size="10" letter-spacing="1.4" '
             f'fill="#c4b5fd" opacity="0.9">{n} WORLDS · {total_mb:.1f} MB OF CODE · SINCE '
             f'{oldest["first"].strftime("%b %Y").upper()} · SYNCED {synced.strftime("%d %b %H:%M").upper()} {TZ_NAME}</text>')
    ly = 380
    lx = 24
    for kind in ("agentic", "intel", "tools", "product", "meta"):
        col, lab = KINDS[kind]
        p.append(f'<circle cx="{lx + 4}" cy="{ly - 3.2}" r="4" fill="url(#pl_{kind})"/>')
        p.append(f'<text x="{lx + 13}" y="{ly}" font-family="{MONO}" font-size="9" fill="#cbd5e1" opacity="0.85">{esc(lab)}</text>')
        lx += 13 + len(lab) * 5.45 + 18
    p.append(f'<text x="24" y="50" font-family="{MONO}" font-size="8.5" letter-spacing="1" fill="#8b7fb8">'
             f'ONE PLANET = ONE PUBLIC REPO · ORBIT = WHEN IT BEGAN · SIZE = ITS CODE</text>')

    # ---- who runs this system
    p.append(f'<line x1="24" y1="398" x2="{W - 24}" y2="398" stroke="url(#idRule)"/>')
    p.append(f'<text x="32" y="428" font-family="{MONO}" font-size="9.5" letter-spacing="1.8" fill="#a78bfa">'
             f'AT THE CENTRE · KARTIKEYA YADAV</text>')
    for k, line in enumerate(LEAD):
        p.append(f'<text x="30" y="{466 + k * 37}" font-family="{SANS}" font-size="32" font-weight="800" '
                 f'letter-spacing="-0.6" fill="url(#idLeadInk)">{esc(line)}</text>')
    yy = 540
    for line in BIO:
        if not line:
            yy += 8
            continue
        p.append(f'<text x="32" y="{yy}" font-family="{SANS}" font-size="12.5" fill="#a1a1aa">{esc(line)}</text>')
        yy += 19
    chips = ["AI/ML ENGINEER", "CO-FOUNDER · KOVIDAM", "AI-ML CLUB · AI LEAD"]
    cx_ = 32
    for chip in chips:
        cw = len(chip) * 5.6 + 18
        p.append(f'<rect x="{cx_:.1f}" y="{H - 52}" width="{cw:.1f}" height="19" rx="9.5" fill="#120a24" stroke="#4c1d95"/>')
        p.append(f'<text x="{cx_ + 9:.1f}" y="{H - 39}" font-family="{MONO}" font-size="8.5" letter-spacing="0.6" '
                 f'fill="#ddd6fe">{esc(chip)}</text>')
        cx_ += cw + 7

    rx0 = 512
    p.append(f'<text x="{rx0}" y="428" font-family="{MONO}" font-size="9.5" letter-spacing="1.8" fill="#22d3ee">'
             f'THE FOUR LAWS OF THIS SYSTEM</text>')
    for k, (title, col, lines) in enumerate(RULES):
        y = 446 + k * 60
        ox, oy = rx0 + 10, y + 6
        p.append(f'<circle cx="{ox}" cy="{oy}" r="9" fill="none" stroke="{col}" stroke-width="1" opacity="0.45"/>')
        p.append(f'<circle cx="{ox}" cy="{oy}" r="2.6" fill="{col}" filter="url(#idGlowF)"/>')
        p.append(f'<circle r="2" fill="#ffffff" cx="0" cy="0" transform="translate({ox + 9},{oy})" opacity="0">'
                 f'<set attributeName="opacity" to="1" begin="0s"/>'
                 f'<animateMotion path="M0,0 A9,9 0 1 1 -18,0 A9,9 0 1 1 0,0" dur="{3.2 + k * 0.7:.1f}s" '
                 f'repeatCount="indefinite"/></circle>')
        p.append(f'<text x="{rx0 + 30}" y="{y + 11}" font-family="{SANS}" font-size="14" font-weight="700" '
                 f'fill="#f5f3ff"><tspan font-family="{MONO}" font-size="9.5" font-weight="400" fill="{col}" '
                 f'letter-spacing="1">{k + 1:02d}  </tspan>{esc(title)}</text>')
        for m, line in enumerate(lines):
            p.append(f'<text x="{rx0 + 30}" y="{y + 29 + m * 14.5}" font-family="{SANS}" font-size="11" '
                     f'fill="#a1a1aa">{esc(line)}</text>')

    p.append('</g>')
    p.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="#2a1650"/>')
    p.append("</svg>")
    return "\n".join(p)


def main():
    try:
        repos = fetch()
        if len(repos) < 3:
            raise FetchError(f"only {len(repos)} public repositories came back — too few to draw a system")
        repos.sort(key=lambda r: (r["first"], r["name"].lower()))
        synced = datetime.fromisoformat(NOW).astimezone(TZ) if NOW else datetime.now(TZ)
        svg = build(repos, synced)
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
