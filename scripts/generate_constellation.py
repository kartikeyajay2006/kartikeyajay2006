#!/usr/bin/env python3
"""Generate assets/project-constellation.svg — the section 06 "Flagship
Systems" board.

A product-catalogue layout: fifteen systems in five domains, each card with a
line icon, its name and category, a two-line pitch, its stack, its status
(live app, project site or source) and one proof metric — the hardest number
its own repository reports (attacks held, rules, tests, tools, gates). The
header totals the systems, the live ones and the tests the repositories
report.

Motion is deliberately restrained: cards settle in once, a thin light runs
around each card's border on a slow loop, and live status dots breathe.

Content is curated, not fetched: every system is a real, public repository
and every pitch, stack line and metric is taken from that repository's own
README. LIVE marks a web app whose homepage answered HTTP 200 when this was
written; SITE is a project page for something you install.

SVG notes (see generate_signal.py): all motion is SMIL and nothing uses
<use>/<mpath>. Everything is visible without SMIL.

Never-fail contract: this script always exits 0. Any problem is logged to
stderr and the existing output file is left untouched.
"""
import os
import sys

OUT_PATH = os.environ.get("OUT_PATH", "assets/project-constellation.svg")

W = 900
PAD = 24
GAP = 14
CARD_W = (W - 2 * PAD - 2 * GAP) / 3
CARD_H = 166
LANE_LABEL = 30          # lane label row above its cards
LANE_GAP = 20
TOP = 136                # first lane starts here
EASE = "0.42 0 0.58 1"
MONO = "ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace"
SANS = "-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif"

INK, INK2, INK3, INK4 = "#fafafa", "#a1a1aa", "#71717a", "#52525b"

LANES = [
    ("01", "Agents that act", "#38bdf8"),
    ("02", "Agent governance", "#818cf8"),
    ("03", "Intelligent systems", "#c084fc"),
    ("04", "Developer tools", "#fbbf24"),
    ("05", "Products and ML", "#f472b6"),
]

# (lane, name, category, icon, pitch lines, stack, status, metric, metric label)
SYSTEMS = [
    (0, "AEGIS", "AGENTIC · AIR-GAPPED", "shield",
     ["Local models, clause-cited formulas, two", "sign-offs and a signed audit record."],
     "FastAPI · Next.js · Ollama · SQLite", "source", "31/31", "attacks held on a live host"),
    (0, "ForgeSRE", "AGENTIC · SRE", "pulse",
     ["Proves an incident's cause in a sandbox,", "then stops for a human before rollback."],
     "Python · MCP · Postgres · Prometheus", "source", "17", "MCP tools, one human gate"),
    (0, "EraseOps", "AGENTIC · PRIVACY", "erase",
     ["Erasure as a production change: rehearsed,", "approved by plan hash, verified clean."],
     "TypeScript · LangGraph · Postgres · MinIO", "source", "0", "personal records left after the rescan"),
    (1, "Chakraview", "AGENT OPS · COMMAND CENTER", "layers",
     ["Runs agent fleets in parallel, traces every", "decision, holds unsure results for review."],
     "Next.js · Fastify · SQLite · OpenAI", "live", "0.7", "confidence gate on every result"),
    (1, "AgentFlow OS", "GOVERNANCE · RISK TIERS", "flow",
     ["Scores each agent action into risk tiers;", "critical actions need two human approvals."],
     "Next.js · FastAPI · Postgres · Redis", "source", "4", "risk tiers, two sign-offs for critical"),
    (1, "B2A Governance", "GOVERNANCE · BUSINESS-TO-AGENT", "chain",
     ["Every agent action policy-checked, routed,", "billed exactly and sealed in an audit chain."],
     "FastAPI · SQLAlchemy · Prometheus", "source", "SHA-256", "hash-chained audit trail"),
    (2, "Evidence Console", "INTELLIGENCE · MULTIMODAL RAG", "graph",
     ["Video, audio, images and PDFs in one graph;", "every answer cites its exact second or page."],
     "FastAPI · React · Neo4j · pgvector", "live", "4", "modalities in one cited graph"),
    (2, "Kovidam Skill Graph", "KOVIDAM · HIRING SIGNALS", "bars",
     ["Ranks candidates on engineering evidence", "from GitHub and five coding platforms."],
     "FastAPI · React · Qdrant · Postgres", "live", "3", "scoring gates before any rank"),
    (2, "Kovidam AI Interview", "KOVIDAM · AI INTERVIEWS", "chat",
     ["First-round interviews that run themselves,", "grounded in each candidate's own resume."],
     "FastAPI · Next.js · Redis · Groq", "live", "1", "click invites a job's candidates"),
    (3, "JKY-Radar", "DEV TOOL · API CONTRACTS", "radar",
     ["Diffs two API contracts: what breaks, which", "clients it hits, and whether to ship."],
     "MongoDB · Express · React · Three.js", "live", "157", "versioned, direction-aware rules"),
    (3, "JKY Terminal", "DEV TOOL · DESKTOP", "terminal",
     ["A local-first AI terminal: shells outlive", "the window, and it asks before it acts."],
     "Rust · Tauri · React · xterm.js", "site", "3,639", "tests · 22 Rust crates"),
    (3, "my-localmcp", "DEV TOOL · MCP SERVER", "plug",
     ["Offline MCP server giving coding agents", "fast, deterministic repository context."],
     "Python · SQLite FTS5 · Ollama · MCP", "source", "8–10×", "less context than raw files"),
    (4, "JKY-Folder", "PRODUCT · APPLICATION DOCUMENTS", "folder",
     ["Instruction PDFs become page-cited", "checklists; documents checked against them."],
     "React · Express · SQLite · Tesseract", "source", "589", "tests · 61 browser journeys"),
    (4, "GitVeda", "PRODUCT · LEARN GIT", "branch",
     ["Learn Git by playing it: a real in-browser", "terminal, AI hints, XP and a leaderboard."],
     "React · Vite · Firebase · OpenAI", "live", "30", "levels, from init to bisect"),
    (4, "DealForge", "ML · REINFORCEMENT LEARNING", "scale",
     ["An RL environment where a buyer learns", "fair, low-risk deals against four parties."],
     "Python · TRL · PPO · Qwen2.5", "source", "5", "reward terms, fairness included"),
]
# The tests the repositories report: JKY Terminal 2,324 + 1,315; JKY-Radar 535 + 23;
# JKY-Folder 528 + 61; ForgeSRE 63 + 12 + 4.
TESTS_REPORTED = 2324 + 1315 + 535 + 23 + 528 + 61 + 63 + 12 + 4

STATUS = {"live": ("LIVE", "#4ade80"), "site": ("SITE", "#38bdf8"), "source": ("SOURCE", INK4)}

ICONS = {  # 24 x 24 line icons
    "shield": '<path d="M12 3l7 3v5.5c0 4.4-3 8-7 9.5-4-1.5-7-5.1-7-9.5V6z"/><path d="M9 12l2 2 4-4"/>',
    "pulse": '<path d="M3 12h4l2-5 3 10 2.5-7 1.5 2h5"/>',
    "erase": '<path d="M4 7h16M9.5 7V4.5h5V7"/><path d="M6 7l1 13h10l1-13"/><path d="M9.5 13.5l2 2 3.5-3.5"/>',
    "layers": '<path d="M12 3l9 4.5-9 4.5-9-4.5z"/><path d="M3 12l9 4.5 9-4.5"/><path d="M3 16.5L12 21l9-4.5"/>',
    "flow": '<circle cx="6" cy="6" r="2.4"/><circle cx="18" cy="6" r="2.4"/><circle cx="12" cy="18" r="2.4"/><path d="M7.4 8l3.4 7.8M16.6 8l-3.4 7.8M8.4 6h7.2"/>',
    "chain": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "graph": '<circle cx="5" cy="6" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="18" cy="18" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="12" cy="12" r="2.4"/><path d="M6.6 7.3l3.6 3.3M17.4 6.4l-3.7 4M16.4 16.6l-2.8-2.9M7.6 16.7l2.7-3.1"/>',
    "bars": '<path d="M4 20h16"/><path d="M7 20v-6M12 20V9M17 20V4"/>',
    "chat": '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9.5h8M8 12.5h5"/>',
    "radar": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><path d="M12 12l6-6"/><circle cx="8.5" cy="14.5" r="1" fill="currentColor"/>',
    "terminal": '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/><path d="M7 10l3 2.5L7 15M12.5 15.5h4.5"/>',
    "plug": '<path d="M9 3v4M15 3v4"/><path d="M6 7h12v3.5a6 6 0 0 1-12 0z"/><path d="M12 16.5V21"/>',
    "folder": '<path d="M3 6h6l2 2.5h10V19H3z"/><path d="M9 13.5l2 2 4-4"/>',
    "branch": '<circle cx="6" cy="5.5" r="2.2"/><circle cx="6" cy="18.5" r="2.2"/><circle cx="18" cy="8" r="2.2"/><path d="M6 7.7v8.6M18 10.2c0 4-6.5 2.5-11.2 6.6"/>',
    "scale": '<path d="M12 4v16M7 20h10M5 7h14"/><path d="M5 7l-2.5 6a2.5 2.5 0 0 0 5 0zM19 7l-2.5 6a2.5 2.5 0 0 0 5 0z"/>',
}


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def breathe(attr, values, dur, begin="0s"):
    n = len(values.split(";"))
    kt = ";".join(f"{i / (n - 1):.3f}" for i in range(n))
    return (f'<animate attributeName="{attr}" values="{values}" keyTimes="{kt}" calcMode="spline" '
            f'keySplines="{";".join([EASE] * (n - 1))}" dur="{dur}" begin="{begin}" repeatCount="indefinite"/>')


def icon(kind, col, x, y, size=16):
    s = size / 24
    return (f'<g transform="translate({x:.1f},{y:.1f}) scale({s:.4f})" fill="none" stroke="{col}" color="{col}" '
            f'stroke-width="{1.7 / s:.3f}" stroke-linecap="round" stroke-linejoin="round">{ICONS[kind]}</g>')


# Helvetica / Arial bold advance widths in em, close enough for the other system sans fonts.
_EM = {**{d: 0.556 for d in "0123456789"}, "/": 0.278, ".": 0.278, ",": 0.278, "-": 0.333, "–": 0.556,
       "×": 0.584, "S": 0.667, "H": 0.722, "A": 0.722}


def metric_width(s, size):
    return sum(_EM.get(ch, 0.62) for ch in s) * size


def lane_y(i):
    return TOP + i * (LANE_LABEL + CARD_H + LANE_GAP)


def card(i, sysd, col_idx):
    lane, name, cat, ico, pitch, stack, status, metric, mlabel = sysd
    _, _, col = LANES[lane]
    x = PAD + col_idx * (CARD_W + GAP)
    y = lane_y(lane) + LANE_LABEL
    w, h, r = CARD_W, CARD_H, 12
    perim = 2 * (w + h) - (8 - 2 * 3.14159) * r
    delay = 0.15 + i * 0.05
    k = delay / (delay + 0.7)
    out = [f'<g><animate attributeName="opacity" values="0;0;1" keyTimes="0;{k:.3f};1" dur="{delay + 0.7:.2f}s" fill="freeze"/>'
           f'<animateTransform attributeName="transform" type="translate" values="0,10;0,10;0,0" keyTimes="0;{k:.3f};1" '
           f'dur="{delay + 0.7:.2f}s" calcMode="spline" keySplines="{EASE};0.16 1 0.3 1" fill="freeze"/>']
    out.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{h}" rx="{r}" fill="url(#cardFill)" stroke="#24242b"/>')
    # a thin light running around the border
    out.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{h}" rx="{r}" fill="none" stroke="{col}" stroke-width="1.2" '
               f'stroke-dasharray="{perim * 0.16:.1f} {perim:.1f}" stroke-linecap="round" opacity="0.85" filter="url(#edgeGlow)">'
               f'<animate attributeName="stroke-dashoffset" values="0;{-perim:.1f}" dur="11s" begin="{-i * 0.73:.2f}s" '
               f'repeatCount="indefinite"/></rect>')
    out.append(f'<rect x="{x + 18:.1f}" y="{y}" width="52" height="1.6" fill="{col}"/>')
    # icon tile, name, category
    out.append(f'<rect x="{x + 16:.1f}" y="{y + 18}" width="30" height="30" rx="8" fill="{col}" fill-opacity="0.1" '
               f'stroke="{col}" stroke-opacity="0.35"/>')
    out.append(icon(ico, col, x + 23, y + 25))
    out.append(f'<text x="{x + 56:.1f}" y="{y + 32}" font-family="{SANS}" font-size="15" font-weight="600" '
               f'letter-spacing="-0.2" fill="{INK}">{esc(name)}</text>')
    out.append(f'<text x="{x + 56:.1f}" y="{y + 46}" font-family="{MONO}" font-size="8" letter-spacing="0.9" '
               f'fill="{INK3}">{esc(cat)}</text>')
    label, scol = STATUS[status]
    sx = x + w - 16
    if status == "source":
        out.append(f'<text x="{sx:.1f}" y="{y + 30}" text-anchor="end" font-family="{MONO}" font-size="8.5" '
                   f'letter-spacing="1" fill="{scol}">{label}</text>')
    else:
        tw = len(label) * 6.1
        out.append(f'<circle cx="{sx - tw - 7:.1f}" cy="{y + 27}" r="2.8" fill="{scol}"/>')
        if status == "live":
            out.append(f'<circle cx="{sx - tw - 7:.1f}" cy="{y + 27}" r="2.8" fill="none" stroke="{scol}" stroke-width="1">'
                       f'{breathe("r", "2.8;7;7", "2.4s", f"{i * 0.3:.1f}s")}{breathe("opacity", "0.8;0;0", "2.4s", f"{i * 0.3:.1f}s")}</circle>')
        out.append(f'<text x="{sx:.1f}" y="{y + 30}" text-anchor="end" font-family="{MONO}" font-size="8.5" '
                   f'letter-spacing="1" fill="{scol}">{label}</text>')
    # pitch
    for m, line in enumerate(pitch):
        out.append(f'<text x="{x + 16:.1f}" y="{y + 72 + m * 16}" font-family="{SANS}" font-size="11.3" '
                   f'fill="{INK2}">{esc(line)}</text>')
    out.append(f'<line x1="{x + 16:.1f}" y1="{y + 102}" x2="{x + w - 16:.1f}" y2="{y + 102}" stroke="#202027"/>')
    # proof metric
    mw = metric_width(metric, 21) - 0.4 * len(metric)
    out.append(f'<text x="{x + 15:.1f}" y="{y + 129}" font-family="{SANS}" font-size="21" font-weight="700" '
               f'letter-spacing="-0.4" fill="{col}">{esc(metric)}</text>')
    out.append(f'<text x="{x + 15 + mw + 9:.1f}" y="{y + 128}" font-family="{MONO}" font-size="8.6" fill="{INK2}">{esc(mlabel)}</text>')
    # stack
    out.append(f'<text x="{x + 16:.1f}" y="{y + 151}" font-family="{MONO}" font-size="8.8" fill="{INK3}">{esc(stack)}</text>')
    out.append('</g>')
    return "".join(out)


def build_svg():
    n = len(SYSTEMS)
    live = sum(1 for s in SYSTEMS if s[6] == "live")
    H = lane_y(len(LANES) - 1) + LANE_LABEL + CARD_H + 58
    p = []
    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-labelledby="constTitle constDesc">')
    p.append('<title id="constTitle">Flagship Systems</title>')
    desc = "; ".join(f"{s[1]} ({s[2].title()}): {' '.join(s[4])} Proof: {s[7]} {s[8]}. Stack: {s[5]}. "
                     f"{STATUS[s[6]][0].title()}." for s in SYSTEMS)
    p.append(f'<desc id="constDesc">{n} flagship systems in {len(LANES)} domains, {live} live, '
             f'{TESTS_REPORTED:,} tests reported across their repositories. {esc(desc)}</desc>')
    p.append(f'''<defs>
    <clipPath id="frame"><rect width="{W}" height="{H}" rx="16"/></clipPath>
    <radialGradient id="topLight" cx="0.5" cy="0" r="0.9"><stop offset="0" stop-color="#1c1c26"/><stop offset="0.55" stop-color="#0b0b0e"/><stop offset="1" stop-color="#09090b"/></radialGradient>
    <linearGradient id="cardFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#141418"/><stop offset="1" stop-color="#0e0e11"/></linearGradient>
    <linearGradient id="rule" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2a2a33"/><stop offset="1" stop-color="#2a2a33" stop-opacity="0"/></linearGradient>
    <linearGradient id="titleInk" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#c7c7d1"/></linearGradient>
    <filter id="edgeGlow" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="1.3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>''')
    p.append('<g clip-path="url(#frame)">')
    p.append(f'<rect width="{W}" height="{H}" fill="url(#topLight)"/>')

    # ---- header: statement on the left, three totals on the right
    p.append(f'<text x="{PAD}" y="38" font-family="{MONO}" font-size="9.5" letter-spacing="1.8" fill="{INK3}">'
             f'FLAGSHIP SYSTEMS · 06</text>')
    p.append(f'<text x="{PAD - 1}" y="72" font-family="{SANS}" font-size="25" font-weight="700" letter-spacing="-0.6" '
             f'fill="url(#titleInk)">Built to act. Governed to be trusted.</text>')
    p.append(f'<text x="{PAD}" y="96" font-family="{SANS}" font-size="12.5" fill="{INK2}">'
             f'Fifteen systems in five domains, each with the proof its own repository reports.</text>')
    stats = [(f"{n}", "SYSTEMS", INK), (f"{live}", "LIVE", "#4ade80"), (f"{TESTS_REPORTED:,}", "TESTS REPORTED", INK)]
    sx = W - PAD
    for val, lab, col in reversed(stats):
        p.append(f'<text x="{sx}" y="70" text-anchor="end" font-family="{SANS}" font-size="24" font-weight="700" '
                 f'letter-spacing="-0.5" fill="{col}">{val}</text>')
        p.append(f'<text x="{sx}" y="88" text-anchor="end" font-family="{MONO}" font-size="8.5" letter-spacing="1.2" '
                 f'fill="{INK3}">{lab}</text>')
        sx -= max(len(val) * 13.5, len(lab) * 6.3) + 28
    p.append(f'<line x1="{PAD}" y1="114" x2="{W - PAD}" y2="114" stroke="#1f1f26"/>')

    # ---- lanes
    per_lane = {}
    for s in SYSTEMS:
        per_lane.setdefault(s[0], []).append(s)
    for li, (num, name, col) in enumerate(LANES):
        y = lane_y(li) + 17
        p.append(f'<text x="{PAD}" y="{y}" font-family="{MONO}" font-size="9.5" letter-spacing="1.6" fill="{col}">{num}</text>')
        p.append(f'<text x="{PAD + 24}" y="{y}" font-family="{MONO}" font-size="9.5" letter-spacing="1.6" fill="{INK2}">'
                 f'{esc(name.upper())}</text>')
        lx = PAD + 24 + len(name) * 7.3 + 14
        p.append(f'<line x1="{lx:.1f}" y1="{y - 3.5}" x2="{W - PAD}" y2="{y - 3.5}" stroke="url(#rule)"/>')
    i = 0
    for li in range(len(LANES)):
        for col_idx, s in enumerate(per_lane.get(li, [])):
            p.append(card(i, s, col_idx))
            i += 1

    # ---- footer
    fy = H - 26
    p.append(f'<line x1="{PAD}" y1="{fy - 18}" x2="{W - PAD}" y2="{fy - 18}" stroke="#1f1f26"/>')
    p.append(f'<text x="{PAD}" y="{fy}" font-family="{MONO}" font-size="8.8" letter-spacing="0.6" fill="{INK3}">'
             f'Every figure is the one the system\'s own repository reports.</text>')
    p.append(f'<circle cx="{W - 286}" cy="{fy - 3}" r="2.8" fill="#4ade80"/>'
             f'<text x="{W - 278}" y="{fy}" font-family="{MONO}" font-size="8.8" letter-spacing="0.6" fill="{INK3}">LIVE APP</text>'
             f'<circle cx="{W - 206}" cy="{fy - 3}" r="2.8" fill="#38bdf8"/>'
             f'<text x="{W - 198}" y="{fy}" font-family="{MONO}" font-size="8.8" letter-spacing="0.6" fill="{INK3}">PROJECT SITE</text>'
             f'<text x="{W - PAD}" y="{fy}" text-anchor="end" font-family="{MONO}" font-size="8.8" letter-spacing="0.6" '
             f'fill="{INK4}">SOURCE = RUN IT</text>')
    p.append('</g>')
    p.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="16" fill="none" stroke="#202028"/>')
    p.append('</svg>')
    return "\n".join(p)


def main():
    try:
        svg = build_svg()
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: flagship board generation failed, leaving existing file untouched: {e}", file=sys.stderr)
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
