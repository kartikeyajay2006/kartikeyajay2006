#!/usr/bin/env python3
"""Generate assets/identity-core.svg — the section 02 "Identity" plate.

A dark, quiet frame in the spirit of the rest of the profile: a beam of light falls
from the top right and dust drifts through it, a soft aura breathes behind one
statement, and the statement carries its sources.

  - The dust is real. Every mote is one day I shipped in the last twelve months,
    from the same contribution calendar Commit City is built from: placed left to
    right by date, as large and bright as that day was busy. A finer haze of
    ambient dust shows only inside the light.
  - "I build AI agents [1] that act [2] — and prove it, [3] with a person in
    charge. [4]" Every claim is set phrase by phrase (textLength pins each width,
    so markers and underlines land exactly) and cited to the repositories that
    back it. In turn, each claim is underlined as its source lights up.
  - The header numbers (days shipped, contributions, public repos, code) are live.

SVG notes (see generate_signal.py): GitHub strips <script> and inline <style>,
so all motion is SMIL, and nothing uses <use>/<mpath>. Anything readable starts
visible, so a renderer that ignores SMIL shows a finished still frame.

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

CYCLE = 12.0         # seconds: each of the four claims is cited in turn
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


# Advance widths per 1000 em (Helvetica / Arial), used to place each phrase exactly. Every phrase is
# also drawn with textLength, so the browser fits it to the width computed here: superscripts and
# underlines always land where they should, whatever font the viewer's system picks.
BOLD = dict(zip("abcdefghijklmnopqrstuvwxyz", [556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889,
                                                611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500]))
BOLD.update({" ": 278, "I": 278, "A": 722, "—": 1000, ".": 278, ",": 278, "’": 278})


def width_bold(s, size, tracking=-0.025):
    return sum(BOLD.get(ch, 600) for ch in s) / 1000 * size + tracking * size * (len(s) - 1)


def wrap(s, size, width):
    words, out, cur = s.split(), [], ""
    for w_ in words:
        if cur and len(cur + " " + w_) * size * 0.5 > width:
            out.append(cur)
            cur = w_
        else:
            cur = (cur + " " + w_).strip()
    return out + [cur]


# The statement, line by line: (text, kind). kind "key" phrases carry a citation; "sup" is its marker.
STATEMENT = [
    [("I build ", "plain"), ("AI agents", "key", 0), ("1", "sup", 0)],
    [("that ", "plain"), ("act", "key", 1), ("2", "sup", 1), (" — and ", "plain"), ("prove it,", "key", 2), ("3", "sup", 2)],
    [("with a ", "plain"), ("person in charge.", "key", 3), ("4", "sup", 3)],
]
CITATIONS = [
    ("AI AGENTS", "#a78bfa",
     "Agentic systems are the core of the work: AEGIS, ForgeSRE, EraseOps and Chakraview, built end to end, "
     "model to product, running where the data lives."),
    ("THAT ACT", "#f472b6",
     "They change real systems. ForgeSRE restarts services and rolls back production; EraseOps deletes a "
     "customer across PostgreSQL and object storage."),
    ("AND PROVE IT", "#22d3ee",
     "31 of 31 attacks held on AEGIS. 3,639 tests in JKY Terminal. Every Evidence Console answer cites the "
     "exact video second or PDF page."),
    ("A PERSON IN CHARGE", "#818cf8",
     "ForgeSRE stops for a human before a rollback. EraseOps runs only after one exact plan hash is approved, "
     "then rescans to zero."),
]


def build(repos, cal, synced):
    days, _ = cal
    rnd = random.Random(2006)
    n = len(repos)
    total_mb = sum(r["bytes"] for r in repos) / 1_000_000
    counts = [c for _, c in days]
    mx = max(counts) or 1
    contrib = sum(counts)
    active = [(i, d, c) for i, (d, c) in enumerate(days) if c]
    W, H = 1000, 540
    SIZE, LINE0, LH = 56, 150, 66
    slot = CYCLE / len(CITATIONS)
    statement_txt = " ".join("".join(c[0] for c in line if c[1] != "sup") for line in STATEMENT)

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-labelledby="idTitle idDesc">',
         '<title id="idTitle">Identity — Kartikeya Yadav</title>',
         f'<desc id="idDesc">A dark, quiet frame. A beam of light falls from the top right and dust drifts through it: '
         f'every mote is one day I shipped in the last twelve months ({len(active)} days, {contrib:,} contributions), '
         f'placed left to right by date and as bright as that day was busy. A soft aura breathes behind the statement: '
         f'{esc(statement_txt)} Each claim is cited to the work that backs it: '
         + esc(" ".join(f"[{i + 1}] {t.title()}: {body}" for i, (t, _, body) in enumerate(CITATIONS)))
         + '</desc>']
    p.append(f'''<defs>
    <clipPath id="idFrame"><rect width="{W}" height="{H}" rx="14"/></clipPath>
    <radialGradient id="idAura" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#7c3aed" stop-opacity="0.34"/><stop offset="0.45" stop-color="#4c1d95" stop-opacity="0.14"/><stop offset="1" stop-color="#4c1d95" stop-opacity="0"/></radialGradient>
    <radialGradient id="idAura2" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#22d3ee" stop-opacity="0.14"/><stop offset="1" stop-color="#22d3ee" stop-opacity="0"/></radialGradient>
    <radialGradient id="idVignette" cx="0.5" cy="0.45" r="0.75"><stop offset="0.55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.7"/></radialGradient>
    <linearGradient id="idBeam" x1="1" y1="0" x2="0.15" y2="1"><stop offset="0" stop-color="#e0e7ff" stop-opacity="0.16"/><stop offset="0.55" stop-color="#a5b4fc" stop-opacity="0.05"/><stop offset="1" stop-color="#a5b4fc" stop-opacity="0"/></linearGradient>
    <linearGradient id="idKey" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ddd6fe"/><stop offset="0.55" stop-color="#a5b4fc"/><stop offset="1" stop-color="#67e8f9"/></linearGradient>
    <filter id="idGrain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="7" result="n"/><feColorMatrix in="n" type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.55 -0.2"/></filter>
    <filter id="idSoft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="14"/></filter>
    <filter id="idMote" x="-300%" y="-300%" width="700%" height="700%"><feGaussianBlur stdDeviation="1.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="idGlowF" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>''')
    p.append('<g clip-path="url(#idFrame)">')
    p.append(f'<rect width="{W}" height="{H}" fill="#060608"/>')

    # ---- the light: a wide beam from the top right, two thinner shafts inside it, all swaying slowly
    beams = [(880, 250, 0.9, 30), (820, 120, 1.0, 38), (960, 90, 0.8, 46)]
    for k, (x_top, width, op, dur) in enumerate(beams):
        poly = f"{x_top - width / 2},-20 {x_top + width / 2},-20 {x_top + width / 2 - 520},{H + 20} {x_top - width / 2 - 760},{H + 20}"
        p.append(f'<polygon points="{poly}" fill="url(#idBeam)" opacity="{op}">'
                 f'<animateTransform attributeName="transform" type="rotate" values="0 {x_top} -20;{2.2 - k:.1f} {x_top} -20;0 {x_top} -20" '
                 f'dur="{dur}s" repeatCount="indefinite" calcMode="spline" keySplines="{EASE};{EASE}"/>'
                 f'{breathe("opacity", f"{op};{op * 0.55:.2f};{op}", f"{dur * 0.7:.0f}s")}</polygon>')

    # ---- the aura behind the statement, breathing
    p.append(f'<ellipse cx="300" cy="{LINE0 + 50}" rx="360" ry="190" fill="url(#idAura)">'
             f'{breathe("rx", "340;390;340", "9s")}{breathe("opacity", "0.85;1;0.85", "9s")}</ellipse>')
    p.append(f'<ellipse cx="620" cy="{LINE0 + 110}" rx="260" ry="140" fill="url(#idAura2)">'
             f'{breathe("opacity", "0.5;1;0.5", "13s", "2s")}</ellipse>')

    # ---- dust: every mote is a day that shipped, left to right by date, brighter the busier it was.
    # Motes inside the beam catch the light; the rest stay faint. Each drifts slowly on its own loop.
    motes = []
    for i, d, c in active:
        k = math.sqrt(c / mx)
        x = 28 + (W - 56) * i / (len(days) - 1) + rnd.uniform(-6, 6)
        y = rnd.uniform(22, LINE0 + 2 * LH + 40)
        in_beam = (y + (x - 880) * (H / 600)) < 300 and x > 300
        r = 0.6 + 2.1 * k
        op = (0.35 + 0.6 * k) if in_beam else (0.18 + 0.45 * k)
        col = "#ffffff" if k > 0.55 else ("#e0e7ff" if in_beam else "#c4b5fd")
        dx, dy = rnd.uniform(-9, 9), rnd.uniform(-22, -8)
        dur = rnd.uniform(16, 34)
        motes.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{col}" opacity="{op:.2f}"'
            + (' filter="url(#idMote)"' if k > 0.5 else "") + '>'
            f'<animateTransform attributeName="transform" type="translate" values="0 0;{dx:.1f} {dy:.1f};{-dx / 2:.1f} {dy / 3:.1f};0 0" '
            f'dur="{dur:.1f}s" begin="-{rnd.uniform(0, dur):.1f}s" repeatCount="indefinite" calcMode="spline" '
            f'keySplines="{EASE};{EASE};{EASE}"/>'
            f'<animate attributeName="opacity" values="{op:.2f};{op * 0.35:.2f};{op:.2f}" dur="{rnd.uniform(4, 9):.1f}s" '
            f'begin="-{rnd.uniform(0, 5):.1f}s" repeatCount="indefinite"/></circle>')
    # a finer haze of ambient dust that only shows inside the light
    for _ in range(150):
        x, y = rnd.uniform(300, W), rnd.uniform(0, LINE0 + 2 * LH + 50)
        if (y + (x - 880) * (H / 600)) > 330:
            continue
        dur = rnd.uniform(20, 40)
        motes.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rnd.uniform(0.35, 0.8):.2f}" fill="#e0e7ff" '
                     f'opacity="{rnd.uniform(0.15, 0.45):.2f}"><animateTransform attributeName="transform" type="translate" '
                     f'values="0 0;{rnd.uniform(-12, 12):.1f} {rnd.uniform(-26, -10):.1f};0 0" dur="{dur:.1f}s" '
                     f'begin="-{rnd.uniform(0, dur):.1f}s" repeatCount="indefinite"/></circle>')
    p.append(f'<g>{"".join(motes)}</g>')

    # film grain and vignette: the dust in the air, and the dark at the edges
    p.append(f'<rect width="{W}" height="{H}" filter="url(#idGrain)" opacity="0.07"/>')
    p.append(f'<rect width="{W}" height="{H}" fill="url(#idVignette)"/>')

    def window(k):
        t0, t1 = k * slot / CYCLE, (k + 1) * slot / CYCLE
        if k == 0:
            return f'values="1;0" keyTimes="0;{t1:.4f}"'
        if k == len(CITATIONS) - 1:
            return f'values="0;1" keyTimes="0;{t0:.4f}"'
        return f'values="0;1;0" keyTimes="0;{t0:.4f};{t1:.4f}"'

    # ---- name and live numbers, quiet
    p.append(f'<text x="40" y="52" font-family="{MONO}" font-size="11.5" letter-spacing="2.4" fill="#a78bfa">'
             f'KARTIKEYA YADAV</text>')
    p.append(f'<text x="40" y="72" font-family="{MONO}" font-size="10.5" letter-spacing="1.6" fill="#5a5a63">'
             f'AI/ML ENGINEER  ·  CO-FOUNDER, KOVIDAM</text>')
    p.append(f'<text x="{W - 40}" y="52" text-anchor="end" font-family="{MONO}" font-size="10.5" letter-spacing="1.6" '
             f'fill="#5a5a63">{len(active)} DAYS SHIPPED · {contrib:,} CONTRIBUTIONS</text>')
    p.append(f'<text x="{W - 40}" y="72" text-anchor="end" font-family="{MONO}" font-size="10.5" letter-spacing="1.6" '
             f'fill="#3f3f46">{n} PUBLIC REPOS · {total_mb:.1f} MB</text>')

    # ---- the statement
    marks = {}
    for li, line in enumerate(STATEMENT):
        y = LINE0 + li * LH
        x = 38.0
        for chunk in line:
            text, kind = chunk[0], chunk[1]
            if kind == "sup":
                k = chunk[2]
                col = CITATIONS[k][1]
                p.append(f'<text x="{x + 3:.1f}" y="{y - 28}" font-family="{MONO}" font-size="18" font-weight="700" '
                         f'fill="{col}">{text}</text>')
                p.append(f'<circle cx="{x + 8.5:.1f}" cy="{y - 34}" r="13" fill="{col}" fill-opacity="0.16" stroke="{col}" '
                         f'stroke-opacity="0.7" opacity="0" filter="url(#idGlowF)"><animate attributeName="opacity" '
                         f'{window(k)} calcMode="discrete" dur="{CYCLE}s" repeatCount="indefinite"/></circle>')
                x += 20
                continue
            w = width_bold(text, SIZE)
            fill = "url(#idKey)" if kind == "key" else "#f4f4f5"
            p.append(f'<text x="{x:.1f}" y="{y}" font-family="{SANS}" font-size="{SIZE}" font-weight="800" '
                     f'textLength="{w:.1f}" lengthAdjust="spacing" fill="{fill}" xml:space="preserve">{esc(text)}</text>')
            if kind == "key":
                marks[chunk[2]] = (x, y, w)
            x += w
    for k, (x, y, w) in marks.items():
        col = CITATIONS[k][1]
        t0 = k * slot / CYCLE
        t_draw = (k * slot + 0.7) / CYCLE
        p.append(f'<g opacity="0"><animate attributeName="opacity" {window(k)} calcMode="discrete" dur="{CYCLE}s" '
                 f'repeatCount="indefinite"/>'
                 f'<path d="M{x + 2:.1f} {y + 13}H{x + w - 4:.1f}" stroke="{col}" stroke-width="9" stroke-linecap="round" '
                 f'stroke-opacity="0.18" stroke-dasharray="{w:.0f}" stroke-dashoffset="{w:.0f}">'
                 f'<animate attributeName="stroke-dashoffset" values="{w:.0f};{w:.0f};0;0" '
                 f'keyTimes="0;{t0:.4f};{t_draw:.4f};1" dur="{CYCLE}s" repeatCount="indefinite"/></path>'
                 f'<path d="M{x + 2:.1f} {y + 13}H{x + w - 4:.1f}" stroke="{col}" stroke-width="3" stroke-linecap="round" '
                 f'stroke-dasharray="{w:.0f}" stroke-dashoffset="{w:.0f}">'
                 f'<animate attributeName="stroke-dashoffset" values="{w:.0f};{w:.0f};0;0" '
                 f'keyTimes="0;{t0:.4f};{t_draw:.4f};1" dur="{CYCLE}s" repeatCount="indefinite"/></path></g>')

    # ---- the sources: four quiet columns, each lit while its claim is underlined
    cy0 = LINE0 + 2 * LH + 66
    gap = 28
    cw = (W - 80 - gap * 3) / 4
    for k, (title, col, body) in enumerate(CITATIONS):
        x = 40 + k * (cw + gap)
        p.append(f'<path d="M{x:.1f} {cy0}H{x + cw:.1f}" stroke="#27272a"/>')
        p.append(f'<path d="M{x:.1f} {cy0}H{x + cw:.1f}" stroke="{col}" stroke-width="2.5" opacity="0">'
                 f'<animate attributeName="opacity" {window(k)} calcMode="discrete" dur="{CYCLE}s" repeatCount="indefinite"/></path>')
        p.append(f'<text x="{x:.1f}" y="{cy0 + 28}" font-family="{MONO}" font-size="12.5" font-weight="700" fill="{col}">'
                 f'[{k + 1}]<tspan dx="8" font-size="10.5" font-weight="400" letter-spacing="1.4" fill="#8a8a93">{esc(title)}'
                 f'</tspan></text>')
        lines = wrap(body, 13.5, cw)
        body_g = "".join(f'<text x="{x:.1f}" y="{cy0 + 54 + m * 19.5}" font-family="{SANS}" font-size="13.5" '
                         f'fill="#a1a1aa">{esc(line)}</text>' for m, line in enumerate(lines))
        lit_g = "".join(f'<text x="{x:.1f}" y="{cy0 + 54 + m * 19.5}" font-family="{SANS}" font-size="13.5" '
                        f'fill="#f4f4f5">{esc(line)}</text>' for m, line in enumerate(lines))
        p.append(body_g)
        p.append(f'<g opacity="0"><animate attributeName="opacity" {window(k)} calcMode="discrete" dur="{CYCLE}s" '
                 f'repeatCount="indefinite"/>{lit_g}</g>')

    p.append('</g>')
    p.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="#1f1f24"/>')
    p.append("</svg>")
    return "\n".join(p)


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
