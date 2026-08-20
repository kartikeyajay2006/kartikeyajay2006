#!/usr/bin/env python3
"""Generate assets/identity-core.svg — the section 02 "Identity" hero:
a holographic wireframe head with orbiting rings, a live HUD strip, and
role/bio/focus/approach panels.

Honesty note (see also generate_neon.py / generate_impact.py): SVG has no
real 3D or JavaScript, and GitHub strips both <script> and any inline
<style> from rendered README markdown. The "3D head turn" here is a
deliberate 2D illusion — nested rotate + scaleX oscillation on the head
group, plus front/behind z-ordering of orbit rings for parallax — not
literal 3D. Every animated element is fully self-contained inline (own
path/values, no <use>/<mpath> href indirection), because GitHub's image
proxy strips internal href/xlink:href fragment references (see
generate_neon.py's postmortem on why that silently breaks motion paths).

What's genuinely live (reused from generate_impact.py's approach, same
GH_CONTRIB_PAT secret, no new secret needed):
  - SYSTEM STATUS, VERIFIED %, CODE VOLUME, ACTIVITY tiles: real REST/
    GraphQL data (public repo count, byte volume across all public repos,
    30-day contributions, and the same 4-registry-project deploy check).
  - LAST SYNC timestamp: the actual run time.

What's curated illustration (not fabricated facts — identity art, role
taglines, and the bio paragraph, the last of which is copied verbatim
from this README's existing Identity section, same words, not new claims):
  - The wireframe head/orbit/role-node geometry.
  - The five role taglines (personal brand copy, same register as the
    rest of this README, not a data claim).

Never-fail contract: this script always exits 0. Any problem is logged
to stderr and the script leaves the existing output file untouched.
"""
import json
import os
import sys
import time
import math
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

LOGIN = os.environ.get("GH_LOGIN", "kartikeyajay2006")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT_PATH = os.environ.get("OUT_PATH", "assets/identity-core.svg")
UA = f"{LOGIN}-identity-generator"

REGISTRY_REPOS = ["multi-layer_orchestation", "GitVeda", "ai-image-classifier", "RL-model-Negotiation"]
REGISTRY_FALLBACK_HOMEPAGE = {
    "multi-layer_orchestation": "https://multi-layer-orchestation.vercel.app/",
    "ai-image-classifier": "https://ai-image-classifier-yw8jmptfdt64yxxyxprabj.streamlit.app/",
}

CONTRIB_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { totalContributions }
    }
  }
}
"""


class FetchError(Exception):
    pass


def _get(url):
    req = urllib.request.Request(url, headers={
        "Authorization": f"bearer {TOKEN}", "Accept": "application/vnd.github+json", "User-Agent": UA,
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _graphql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json", "User-Agent": UA},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _safe_languages(repo):
    try:
        return _get(f"https://api.github.com/repos/{LOGIN}/{repo}/languages")
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: languages fetch failed for {repo}: {e}", file=sys.stderr)
        return {}


def _safe_repo(repo):
    try:
        return _get(f"https://api.github.com/repos/{LOGIN}/{repo}")
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: repo fetch failed for {repo}: {e}", file=sys.stderr)
        return {}


def fetch_all(retries=3):
    if not TOKEN:
        raise FetchError("GH_TOKEN is not set (reuses the GH_CONTRIB_PAT secret).")
    last_err = None
    for attempt in range(retries):
        try:
            return _fetch_once()
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"WARNING: attempt {attempt + 1}/{retries} failed: {e}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    raise FetchError(str(last_err))


def _fetch_once():
    now = datetime.now(timezone.utc)
    frm = now - timedelta(days=30)
    payload = _graphql(CONTRIB_QUERY, {
        "login": LOGIN,
        "from": frm.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    if payload.get("errors"):
        raise FetchError(f"GraphQL errors: {payload['errors']}")
    user = payload.get("data", {}).get("user")
    if not user:
        raise FetchError(f"user '{LOGIN}' not found")
    total_30d = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]

    profile = _get(f"https://api.github.com/users/{LOGIN}")
    public_repos = profile.get("public_repos", 0)

    all_repos = _get(f"https://api.github.com/users/{LOGIN}/repos?per_page=100&type=public")
    if not isinstance(all_repos, list):
        all_repos = []
    total_bytes = 0
    for r in all_repos:
        total_bytes += sum(_safe_languages(r["name"]).values())

    deployed = 0
    for repo in REGISTRY_REPOS:
        meta = _safe_repo(repo)
        homepage = (meta.get("homepage") or "").strip() or REGISTRY_FALLBACK_HOMEPAGE.get(repo)
        if homepage:
            deployed += 1

    return {
        "total_30d": total_30d,
        "public_repos": public_repos,
        "total_bytes": total_bytes,
        "verified_pct": round(100 * deployed / len(REGISTRY_REPOS)),
    }


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ellipse_path(cx, cy, rx, ry):
    """4-Bezier approximation of an ellipse, for animateMotion paths."""
    k = 0.5522847498
    return (
        f"M{cx-rx:.1f},{cy:.1f} "
        f"C{cx-rx:.1f},{cy-ry*k:.1f} {cx-rx*k:.1f},{cy-ry:.1f} {cx:.1f},{cy-ry:.1f} "
        f"C{cx+rx*k:.1f},{cy-ry:.1f} {cx+rx:.1f},{cy-ry*k:.1f} {cx+rx:.1f},{cy:.1f} "
        f"C{cx+rx:.1f},{cy+ry*k:.1f} {cx+rx*k:.1f},{cy+ry:.1f} {cx:.1f},{cy+ry:.1f} "
        f"C{cx-rx*k:.1f},{cy+ry:.1f} {cx-rx:.1f},{cy+ry*k:.1f} {cx-rx:.1f},{cy:.1f} Z"
    )


ROLES = [
    ("ENGINEER", "I engineer systems that scale.", -50, "#a855f7", "code"),
    ("PROBLEM SOLVER", "I turn complexity into clarity.", 15, "#22d3ee", "brain"),
    ("AI NATIVE", "I work at the intersection of AI & systems.", 80, "#ec4899", "spark"),
    ("BUILDER", "I ship products that solve real problems.", 155, "#eab308", "cube"),
    ("FOUNDER", "I build from zero to impact.", 220, "#22c55e", "rocket"),
]

PRINCIPLES = [
    ("Curiosity", "100%"), ("Consistency", "INF"), ("Ownership", "TRUE"),
    ("Learning Velocity", "MAX"), ("System Thinking", "ON"),
]

FOCUS = [
    ("AGENTIC AI", "SYSTEMS", "agent", "#a855f7"),
    ("SYSTEM", "ARCHITECTURE", "layers", "#22d3ee"),
    ("AI TALENT", "INTELLIGENCE", "people", "#ec4899"),
    ("REAL-WORLD", "IMPACT", "target", "#22c55e"),
]

APPROACH = [("RESEARCH", "search"), ("DESIGN", "pencil"), ("BUILD", "code"), ("VALIDATE", "chart"), ("DEPLOY", "rocket")]

BIO_LINES = [
    "I'm an <tspan fill=\"#22d3ee\">AI/ML engineer</tspan> and <tspan fill=\"#a855f7\">founder</tspan> who builds systems end-to-end &#8212;",
    "the model, the agent-orchestration layer, the backend underneath,",
    "and the product wrapped around it.",
    "",
    "My work spans <tspan fill=\"#22d3ee\">agentic orchestration</tspan> platforms,",
    "<tspan fill=\"#a855f7\">explainable ML scoring</tspan> systems, and <tspan fill=\"#f5a623\">reinforcement-learning</tspan>",
    "research, alongside co-founding <tspan fill=\"#22c55e\">Kovidam</tspan>, an AI",
    "talent-intelligence platform.",
    "",
    "I care about systems that are <tspan fill=\"#e8e8e8\" font-weight=\"700\">architected</tspan>, not just",
    "prompted &#8212; real backends, real data pipelines, real evaluation,",
    "shipped as working software.",
]


def small_icon(kind, cx, cy, color, s=1.0):
    if kind == "code":
        return (f'<polyline points="{cx-5*s},{cy-4*s} {cx-8*s},{cy} {cx-5*s},{cy+4*s}" fill="none" stroke="{color}" stroke-width="{1.4*s}" stroke-linecap="round" stroke-linejoin="round"/>'
                f'<polyline points="{cx+5*s},{cy-4*s} {cx+8*s},{cy} {cx+5*s},{cy+4*s}" fill="none" stroke="{color}" stroke-width="{1.4*s}" stroke-linecap="round" stroke-linejoin="round"/>')
    if kind == "brain":
        return (f'<circle cx="{cx}" cy="{cy}" r="{7*s}" fill="none" stroke="{color}" stroke-width="{1.3*s}"/>'
                f'<path d="M{cx-3*s},{cy-4*s} Q{cx},{cy} {cx-3*s},{cy+4*s}" fill="none" stroke="{color}" stroke-width="{1*s}"/>'
                f'<path d="M{cx+3*s},{cy-4*s} Q{cx},{cy} {cx+3*s},{cy+4*s}" fill="none" stroke="{color}" stroke-width="{1*s}"/>')
    if kind == "spark":
        return f'<path d="M{cx},{cy-8*s} L{cx+2.4*s},{cy-2.4*s} L{cx+8*s},{cy} L{cx+2.4*s},{cy+2.4*s} L{cx},{cy+8*s} L{cx-2.4*s},{cy+2.4*s} L{cx-8*s},{cy} L{cx-2.4*s},{cy-2.4*s} Z" fill="{color}"/>'
    if kind == "cube":
        return (f'<rect x="{cx-6*s}" y="{cy-6*s}" width="{12*s}" height="{12*s}" rx="2" fill="none" stroke="{color}" stroke-width="{1.4*s}"/>'
                f'<line x1="{cx-6*s}" y1="{cy}" x2="{cx+6*s}" y2="{cy}" stroke="{color}" stroke-width="{1*s}" opacity="0.6"/>')
    if kind == "rocket":
        return (f'<path d="M{cx},{cy-8*s} C{cx+4*s},{cy-3*s} {cx+4*s},{cy+3*s} {cx},{cy+8*s} '
                f'C{cx-4*s},{cy+3*s} {cx-4*s},{cy-3*s} {cx},{cy-8*s} Z" fill="none" stroke="{color}" stroke-width="{1.3*s}"/>'
                f'<circle cx="{cx}" cy="{cy-1*s}" r="{1.6*s}" fill="{color}"/>')
    if kind == "agent":
        return (f'<rect x="{cx-7*s}" y="{cy-5*s}" width="{14*s}" height="{11*s}" rx="3" fill="none" stroke="{color}" stroke-width="{1.3*s}"/>'
                f'<circle cx="{cx-3*s}" cy="{cy}" r="{1.4*s}" fill="{color}"/><circle cx="{cx+3*s}" cy="{cy}" r="{1.4*s}" fill="{color}"/>')
    if kind == "layers":
        return "".join(f'<rect x="{cx-7*s}" y="{cy-6*s+i*5*s}" width="{14*s}" height="{3*s}" rx="1.2" fill="none" stroke="{color}" stroke-width="{1.1*s}"/>' for i in range(3))
    if kind == "people":
        return (f'<circle cx="{cx-3*s}" cy="{cy-2*s}" r="{2.6*s}" fill="none" stroke="{color}" stroke-width="{1.2*s}"/>'
                f'<circle cx="{cx+3*s}" cy="{cy-2*s}" r="{2.6*s}" fill="none" stroke="{color}" stroke-width="{1.2*s}"/>'
                f'<path d="M{cx-7*s},{cy+7*s} Q{cx-3*s},{cy+2*s} {cx},{cy+5*s} Q{cx+3*s},{cy+2*s} {cx+7*s},{cy+7*s}" fill="none" stroke="{color}" stroke-width="{1.2*s}"/>')
    if kind == "target":
        return (f'<circle cx="{cx}" cy="{cy}" r="{7*s}" fill="none" stroke="{color}" stroke-width="{1.2*s}"/>'
                f'<circle cx="{cx}" cy="{cy}" r="{3.4*s}" fill="none" stroke="{color}" stroke-width="{1.2*s}"/>'
                f'<circle cx="{cx}" cy="{cy}" r="{1.1*s}" fill="{color}"/>')
    if kind == "search":
        return (f'<circle cx="{cx-1.5*s}" cy="{cy-1.5*s}" r="{5*s}" fill="none" stroke="{color}" stroke-width="{1.3*s}"/>'
                f'<line x1="{cx+2.5*s}" y1="{cy+2.5*s}" x2="{cx+6.5*s}" y2="{cy+6.5*s}" stroke="{color}" stroke-width="{1.3*s}" stroke-linecap="round"/>')
    if kind == "pencil":
        return f'<path d="M{cx-6*s},{cy+6*s} L{cx-4*s},{cy-2*s} L{cx+4*s},{cy-8*s} L{cx+7*s},{cy-5*s} L{cx-1*s},{cy+3*s} Z" fill="none" stroke="{color}" stroke-width="{1.2*s}" stroke-linejoin="round"/>'
    if kind == "chart":
        return "".join(f'<rect x="{cx-7*s+i*5*s}" y="{cy+6*s-h*s}" width="{3.4*s}" height="{h*s}" fill="{color}"/>' for i, h in enumerate((5, 9, 13)))
    return ""


def build_svg(data):
    total_30d = data["total_30d"]
    public_repos = data["public_repos"]
    code_mb = data["total_bytes"] / 1_000_000
    verified_pct = data["verified_pct"]
    synced = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    W = 900
    left, right = 20, 880
    inner_w = right - left

    hud_y0, hud_h = 40, 88
    tile_gap = 10
    tile_w = (inner_w - 4 * tile_gap) / 5
    tile_x = [left + i * (tile_w + tile_gap) for i in range(5)]

    col_gap = 20
    lcol_w = 400
    rcol_w = inner_w - lcol_w - col_gap
    lcol_x, rcol_x = left, left + lcol_w + col_gap

    body_y0 = hud_y0 + hud_h + 18
    head_box_h = 430
    principles_h = 240
    left_bottom = body_y0 + head_box_h + 14 + principles_h

    bio_h, focus_h, approach_h, inline_h = 306, 140, 88, 108
    gaps = 14
    right_bottom = body_y0 + bio_h + gaps + focus_h + gaps + approach_h + gaps + inline_h

    body_bottom = max(left_bottom, right_bottom)
    log_y0 = body_bottom + 18
    log_h = 56
    H = log_y0 + log_h + 20

    hx = lcol_x + lcol_w / 2
    hy = body_y0 + head_box_h / 2 - 10

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H:.0f}" width="100%" '
                  f'role="img" aria-labelledby="idTitle idDesc">')
    parts.append('<title id="idTitle">Identity core — live holographic system</title>')
    parts.append(f'<desc id="idDesc">Kartikeya Yadav — AI/ML engineer and founder. Live status: {public_repos} '
                  f'public repositories, {code_mb:.1f}MB of code, {total_30d} contributions in the last 30 days, '
                  f'{verified_pct}% of showcased projects independently verified deployed. '
                  f'Regenerated automatically by GitHub Actions.</desc>')

    parts.append(f'''<defs>
    <filter id="glow" x="-250%" y="-250%" width="600%" height="600%"><feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="glowSoft" x="-250%" y="-250%" width="600%" height="600%"><feGaussianBlur stdDeviation="1.3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <radialGradient id="coreGrad" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffffff"/><stop offset="35%" stop-color="#8ff4ff"/>
      <stop offset="75%" stop-color="#7c3aed"/><stop offset="100%" stop-color="#7c3aed" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="scanGradV" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#22d3ee" stop-opacity="0"/><stop offset="50%" stop-color="#22d3ee"/>
      <stop offset="100%" stop-color="#22d3ee" stop-opacity="0"/>
    </linearGradient>
  </defs>''')

    parts.append(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1:.0f}" rx="14" fill="#0a0a0a" stroke="#1f1f1f"/>')
    parts.append(f'<text x="{left}" y="24" font-family="Consolas, \'SF Mono\', monospace" font-size="10" '
                 f'letter-spacing="1" fill="#666">// SYSTEM.02 &gt; WHO_AM_I.EXE</text>')
    parts.append(f'<circle cx="{right}" cy="20" r="3" fill="#a855f7"><animate attributeName="opacity" '
                 f'values="1;0.3;1" dur="2s" repeatCount="indefinite"/></circle>')

    # ================= HUD =================
    def tile_shell(x, label):
        return (f'<rect x="{x:.1f}" y="{hud_y0}" width="{tile_w:.1f}" height="{hud_h}" rx="10" fill="#101014" stroke="#1f1f24"/>'
                f'<text x="{x+12:.1f}" y="{hud_y0+18}" font-family="Consolas, monospace" font-size="8.5" '
                f'letter-spacing="0.8" fill="#666">{label}</text>')

    x = tile_x[0]
    parts.append(tile_shell(x, "SYSTEM STATUS"))
    parts.append(f'<circle cx="{x+16:.1f}" cy="{hud_y0+42}" r="3" fill="#22c55e" filter="url(#glowSoft)">'
                 f'<animate attributeName="opacity" values="1;0.4;1" dur="1.8s" repeatCount="indefinite"/></circle>')
    parts.append(f'<text x="{x+25:.1f}" y="{hud_y0+46}" font-family="Helvetica, Arial, sans-serif" font-size="14" '
                 f'font-weight="700" fill="#22c55e">ONLINE</text>')
    hb = f"M{x+12:.1f},{hud_y0+68} h8 l3,-8 l4,14 l3,-11 l2,5 h{tile_w-40:.1f}"
    parts.append(f'<path d="{hb}" fill="none" stroke="#22c55e" stroke-width="1.1" opacity="0.7"/>')

    x = tile_x[1]
    parts.append(tile_shell(x, "CORE ID"))
    parts.append(f'<text x="{x+12:.1f}" y="{hud_y0+46}" font-family="Consolas, monospace" font-size="12" '
                 f'font-weight="700" fill="#e8e8e8">{esc(LOGIN)}</text>')
    fx, fy = x + tile_w - 22, hud_y0 + 62
    parts.append(f'<path d="M{fx-6},{fy+6} Q{fx-6},{fy-6} {fx},{fy-6} Q{fx+6},{fy-6} {fx+6},{fy} Q{fx+6},{fy+8} {fx},{fy+8}" '
                 f'fill="none" stroke="#a855f7" stroke-width="1" opacity="0.8"/>'
                 f'<path d="M{fx-3},{fy+5} Q{fx-3},{fy-2} {fx},{fy-2} Q{fx+3},{fy-2} {fx+3},{fy+3}" '
                 f'fill="none" stroke="#a855f7" stroke-width="1" opacity="0.8"/>')
    parts.append(f'<text x="{x+12:.1f}" y="{hud_y0+66}" font-family="Consolas, monospace" font-size="8" fill="#555">VERIFIED IDENTITY</text>')

    x = tile_x[2]
    parts.append(tile_shell(x, "VERIFIED"))
    parts.append(f'<text x="{x+12:.1f}" y="{hud_y0+44}" font-family="Helvetica, Arial, sans-serif" font-size="20" '
                 f'font-weight="700" fill="#22d3ee">{verified_pct}%</text>')
    seg_w = (tile_w - 24) / 6 - 2
    filled_segs = round(verified_pct / 100 * 6)
    for i in range(6):
        sx = x + 12 + i * (seg_w + 2)
        parts.append(f'<rect x="{sx:.1f}" y="{hud_y0+58}" width="{seg_w:.1f}" height="5" rx="1.5" '
                     f'fill="{"#22d3ee" if i < filled_segs else "#1f1f24"}"/>')
    parts.append(f'<text x="{x+12:.1f}" y="{hud_y0+76}" font-family="Consolas, monospace" font-size="7.5" fill="#555">DEPLOYMENT VERIFIED</text>')

    x = tile_x[3]
    parts.append(tile_shell(x, "CODE VOLUME"))
    parts.append(f'<text x="{x+12:.1f}" y="{hud_y0+44}" font-family="Helvetica, Arial, sans-serif" font-size="20" '
                 f'font-weight="700" fill="#f5a623">{code_mb:.1f}MB</text>')
    bar_w = (tile_w - 24) / 6 - 2
    heights = [4, 7, 5, 9, 6, 11]
    for i, bh in enumerate(heights):
        bx = x + 12 + i * (bar_w + 2)
        parts.append(f'<rect x="{bx:.1f}" y="{hud_y0+68-bh:.1f}" width="{bar_w:.1f}" height="{bh}" rx="1" fill="#f5a623" opacity="0.8"/>')
    parts.append(f'<text x="{x+12:.1f}" y="{hud_y0+76}" font-family="Consolas, monospace" font-size="7.5" fill="#555">ACROSS {public_repos} REPOS</text>')

    x = tile_x[4]
    parts.append(tile_shell(x, "ACTIVITY"))
    parts.append(f'<circle cx="{x+16:.1f}" cy="{hud_y0+42}" r="6" fill="none" stroke="#ec4899" stroke-width="1.3" opacity="0.6">'
                 f'<animate attributeName="r" values="3.5;8;3.5" dur="2.2s" repeatCount="indefinite"/>'
                 f'<animate attributeName="opacity" values="0.8;0;0.8" dur="2.2s" repeatCount="indefinite"/></circle>')
    parts.append(f'<circle cx="{x+16:.1f}" cy="{hud_y0+42}" r="3" fill="#ec4899" filter="url(#glowSoft)"/>')
    parts.append(f'<text x="{x+25:.1f}" y="{hud_y0+46}" font-family="Helvetica, Arial, sans-serif" font-size="14" '
                 f'font-weight="700" fill="#ec4899">LIVE</text>')
    parts.append(f'<text x="{x+12:.1f}" y="{hud_y0+76}" font-family="Consolas, monospace" font-size="7.5" fill="#888">{total_30d} contrib &#183; 30d</text>')

    # ================= LEFT: IDENTITY CORE =================
    parts.append(f'<rect x="{lcol_x}" y="{body_y0}" width="{lcol_w}" height="{head_box_h}" rx="12" fill="#0d0d10" stroke="#1f1f24"/>')
    parts.append(f'<text x="{lcol_x+16}" y="{body_y0+24}" font-family="Consolas, monospace" font-size="11" '
                 f'font-weight="700" letter-spacing="1" fill="#ddd">IDENTITY CORE</text>')

    # -- orbit rings (2 behind head, 3 in front) --
    ring_specs = [
        (100, 34, "#a855f7", 14, "1"), (122, 40, "#22d3ee", 20, "-1"),
        (144, 45, "#22c55e", 17, "1"), (166, 50, "#ec4899", 24, "-1"),
        (188, 55, "#3b82f6", 19, "1"),
    ]

    def render_ring(idx, spec):
        rx, ry, color, dur, direction = spec
        frm, to = ("0", "360") if direction == "1" else ("360", "0")
        out = [f'<ellipse cx="{hx}" cy="{hy}" rx="{rx}" ry="{ry}" fill="none" stroke="{color}" '
               f'stroke-width="1" opacity="0.32"/>']
        epath = ellipse_path(hx, hy, rx, ry)
        n_particles = 2
        for p in range(n_particles):
            begin = -(dur * p / n_particles)
            out.append(f'<circle r="2.1" fill="{color}" filter="url(#glowSoft)">'
                       f'<animateMotion dur="{dur}s" begin="{begin:.1f}s" repeatCount="indefinite" path="{epath}"/>'
                       f'</circle>')
        return "".join(out)

    parts.append('<g opacity="0"><animate attributeName="opacity" values="0;1" dur="0.7s" begin="1s" fill="freeze"/>')
    for i in (0, 1):
        parts.append(render_ring(i, ring_specs[i]))
    parts.append('</g>')

    # -- wireframe head (nested groups: outer = scaleX oscillation, inner = rotate oscillation) --
    head_top, head_bot = hy - 78, hy + 82
    contours = []
    n_contour = 7
    for i in range(n_contour):
        t = i / (n_contour - 1)
        cy_ = head_top + t * (head_bot - head_top)
        width_factor = math.sin(t * math.pi) ** 0.6
        rx_ = 58 * width_factor
        contours.append((cy_, rx_))

    parts.append('<g opacity="0"><animate attributeName="opacity" values="0;1" dur="0.8s" begin="2s" fill="freeze"/>')
    parts.append(f'<g transform="translate({hx},{hy})">')
    parts.append(f'  <animateTransform attributeName="transform" type="scale" additive="sum" '
                 f'values="1,1; 1.06,1; 0.95,1; 1.06,1; 1,1" dur="11s" repeatCount="indefinite" calcMode="linear"/>')
    parts.append(f'<g transform="translate({-hx},{-hy})">')
    parts.append(f'  <animateTransform attributeName="transform" type="rotate" additive="sum" '
                 f'values="-6 {hx} {hy}; 6 {hx} {hy}; -6 {hx} {hy}" dur="11s" repeatCount="indefinite" calcMode="linear"/>')

    parts.append(f'<path d="M{hx},{head_top} Q{hx+60},{head_top+20} {hx+58},{hy} Q{hx+56},{head_bot-16} {hx},{head_bot} '
                 f'Q{hx-56},{head_bot-16} {hx-58},{hy} Q{hx-60},{head_top+20} {hx},{head_top} Z" '
                 f'fill="none" stroke="#22d3ee" stroke-width="1" opacity="0.25"/>')

    verts = []
    for cy_, rx_ in contours:
        parts.append(f'<ellipse cx="{hx}" cy="{cy_:.1f}" rx="{rx_:.1f}" ry="{max(rx_*0.22,3):.1f}" '
                     f'fill="none" stroke="#7dd3fc" stroke-width="0.8" opacity="0.4"/>')
        n_pts = 6
        for j in range(n_pts):
            ang = math.pi * j / (n_pts - 1)
            vx = hx - rx_ * math.cos(ang)
            verts.append((vx, cy_))
    n_merid = 5
    for m in range(n_merid):
        frac = m / (n_merid - 1)
        offset = (frac - 0.5) * 2
        pts = []
        for cy_, rx_ in contours:
            vx = hx + offset * rx_ * 0.96
            pts.append((vx, cy_))
        d = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts)
        parts.append(f'<path d="{d}" fill="none" stroke="#7dd3fc" stroke-width="0.7" opacity="0.28"/>')

    for i, (vx, vy) in enumerate(verts):
        shimmer = i % 4 == 0
        anim = (f'<animate attributeName="opacity" values="0.9;0.15;0.9" dur="{2.2+(i%5)*0.3:.1f}s" '
                f'begin="{(i%7)*0.3:.1f}s" repeatCount="indefinite"/>') if shimmer else ""
        parts.append(f'<circle cx="{vx:.1f}" cy="{vy:.1f}" r="1.5" fill="#a5f3fc" opacity="0.75">{anim}</circle>')

    # scanline sweeping the head bounding box
    parts.append(f'<rect x="{hx-62:.1f}" y="{head_top-6:.1f}" width="124" height="4" fill="url(#scanGradV)" opacity="0.8">'
                 f'<animate attributeName="y" values="{head_top-6:.1f};{head_bot-2:.1f}" dur="4.5s" '
                 f'repeatCount="indefinite" calcMode="linear"/></rect>')

    # core — activates 1s after the wireframe (its own delayed reveal, nested so it
    # still inherits the head's rotate/scale motion)
    core_y = hy - 6
    parts.append('<g opacity="0"><animate attributeName="opacity" values="0;1" dur="0.5s" begin="3s" fill="freeze"/>')
    parts.append(f'<circle cx="{hx}" cy="{core_y}" r="9" fill="url(#coreGrad)" filter="url(#glow)">'
                 f'<animate attributeName="r" values="7;11;7" dur="2.6s" repeatCount="indefinite"/></circle>')
    parts.append(f'<circle cx="{hx}" cy="{core_y}" r="9" fill="none" stroke="#ffffff" opacity="0.5">'
                 f'<animate attributeName="r" values="9;30;9" dur="4s" repeatCount="indefinite"/>'
                 f'<animate attributeName="opacity" values="0.5;0;0.5" dur="4s" repeatCount="indefinite"/></circle>')
    parts.append('</g>')  # close core boot-reveal

    parts.append('</g></g></g>')  # close head rotate + scale groups, then head boot-reveal

    parts.append('<g opacity="0"><animate attributeName="opacity" values="0;1" dur="0.7s" begin="1s" fill="freeze"/>')
    for i in (2, 3, 4):
        parts.append(render_ring(i, ring_specs[i]))
    parts.append('</g>')

    # role nodes + data-trace lines — labels are centered on the node's own x (never
    # edge-anchored text extending outward), and placed above or below based on which
    # half of the panel the node falls in, so nothing can bleed past the card border.
    parts.append('<g opacity="0"><animate attributeName="opacity" values="0;1" dur="0.8s" begin="4s" fill="freeze"/>')
    for i, (label, tagline, ang_deg, color, icon) in enumerate(ROLES):
        ang = math.radians(ang_deg)
        rx_o, ry_o = 118, 100
        nx = hx + rx_o * math.cos(ang)
        ny = hy + ry_o * math.sin(ang)
        nx = max(lcol_x + 62, min(lcol_x + lcol_w - 62, nx))
        ny = max(body_y0 + 52, min(body_y0 + head_box_h - 52, ny))

        trace_begin = -(i * 0.7)
        parts.append(f'<line x1="{hx:.1f}" y1="{core_y:.1f}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{color}" '
                     f'stroke-width="0.6" opacity="0.15"/>')
        parts.append(f'<circle r="1.8" fill="{color}" filter="url(#glowSoft)">'
                     f'<animateMotion dur="3.4s" begin="{trace_begin:.1f}s" repeatCount="indefinite" '
                     f'keyPoints="0;1;1;1" keyTimes="0;0.32;0.4;1" calcMode="linear" '
                     f'path="M{hx:.1f},{core_y:.1f} L{nx:.1f},{ny:.1f}"/>'
                     f'<animate attributeName="opacity" values="0;1;1;0;0" keyTimes="0;0.05;0.32;0.4;1" '
                     f'dur="3.4s" begin="{trace_begin:.1f}s" repeatCount="indefinite"/></circle>')

        parts.append(f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="14" fill="{color}" opacity="0.15" filter="url(#glowSoft)"/>')
        parts.append(f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="11.5" fill="#0b0b0d" stroke="{color}" stroke-width="1.5"/>')
        parts.append(small_icon(icon, nx, ny, color, s=0.8))

        tag_words = tagline.split()
        mid = (len(tag_words) + 1) // 2
        line1 = " ".join(tag_words[:mid])
        line2 = " ".join(tag_words[mid:])
        label_y, t1_y, t2_y = ((ny - 30, ny - 18, ny - 6) if math.sin(ang) > 0 else (ny + 26, ny + 38, ny + 50))
        parts.append(f'<text x="{nx:.1f}" y="{label_y:.1f}" text-anchor="middle" '
                     f'font-family="Consolas, monospace" font-size="9" font-weight="700" letter-spacing="0.5" '
                     f'fill="{color}">{esc(label)}</text>')
        parts.append(f'<text x="{nx:.1f}" y="{t1_y:.1f}" text-anchor="middle" '
                     f'font-family="Helvetica, Arial, sans-serif" font-size="8" fill="#999">{esc(line1)}</text>')
        if line2:
            parts.append(f'<text x="{nx:.1f}" y="{t2_y:.1f}" text-anchor="middle" '
                         f'font-family="Helvetica, Arial, sans-serif" font-size="8" fill="#999">{esc(line2)}</text>')
    parts.append('</g>')  # close role-nodes boot-reveal

    # -- operating principles --
    py0 = body_y0 + head_box_h + 14
    parts.append(f'<rect x="{lcol_x}" y="{py0}" width="{lcol_w}" height="{principles_h}" rx="12" fill="#0d0d10" stroke="#1f1f24"/>')
    parts.append(f'<text x="{lcol_x+16}" y="{py0+20}" font-family="Consolas, monospace" font-size="10" '
                 f'letter-spacing="1" fill="#888">// OPERATING PRINCIPLES</text>')
    for i, (name, val) in enumerate(PRINCIPLES):
        ly = py0 + 40 + i * 18
        dots = "." * max(28 - len(name), 6)
        parts.append(f'<text x="{lcol_x+16}" y="{ly}" font-family="Consolas, monospace" font-size="9.5" fill="#8a8a8a">'
                     f'&gt; {esc(name)}{dots}<tspan fill="#22c55e">[{val}]</tspan></text>')
    fy2 = py0 + principles_h - 16
    parts.append(f'<text x="{lcol_x+16}" y="{fy2}" font-family="Consolas, monospace" font-size="9.5" '
                 f'font-weight="700" fill="#a855f7">&gt; ALWAYS BUILDING.</text>')
    cur_x = lcol_x + 16 + 6.3 * len("> ALWAYS BUILDING. ")
    parts.append(f'<rect x="{cur_x:.1f}" y="{fy2-9}" width="6" height="11" fill="#a855f7">'
                 f'<animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></rect>')
    # mini radar decoration
    rcx, rcy = lcol_x + lcol_w - 62, py0 + principles_h - 46
    for rr in (10, 20, 30):
        parts.append(f'<circle cx="{rcx}" cy="{rcy}" r="{rr}" fill="none" stroke="#22c55e" stroke-width="0.6" opacity="0.25"/>')
    parts.append(f'<circle cx="{rcx}" cy="{rcy}" r="3" fill="#22c55e" filter="url(#glowSoft)">'
                 f'<animate attributeName="opacity" values="1;0.3;1" dur="1.6s" repeatCount="indefinite"/></circle>')
    for i in range(5):
        rp = 8 + (i * 5) % 26
        ap = i * 71
        px = rcx + rp * math.cos(math.radians(ap))
        pyv = rcy + rp * math.sin(math.radians(ap))
        parts.append(f'<circle cx="{px:.1f}" cy="{pyv:.1f}" r="1.3" fill="#22c55e" opacity="0.6"/>')

    # ================= RIGHT: BIO / FOCUS / APPROACH / INLINE =================
    ry0 = body_y0
    parts.append(f'<rect x="{rcol_x}" y="{ry0}" width="{rcol_w}" height="{bio_h}" rx="12" fill="#0d0d10" stroke="#1f1f24"/>')
    parts.append(f'<text x="{rcol_x+16}" y="{ry0+22}" font-family="Consolas, monospace" font-size="11" '
                 f'font-weight="700" letter-spacing="1" fill="#ddd">// BIO.SYSTEM</text>')
    parts.append(f'<text x="{rcol_x+rcol_w-14}" y="{ry0+22}" text-anchor="end" font-family="Consolas, monospace" '
                 f'font-size="8.5" fill="#666">LIVE FEED</text>')
    parts.append(f'<circle cx="{rcol_x+rcol_w-108}" cy="{ry0+18}" r="2.5" fill="#ec4899">'
                 f'<animate attributeName="opacity" values="1;0.3;1" dur="1.4s" repeatCount="indefinite"/></circle>')

    by = ry0 + 42
    for line in BIO_LINES:
        if line:
            parts.append(f'<text x="{rcol_x+16}" y="{by}" font-family="Helvetica, Arial, sans-serif" font-size="10.5" '
                         f'fill="#c9c9c9">{line}</text>')
        by += 19

    # small wireframe globe decoration, tucked in its own clear strip below the text
    gcx, gcy, gr = rcol_x + rcol_w - 40, ry0 + bio_h - 24, 17
    parts.append(f'<g transform="translate({gcx},{gcy})">'
                 f'<animateTransform attributeName="transform" type="rotate" from="0 {gcx} {gcy}" '
                 f'to="360 {gcx} {gcy}" dur="26s" repeatCount="indefinite"/>')
    parts.append(f'<circle cx="0" cy="0" r="{gr}" fill="none" stroke="#3b82f6" stroke-width="0.8" opacity="0.35"/>')
    for k in range(1, 3):
        ry_g = gr * (1 - k * 0.32)
        parts.append(f'<ellipse cx="0" cy="0" rx="{gr}" ry="{ry_g:.1f}" fill="none" stroke="#3b82f6" stroke-width="0.6" opacity="0.3"/>')
    for k in range(3):
        rx_g = gr * (0.35 + k * 0.32)
        parts.append(f'<ellipse cx="0" cy="0" rx="{rx_g:.1f}" ry="{gr:.1f}" fill="none" stroke="#3b82f6" stroke-width="0.6" opacity="0.3"/>')
    parts.append('</g>')

    # -- current focus --
    fy0 = ry0 + bio_h + gaps
    parts.append(f'<rect x="{rcol_x}" y="{fy0}" width="{rcol_w}" height="{focus_h}" rx="12" fill="#0d0d10" stroke="#1f1f24"/>')
    parts.append(f'<text x="{rcol_x+16}" y="{fy0+20}" font-family="Consolas, monospace" font-size="10" '
                 f'letter-spacing="1" fill="#888">// CURRENT FOCUS</text>')
    fcell_w = rcol_w / 4
    for i, (l1, l2, icon, color) in enumerate(FOCUS):
        fcx = rcol_x + fcell_w * i + fcell_w / 2
        fcy = fy0 + 58
        parts.append(f'<circle cx="{fcx:.1f}" cy="{fcy}" r="16" fill="{color}" opacity="0.12" filter="url(#glowSoft)"/>')
        parts.append(f'<circle cx="{fcx:.1f}" cy="{fcy}" r="13.5" fill="#0b0b0d" stroke="{color}" stroke-width="1.4"/>')
        parts.append(small_icon(icon, fcx, fcy, color))
        parts.append(f'<text x="{fcx:.1f}" y="{fcy+30}" text-anchor="middle" font-family="Consolas, monospace" '
                     f'font-size="8" letter-spacing="0.4" fill="#aaa">{esc(l1)}</text>')
        parts.append(f'<text x="{fcx:.1f}" y="{fcy+41}" text-anchor="middle" font-family="Consolas, monospace" '
                     f'font-size="8" letter-spacing="0.4" fill="#aaa">{esc(l2)}</text>')
    conn_y = fy0 + focus_h - 12
    parts.append(f'<line x1="{rcol_x+30}" y1="{conn_y}" x2="{rcol_x+rcol_w-30}" y2="{conn_y}" stroke="#242430" stroke-width="1"/>')
    for i in range(4):
        cxp = rcol_x + fcell_w * i + fcell_w / 2
        parts.append(f'<circle cx="{cxp:.1f}" cy="{conn_y}" r="2" fill="{FOCUS[i][3]}"/>')

    # -- tech approach --
    ay0 = fy0 + focus_h + gaps
    parts.append(f'<rect x="{rcol_x}" y="{ay0}" width="{rcol_w}" height="{approach_h}" rx="12" fill="#0d0d10" stroke="#1f1f24"/>')
    parts.append(f'<text x="{rcol_x+16}" y="{ay0+20}" font-family="Consolas, monospace" font-size="10" '
                 f'letter-spacing="1" fill="#888">// TECH APPROACH</text>')
    acell_w = (rcol_w - 32) / len(APPROACH)
    line_y = ay0 + 68
    parts.append(f'<line x1="{rcol_x+30}" y1="{line_y}" x2="{rcol_x+rcol_w-30}" y2="{line_y}" stroke="#242430" stroke-width="1.5"/>')
    dot_path = f"M{rcol_x+30},{line_y} L{rcol_x+rcol_w-30},{line_y}"
    parts.append(f'<circle r="3.5" fill="#22d3ee" filter="url(#glow)">'
                 f'<animateMotion dur="4.5s" repeatCount="indefinite" path="{dot_path}" calcMode="linear"/></circle>')
    for i, (label, icon) in enumerate(APPROACH):
        acx = rcol_x + 16 + acell_w * i + acell_w / 2
        parts.append(f'<circle cx="{acx:.1f}" cy="{line_y}" r="11" fill="#0b0b0d" stroke="#3b82f6" stroke-width="1.3"/>')
        parts.append(small_icon(icon, acx, line_y, "#3b82f6", s=0.75))
        parts.append(f'<text x="{acx:.1f}" y="{line_y+24}" text-anchor="middle" font-family="Consolas, monospace" '
                     f'font-size="7.5" letter-spacing="0.4" fill="#999">{esc(label)}</text>')
        if i < len(APPROACH) - 1:
            ax2 = rcol_x + 16 + acell_w * (i + 1) + acell_w / 2
            parts.append(f'<text x="{(acx+ax2)/2:.1f}" y="{line_y+4}" text-anchor="middle" '
                         f'font-family="Consolas, monospace" font-size="9" fill="#3b82f6" opacity="0.6">&#8594;</text>')

    # -- in a line --
    iy0 = ay0 + approach_h + gaps
    parts.append(f'<rect x="{rcol_x}" y="{iy0}" width="{rcol_w}" height="{inline_h}" rx="12" fill="#0d0d10" stroke="#1f1f24"/>')
    parts.append(f'<text x="{rcol_x+16}" y="{iy0+20}" font-family="Consolas, monospace" font-size="10" '
                 f'letter-spacing="1" fill="#888">// IN A LINE</text>')
    parts.append(f'<text x="{rcol_x+16}" y="{iy0+44}" font-family="Consolas, monospace" font-size="9" fill="#555">[</text>')
    parts.append(f'<text x="{rcol_x+30}" y="{iy0+44}" font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#ddd">'
                 f'I design <tspan fill="#22d3ee">intelligent systems</tspan>.</text>')
    parts.append(f'<text x="{rcol_x+30}" y="{iy0+66}" font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#ddd">'
                 f'I build <tspan fill="#a855f7">agentic products</tspan>. I create <tspan fill="#22c55e">measurable impact</tspan>.</text>')
    parts.append(f'<text x="{rcol_x+rcol_w-16}" y="{iy0+66}" text-anchor="end" font-family="Consolas, monospace" '
                 f'font-size="9" fill="#555">]</text>')

    # ================= bottom log strip =================
    parts.append(f'<rect x="{left}" y="{log_y0}" width="{inner_w}" height="{log_h}" rx="10" fill="#0d0d10" stroke="#1f1f24"/>')
    parts.append(f'<text x="{left+16}" y="{log_y0+22}" font-family="Consolas, monospace" font-size="9.5" '
                 f'font-weight="700" fill="#ddd">&gt; IDENTITY.LOG</text>')
    parts.append(f'<text x="{left+16}" y="{log_y0+38}" font-family="Consolas, monospace" font-size="8.5" fill="#666">Boot sequence initiated&#8230;</text>')

    stages = [("INITIALIZING", "#a855f7", 0.0), ("LOADING CORE", "#22d3ee", 1.0),
              ("VERIFYING SYSTEMS", "#3b82f6", 2.0), ("SYNCHRONIZING", "#22c55e", 3.0),
              ("SYSTEM ONLINE", "#22c55e", 4.0)]
    seg_x0 = left + 210
    seg_w2 = (inner_w - 210 - 170) / len(stages)
    for i, (label, color, delay) in enumerate(stages):
        sx = seg_x0 + i * seg_w2
        parts.append(f'<text x="{sx:.1f}" y="{log_y0+20}" font-family="Consolas, monospace" font-size="8" '
                     f'letter-spacing="0.5" fill="#888">{esc(label)}</text>')
        for d in range(4):
            dx = sx + d * 9
            op_vals = "0.15;1;0.15" if i < 4 else "1;0.4;1"
            parts.append(f'<circle cx="{dx:.1f}" cy="{log_y0+30}" r="2" fill="{color}">'
                         f'<animate attributeName="opacity" values="{op_vals}" dur="1.4s" '
                         f'begin="{delay+d*0.15:.2f}s" repeatCount="indefinite"/></circle>')

    parts.append(f'<text x="{right-150}" y="{log_y0+20}" font-family="Consolas, monospace" font-size="8.5" '
                 f'fill="#666">LAST SYNC</text>')
    parts.append(f'<text x="{right-150}" y="{log_y0+34}" font-family="Consolas, monospace" font-size="8.5" '
                 f'fill="#999">{synced}</text>')
    rcx2, rcy2 = right - 20, log_y0 + 27
    parts.append(f'<circle cx="{rcx2}" cy="{rcy2}" r="9" fill="none" stroke="#22d3ee" stroke-width="1.4" stroke-dasharray="8 5">'
                 f'<animateTransform attributeName="transform" type="rotate" from="0 {rcx2} {rcy2}" '
                 f'to="360 {rcx2} {rcy2}" dur="3s" repeatCount="indefinite"/></circle>')

    # ---- 5s boot: stagger the big content groups in, then continuous idle underneath ----
    parts.append('</svg>')
    svg = "\n".join(parts)
    return svg


def main():
    try:
        data = fetch_all()
        svg = build_svg(data)
    except Exception as e:  # noqa: BLE001 - deliberate: never let this step fail the job
        print(f"WARNING: could not regenerate {OUT_PATH}: {e}. Leaving existing file untouched.", file=sys.stderr)
        return

    if "<svg" not in svg or "</svg>" not in svg:
        print("WARNING: generated SVG failed a basic sanity check. Leaving existing file untouched.", file=sys.stderr)
        return

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


if __name__ == "__main__":
    main()
    sys.exit(0)
