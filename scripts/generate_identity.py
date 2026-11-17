#!/usr/bin/env python3
"""Generate assets/identity-core.svg — the section 02 "Identity" plate: a
fingerprint grown from the work itself, beside who I am and the four laws.

The print is real data. One continuous whorl ridge is the last year of my GitHub
contributions -- the same merged calendar Commit City is built from -- with the
core a year ago and the edge today. Every day owns an equal stretch of the
ridge, and its ink is as thick and bright as that day's contributions; quiet
days are a faint hairline. The six biggest days are ringed as minutiae, the
largest labelled. The print is signed with the SHA-256 of the date:count list
it was drawn from, so it can be reproduced from public data.

A scanner sweeps the print (a bright copy of the ridge seen through a moving
band), "PRINT VERIFIED" flashes, and the four laws tick one by one; each law
names the repositories it was shipped in. The header numbers are live.

SVG notes (see generate_signal.py): GitHub strips <script> and inline <style>,
so all motion is SMIL, and nothing uses <use>/<mpath>. Anything readable starts
visible, so a renderer that ignores SMIL shows a finished still frame.

Local preview without the API: set IDENTITY_FIXTURE to a JSON list of
{"name", "first", "bytes"} repositories and the script renders from that file.
Set IDENTITY_DUMP to a path to save the fetched list in that same format.

Never-fail contract: this script always exits 0. Any problem is logged to
stderr and the output file is left exactly as it was.
"""
import hashlib
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

CYCLE = 6.0          # seconds: scan sweep, then the four laws tick
MONO = "ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace"
SANS = "-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif"
EASE = "0.42 0 0.58 1"

LEAD = ["I build AI agents", "that act — and prove it."]
BIO = [
    "AI/ML engineer and co-founder of Kovidam, an AI talent-intelligence",
    "platform. I build systems end to end: the model, the agents that",
    "use it, the backend underneath and the product on top.",
    "",
    "Architected, not prompted — real data pipelines, real evaluation,",
    "and a person in charge of anything that can’t be undone.",
]
BIO_SHORT = [
    "AI/ML engineer and co-founder of Kovidam. I build systems end to end:",
    "the model, the agents that use it, the backend and the product on top,",
    "with a person in charge of anything that can’t be undone.",
]
LAWS = [
    ("Prove it worked", "#a78bfa", "ForgeSRE verifies recovery; EraseOps rescans until nothing is left."),
    ("A human signs off", "#f472b6", "ForgeSRE waits before a rollback; EraseOps on one exact plan hash."),
    ("Show the source", "#22d3ee", "The Evidence Console cites the exact video second or PDF page."),
    ("Run where the data lives", "#818cf8", "AEGIS runs air-gapped; JKY Terminal and my-localmcp stay local."),
]
RULES = [
    ("Prove it worked", "#a78bfa",
     ["ForgeSRE checks recovery against thresholds; EraseOps", "rescans until nothing personal is left."]),
    ("A human signs off", "#f472b6",
     ["ForgeSRE stops before a production rollback; EraseOps", "waits for approval of one exact plan hash."]),
    ("Show the source", "#22d3ee",
     ["The evidence console links every answer to the exact", "video second or PDF page it came from."]),
    ("Run where the data lives", "#818cf8",
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


def fetch_calendar():
    """The same merged 12-month contribution calendar Commit City is built from."""
    import generate_signal as sig  # noqa: PLC0415  (sibling script, stdlib only)
    d = sig.parse(sig.fetch(), sig.fetch_public_calendar())
    days = [(dd["date"], dd["contributionCount"]) for w in d["weeks"] for dd in w["contributionDays"]]
    return days, d


def spiral_points(n_days, cx, cy):
    """One continuous ridge, a whorl from the core outward; day i owns an equal share of its length.
    Returns, per day, the list of points along its stretch of the ridge."""
    turns, r0, r1 = 25.5, 9.0, 168.0
    steps = n_days * 9
    pts = []
    for s in range(steps + 1):
        f = s / steps
        t = f * turns * 2 * math.pi
        # equal arc length per day: radius grows with sqrt so outer turns are not over-weighted
        r = r0 + (r1 - r0) * f
        a = t - math.pi / 2 + 0.35 * math.sin(f * math.pi)          # a slight twist, like a real whorl
        x = r * math.cos(a) * 0.80
        y = r * math.sin(a)
        if y > 0:                                                     # ridges flatten toward the crease
            y *= 1 - 0.14 * (r / r1)
        lean = math.radians(-9)
        xr = x * math.cos(lean) - y * math.sin(lean)
        yr = x * math.sin(lean) + y * math.cos(lean)
        pts.append((cx + xr, cy + yr))
    # equal arc length per day
    cum = [0.0]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(x1 - x0, y1 - y0))
    total = cum[-1]
    per_day, j = [], 0
    for i in range(n_days):
        a, b = total * i / n_days, total * (i + 1) / n_days
        seg = []
        while j < len(pts) and cum[j] < a:
            j += 1
        k = max(j - 1, 0)
        while k < len(pts) and cum[k] <= b:
            seg.append(pts[k])
            k += 1
        if k < len(pts):
            seg.append(pts[k])
        per_day.append(seg)
    return per_day


def ramp(t):
    """violet (a year ago) -> indigo -> cyan (now)."""
    stops = [(0.0, (0xa7, 0x8b, 0xfa)), (0.5, (0x81, 0x8c, 0xf8)), (1.0, (0x22, 0xd3, 0xee))]
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            return "#" + "".join(f"{round(a + (b - a) * k):02x}" for a, b in zip(c0, c1))
    return "#22d3ee"


def build(repos, cal, synced):
    days, sig = cal
    n = len(repos)
    total_mb = sum(r["bytes"] for r in repos) / 1_000_000
    counts = [c for _, c in days]
    mx = max(counts) or 1
    total = sum(counts)
    active = sum(1 for c in counts if c)
    first = datetime.fromisoformat(days[0][0])
    digest = hashlib.sha256("\n".join(f"{d}:{c}" for d, c in days).encode()).hexdigest()
    top_days = sorted(range(len(days)), key=lambda i: -counts[i])[:6]
    peak = top_days[0]

    W, H = 1000, 560
    PX, PY = 214, 272                       # centre of the print
    rules_txt = "; ".join(t + ": " + " ".join(lines) for t, _, lines in RULES)
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-labelledby="idTitle idDesc">',
         '<title id="idTitle">Identity — a fingerprint grown from the work</title>',
         f'<desc id="idDesc">A fingerprint drawn from Kartikeya Yadav\'s real GitHub contributions: one spiral ridge is the '
         f'last {len(days)} days, the core a year ago and the edge today, its ink as thick and bright as that day\'s '
         f'contributions ({total:,} over {active} active days; the six biggest days are marked, the largest '
         f'{counts[peak]} on {fmt_date(days[peak][0])}). A scanner sweeps the print and the four laws are verified one by '
         f'one. The print is signed with the SHA-256 of its own data, {digest[:16]}. Beside it: {esc(" ".join(LEAD))} '
         f'{esc(" ".join(l for l in BIO if l))} The four laws: {esc(rules_txt)}.</desc>']
    p.append(f'''<defs>
    <clipPath id="idFrame"><rect width="{W}" height="{H}" rx="14"/></clipPath>
    <radialGradient id="idLight" cx="0.21" cy="0.52" r="0.42"><stop offset="0" stop-color="#7c3aed" stop-opacity="0.20"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>
    <linearGradient id="idLeadInk" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff"/><stop offset="0.45" stop-color="#c4b5fd"/><stop offset="1" stop-color="#67e8f9"/></linearGradient>
    <linearGradient id="idBeam" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#22d3ee" stop-opacity="0"/><stop offset="0.75" stop-color="#22d3ee" stop-opacity="0.22"/><stop offset="1" stop-color="#ecfeff" stop-opacity="0.9"/></linearGradient>
    <filter id="idGlowF" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="idInk" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="0.9" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <clipPath id="idScan"><rect x="{PX - 190}" y="{PY - 200}" width="380" height="34">
      <animate attributeName="y" values="{PY - 230};{PY + 190};{PY + 190}" keyTimes="0;0.5;1" dur="{CYCLE}s" repeatCount="indefinite"/></rect></clipPath>
  </defs>''')
    p.append('<g clip-path="url(#idFrame)">')
    p.append(f'<rect width="{W}" height="{H}" fill="#0a0a0a"/><rect width="{W}" height="{H}" fill="url(#idLight)"/>')
    grid = []
    for x in range(20, W, 20):
        grid.append(f'<path d="M{x} 0V{H}" stroke="#a78bfa" stroke-opacity="{0.045 if x % 100 == 0 else 0.016}"/>')
    for y in range(20, H, 20):
        grid.append(f'<path d="M0 {y}H{W}" stroke="#a78bfa" stroke-opacity="{0.045 if y % 100 == 0 else 0.016}"/>')
    p.append("".join(grid))

    # ---- HUD
    p.append(f'<text x="28" y="34" font-family="{MONO}" font-size="11" letter-spacing="1.2" fill="#5a5a63">'
             f'IDENTITY // VERIFIED FROM THE WORK</text>')
    p.append(f'<circle cx="{W - 28}" cy="30" r="3" fill="#22c55e" filter="url(#idGlowF)">{breathe("opacity", "1;0.3;1", "2s")}</circle>')
    p.append(f'<text x="{W - 38}" y="34" text-anchor="end" font-family="{MONO}" font-size="11" letter-spacing="1.2" '
             f'fill="#5a5a63">{n} PUBLIC REPOS · {total_mb:.1f} MB OF CODE · SYNCED {synced.strftime("%d %b").upper()}</text>')

    # ---- the scanner bed
    bx0, by0, bx1, by1 = PX - 186, PY - 206, PX + 186, PY + 196
    p.append(f'<rect x="{bx0}" y="{by0}" width="{bx1 - bx0}" height="{by1 - by0}" rx="16" fill="#0d0d10" fill-opacity="0.55" '
             f'stroke="#1f1f24"/>')
    for (cx, cy, dx, dy) in ((bx0, by0, 1, 1), (bx1, by0, -1, 1), (bx0, by1, 1, -1), (bx1, by1, -1, -1)):
        p.append(f'<path d="M{cx + dx * 4} {cy + dy * 26}V{cy + dy * 4}H{cx + dx * 26}" fill="none" stroke="#a78bfa" '
                 f'stroke-width="2" stroke-linecap="round" opacity="0.8"/>')
    p.append(f'<ellipse cx="{PX}" cy="{PY + 2}" rx="152" ry="186" fill="none" stroke="#a78bfa" stroke-opacity="0.12" '
             f'stroke-dasharray="2 5"/>')

    # ---- the print: one ridge, one day per stretch, ink = that day's contributions
    per_day = spiral_points(len(days), PX, PY)
    base, lit = [], []
    for i, ((date, c), seg) in enumerate(zip(days, per_day)):
        if len(seg) < 2:
            continue
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in seg)
        k = math.sqrt(c / mx)
        col = ramp(i / (len(days) - 1))
        if c:
            base.append(f'<path d="{d}" stroke="{col}" stroke-width="{1.15 + 2.1 * k:.2f}" stroke-opacity="{0.55 + 0.45 * k:.2f}"/>')
        else:
            base.append(f'<path d="{d}" stroke="{col}" stroke-width="0.8" stroke-opacity="0.2"/>')
        lit.append(f'<path d="{d}" stroke="#ecfeff" stroke-width="{1.3 + 2.1 * k:.2f}" stroke-opacity="{0.55 + 0.45 * k:.2f}"/>')
    p.append(f'<g fill="none" stroke-linecap="round" stroke-linejoin="round" filter="url(#idInk)">{"".join(base)}</g>')
    # the scan: the same ridge, bright, seen only through the moving band
    p.append(f'<g clip-path="url(#idScan)" fill="none" stroke-linecap="round" stroke-linejoin="round" filter="url(#idGlowF)">'
             f'{"".join(lit)}</g>')
    p.append(f'<rect x="{bx0 + 6}" y="{PY - 230}" width="{bx1 - bx0 - 12}" height="34" fill="url(#idBeam)">'
             f'<animate attributeName="y" values="{PY - 230};{PY + 190};{PY + 190}" keyTimes="0;0.5;1" dur="{CYCLE}s" '
             f'repeatCount="indefinite"/><animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.48;0.5;1" '
             f'dur="{CYCLE}s" repeatCount="indefinite"/></rect>')
    # minutiae: the six biggest days, ringed after the scan passes
    for rank, i in enumerate(top_days):
        seg = per_day[i]
        if not seg:
            continue
        x, y = seg[len(seg) // 2]
        p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="#ffffff" filter="url(#idGlowF)"/>')
        p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="none" stroke="#22d3ee" stroke-width="1.2" opacity="0.9">'
                 f'<animate attributeName="r" values="4;4;11;4" keyTimes="0;{0.5 + rank * 0.04:.2f};{0.62 + rank * 0.04:.2f};1" '
                 f'dur="{CYCLE}s" repeatCount="indefinite"/></circle>')

    # core and edge
    cxp, cyp = per_day[0][0]
    exp, eyp = per_day[-1][-1]
    p.append(f'<circle cx="{cxp:.1f}" cy="{cyp:.1f}" r="2.4" fill="#a78bfa"/>')
    p.append(f'<circle cx="{exp:.1f}" cy="{eyp:.1f}" r="3.2" fill="#22c55e" filter="url(#idGlowF)">'
             f'{breathe("opacity", "1;0.35;1", "1.6s")}</circle>')
    # readout under the print
    for k, (line, fill) in enumerate((
            (f"ONE RIDGE = {len(days)} DAYS  ·  CORE {first.strftime('%b %Y').upper()} → EDGE TODAY", "#8a8a93"),
            (f"RINGED = 6 BIGGEST DAYS  ·  PEAK {counts[peak]} ON {fmt_date(days[peak][0]).upper()}", "#8a8a93"),
            (f"SIGNED  sha256:{digest[:12]}…{digest[-6:]}", "#5a5a63"))):
        p.append(f'<text x="{PX}" y="{by1 + 24 + k * 17}" text-anchor="middle" font-family="{MONO}" font-size="10" '
                 f'letter-spacing="0.8" fill="{fill}">{esc(line)}</text>')
    # match flash once the scan is through
    p.append(f'<g opacity="0"><animate attributeName="opacity" values="0;0;1;1;0" keyTimes="0;0.5;0.53;0.94;1" '
             f'dur="{CYCLE}s" repeatCount="indefinite"/>'
             f'<rect x="{PX - 84}" y="{by0 - 13}" width="168" height="26" rx="13" fill="#0d0d10" stroke="#22c55e" '
             f'stroke-opacity="0.7"/><circle cx="{PX - 68}" cy="{by0}" r="3.5" fill="#22c55e"/>'
             f'<text x="{PX + 6}" y="{by0 + 4.5}" text-anchor="middle" font-family="{MONO}" font-size="11" font-weight="700" '
             f'letter-spacing="1.4" fill="#f4f4f5">PRINT VERIFIED</text></g>')

    # ---- right: who, then the four laws, verified one by one after each scan
    x0 = 440
    p.append(f'<text x="{x0}" y="98" font-family="{MONO}" font-size="11" letter-spacing="1.6" fill="#a78bfa">'
             f'KARTIKEYA YADAV · AI/ML ENGINEER</text>')
    for k, line in enumerate(LEAD):
        p.append(f'<text x="{x0 - 2}" y="{142 + k * 42}" font-family="{SANS}" font-size="38" font-weight="800" '
                 f'letter-spacing="-1" fill="url(#idLeadInk)">{esc(line)}</text>')
    for k, line in enumerate(BIO_SHORT):
        p.append(f'<text x="{x0}" y="{220 + k * 21}" font-family="{SANS}" font-size="14.5" fill="#a1a1aa">{esc(line)}</text>')
    ly0 = 302
    p.append(f'<text x="{x0}" y="{ly0}" font-family="{MONO}" font-size="11" letter-spacing="1.6" fill="#8a8a93">'
             f'VERIFIED AGAINST FOUR LAWS</text>')
    p.append(f'<path d="M{x0 + 214} {ly0 - 4}H{W - 30}" stroke="#1f1f24"/>')
    for k, (title, col, proof) in enumerate(LAWS):
        y = ly0 + 34 + k * 46
        t_tick = 0.56 + k * 0.07
        tick = (f'<animate attributeName="opacity" values="0.15;0.15;1;1" keyTimes="0;{t_tick:.2f};{t_tick + 0.03:.2f};1" '
                f'dur="{CYCLE}s" repeatCount="indefinite"/>')
        p.append(f'<circle cx="{x0 + 11}" cy="{y - 5}" r="11" fill="none" stroke="{col}" stroke-opacity="0.45"/>')
        p.append(f'<g opacity="1">{tick}<circle cx="{x0 + 11}" cy="{y - 5}" r="11" fill="{col}" fill-opacity="0.16" '
                 f'stroke="{col}"/><path d="M{x0 + 6} {y - 5}l3.5 3.5l6.5 -7" fill="none" stroke="{col}" stroke-width="2" '
                 f'stroke-linecap="round" stroke-linejoin="round"/></g>')
        p.append(f'<text x="{x0 + 34}" y="{y}" font-family="{SANS}" font-size="16" font-weight="700" fill="#f4f4f5">'
                 f'<tspan font-family="{MONO}" font-size="11" font-weight="400" fill="{col}" letter-spacing="1">'
                 f'{k + 1:02d}  </tspan>{esc(title)}</text>')
        p.append(f'<text x="{x0 + 34}" y="{y + 19}" font-family="{SANS}" font-size="13" fill="#8a8a93">{esc(proof)}</text>')

    p.append('</g>')
    p.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="#1f1f24"/>')
    p.append("</svg>")
    return "\n".join(p)


def fmt_date(s):
    d = datetime.fromisoformat(s)
    return f"{d.day} {d.strftime('%b %Y')}"


def main():
    try:
        repos = fetch()
        if len(repos) < 3:
            raise FetchError(f"only {len(repos)} public repositories came back — too few to draw a system")
        repos.sort(key=lambda r: (r["first"], r["name"].lower()))
        synced = datetime.fromisoformat(NOW).astimezone(TZ) if NOW else datetime.now(TZ)
        cal = fetch_calendar()
        if len(cal[0]) < 300:
            raise FetchError(f"contribution calendar came back short ({len(cal[0])} days)")
        svg = build(repos, cal, synced)
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
