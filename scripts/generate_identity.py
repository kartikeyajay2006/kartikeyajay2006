#!/usr/bin/env python3
"""Generate assets/identity-core.svg — the section 02 "Identity" plate.

Left: who I am and what the work is about, in two lines and a short bio.
Right: the four laws the work keeps, drawn as the path every agent action
takes. An action enters at the top, passes four gates (prove it worked, a
human signs off, show the source, run where the data lives), and only then
counts; each gate lights as the action reaches it, then the loop closes for
the next one. Every law names the repositories it was shipped in.

The header numbers (public repositories, bytes of code, first commit) are
live from the GitHub API; the bio and the laws are curated copy, and nothing
there is a number or a claim the repositories do not back up.

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

W, H = 900, 428
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


def build(repos, synced):
    n = len(repos)
    total_mb = sum(r["bytes"] for r in repos) / 1_000_000
    oldest = repos[0]
    rules_txt = "; ".join(t + ": " + " ".join(lines) for t, _, lines in RULES)
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-labelledby="idTitle idDesc">',
         '<title id="idTitle">Identity — how I build</title>',
         f'<desc id="idDesc">Kartikeya Yadav. {esc(" ".join(LEAD))} {esc(" ".join(l for l in BIO if l))} '
         f'Beside it, the four laws drawn as a pipeline every agent action passes through, each gate lighting as the '
         f'action reaches it: {esc(rules_txt)}. Live: {n} public repositories, {total_mb:.1f} MB of code, building since '
         f'{oldest["first"].strftime("%B %Y")}.</desc>',
         f'''<defs>
    <clipPath id="idFrame"><rect width="{W}" height="{H}" rx="14"/></clipPath>
    <radialGradient id="idLight" cx="0.12" cy="0.1" r="0.8"><stop offset="0" stop-color="#7c3aed" stop-opacity="0.16"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>
    <linearGradient id="idLeadInk" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff"/><stop offset="0.45" stop-color="#c4b5fd"/><stop offset="1" stop-color="#67e8f9"/></linearGradient>
    <linearGradient id="idWire" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a78bfa"/><stop offset="0.5" stop-color="#f472b6"/><stop offset="1" stop-color="#22d3ee"/></linearGradient>
    <filter id="idGlowF" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>''',
         '<g clip-path="url(#idFrame)">',
         f'<rect width="{W}" height="{H}" fill="#0a0a0a"/><rect width="{W}" height="{H}" fill="url(#idLight)"/>']
    grid = []
    for x in range(20, W, 20):
        grid.append(f'<path d="M{x} 0V{H}" stroke="#a78bfa" stroke-opacity="{0.05 if x % 100 == 0 else 0.018}"/>')
    for y in range(20, H, 20):
        grid.append(f'<path d="M0 {y}H{W}" stroke="#a78bfa" stroke-opacity="{0.05 if y % 100 == 0 else 0.018}"/>')
    p.append("".join(grid))

    # ---- HUD, the same corner labels every section carries
    p.append(f'<text x="24" y="32" font-family="{MONO}" font-size="10" letter-spacing="1.2" fill="#5a5a63">'
             f'IDENTITY // HOW I BUILD</text>')
    p.append(f'<circle cx="{W - 24}" cy="28.5" r="3" fill="#22c55e" filter="url(#idGlowF)">{breathe("opacity", "1;0.3;1", "2s")}</circle>')
    p.append(f'<text x="{W - 34}" y="32" text-anchor="end" font-family="{MONO}" font-size="10" letter-spacing="1.2" '
             f'fill="#5a5a63">{n} PUBLIC REPOS · {total_mb:.1f} MB OF CODE · SINCE '
             f'{oldest["first"].strftime("%b %Y").upper()}</text>')

    # ---- left: who, and what the work is about
    p.append(f'<text x="32" y="84" font-family="{MONO}" font-size="9.5" letter-spacing="1.6" fill="#a78bfa">'
             f'KARTIKEYA YADAV · AI/ML ENGINEER</text>')
    for k, line in enumerate(LEAD):
        p.append(f'<text x="30" y="{126 + k * 40}" font-family="{SANS}" font-size="34" font-weight="800" '
                 f'letter-spacing="-0.8" fill="url(#idLeadInk)">{esc(line)}</text>')
    yy = 204
    for line in BIO:
        if not line:
            yy += 9
            continue
        p.append(f'<text x="32" y="{yy}" font-family="{SANS}" font-size="13" fill="#a1a1aa">{esc(line)}</text>')
        yy += 20
    chips = ["AI/ML ENGINEER", "CO-FOUNDER · KOVIDAM", "AI-ML CLUB · AI LEAD"]
    cx_ = 32
    for chip in chips:
        cw = len(chip) * 5.6 + 18
        p.append(f'<rect x="{cx_:.1f}" y="{H - 58}" width="{cw:.1f}" height="20" rx="10" fill="#0d0d10" stroke="#3b2a6b"/>')
        p.append(f'<text x="{cx_ + 9:.1f}" y="{H - 44.5}" font-family="{MONO}" font-size="8.5" letter-spacing="0.6" '
                 f'fill="#ddd6fe">{esc(chip)}</text>')
        cx_ += cw + 7

    # ---- right: the four laws as gates on the path every action takes
    gx = 492                      # the wire
    cx0, cx1 = 512, W - 28        # gate cards
    top_y, gate_h, gate_gap = 96, 62, 10
    in_y = 66
    out_y = top_y + 4 * (gate_h + gate_gap) + 10
    p.append(f'<text x="{cx0}" y="{in_y + 4}" font-family="{MONO}" font-size="9.5" letter-spacing="1.6" fill="#8a8a93">'
             f'EVERY ACTION AN AGENT TAKES</text>')
    p.append(f'<circle cx="{gx}" cy="{in_y}" r="5" fill="#0d0d10" stroke="#a78bfa" stroke-width="1.4"/>')
    p.append(f'<path d="M{gx} {in_y + 5}V{out_y - 5}" stroke="#a78bfa" stroke-width="1.4" stroke-opacity="0.45"/>')
    # the way back up: the loop closes, the next action starts
    p.append(f'<path d="M{gx - 5} {out_y}H{gx - 18}V{in_y}H{gx - 5}" fill="none" stroke="#3f3f46" stroke-dasharray="2 4"/>')
    cycle = 7.0
    down_end = 0.72
    for k, (title, col, lines) in enumerate(RULES):
        y = top_y + k * (gate_h + gate_gap)
        mid = y + gate_h / 2
        t_hit = (k + 0.5) / 4 * down_end
        flash = (f'values="0;0;1;0.15;0.15" keyTimes="0;{t_hit:.3f};{t_hit + 0.03:.3f};{t_hit + 0.2:.3f};1" '
                 f'dur="{cycle}s" repeatCount="indefinite"')
        p.append(f'<rect x="{cx0}" y="{y}" width="{cx1 - cx0}" height="{gate_h}" rx="10" fill="#0d0d10" stroke="#1f1f24"/>')
        p.append(f'<rect x="{cx0}" y="{y}" width="{cx1 - cx0}" height="{gate_h}" rx="10" fill="{col}" fill-opacity="0.07" '
                 f'stroke="{col}" stroke-opacity="0.8" opacity="0.15"><animate attributeName="opacity" {flash}/></rect>')
        p.append(f'<rect x="{cx0 + 1}" y="{y + 12}" width="2.5" height="{gate_h - 24}" rx="1.2" fill="{col}"/>')
        # the gate on the wire, and its tap into the card
        p.append(f'<path d="M{gx} {mid}H{cx0}" stroke="{col}" stroke-opacity="0.35"/>')
        p.append(f'<rect x="{gx - 6}" y="{mid - 6}" width="12" height="12" rx="2" transform="rotate(45 {gx} {mid})" '
                 f'fill="#0d0d10" stroke="{col}" stroke-width="1.3"/>')
        p.append(f'<rect x="{gx - 3}" y="{mid - 3}" width="6" height="6" rx="1" transform="rotate(45 {gx} {mid})" '
                 f'fill="{col}" opacity="0.3"><animate attributeName="opacity" {flash}/></rect>')
        p.append(f'<text x="{cx0 + 16}" y="{y + 23}" font-family="{SANS}" font-size="14" font-weight="700" fill="#f4f4f5">'
                 f'<tspan font-family="{MONO}" font-size="9.5" font-weight="400" fill="{col}" letter-spacing="1">'
                 f'{k + 1:02d}  </tspan>{esc(title)}</text>')
        for m, line in enumerate(lines):
            p.append(f'<text x="{cx0 + 16}" y="{y + 40 + m * 13.5}" font-family="{SANS}" font-size="10.8" '
                     f'fill="#a1a1aa">{esc(line)}</text>')
    p.append(f'<circle cx="{gx}" cy="{out_y}" r="5" fill="#22d3ee" filter="url(#idGlowF)"/>')
    p.append(f'<text x="{cx0}" y="{out_y + 4}" font-family="{MONO}" font-size="9.5" letter-spacing="1.6" fill="#8a8a93">'
             f'ONLY THEN DOES IT COUNT</text>')
    # the action itself: down through every gate, then back round for the next one
    path = f"M{gx} {in_y} V{out_y} H{gx - 18} V{in_y} H{gx}"
    p.append(f'<circle r="4.5" fill="#ffffff" filter="url(#idGlowF)"><animateMotion path="{path}" '
             f'keyPoints="0;{(out_y - in_y) / (2 * (out_y - in_y) + 36):.4f};1" keyTimes="0;{down_end};1" '
             f'calcMode="linear" dur="{cycle}s" repeatCount="indefinite"/></circle>')

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
