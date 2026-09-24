#!/usr/bin/env python3
"""Generate assets/project-constellation.svg — the section 06 "Flagship
Systems" board: nine systems in three lanes (Agentic, Intelligent, ML /
Tooling / Product), each rendered as a glass panel with an animated icon
badge, a one-line pitch, stack chips, and a LIVE / SOURCE status, hung off
lane rails that carry traveling energy pulses.

Honesty note (see also generate_atlas.py): SVG has no real 3D, hover, or
JavaScript, and GitHub strips both <script> and any inline <style> from
rendered README markdown — this holds whether the SVG is embedded via <img>
or written inline, so there is no way to express :hover or cursor-tracking
here. "Alive" comes entirely from continuous ambient SMIL animation (rail
pulses, rotating badge rings, a scanline sweep and a panel-by-panel border
ripple that replay every CYCLE seconds) rather than any pointer interaction.

Unlike the Engineering Atlas, panel text never fades out: this board is
text-heavy and meant to be read, so panels only play a one-shot entrance.
The base opacity of every panel is 1 and the entrance is an animation with
fill="freeze" — renderers that ignore SMIL still show the full board.
Every animated element is fully self-contained (own path/values, no
<use>/<mpath> href indirection), because GitHub's image proxy strips
internal href/xlink:href fragment references.

Content is curated, not fetched: the nine systems below are real, public
repositories, and every pitch/stack line is taken from that repository's
own README or dependency manifests — no invented systems, no fabricated
stats. LIVE marks a repo whose homepage URL answered HTTP 200 when this
board was written. There is no live-data workflow for this asset (same as
engineering-atlas.svg / hero-banner.svg / trajectory.svg).

Never-fail contract: this script always exits 0. Any problem is logged
to stderr and the script leaves the existing output file untouched.
"""
import os
import random
import sys

OUT_PATH = os.environ.get("OUT_PATH", "assets/project-constellation.svg")

W = 900
PAD = 20
GAP = 16
PANEL_W = (W - 2 * PAD - 2 * GAP) / 3  # ≈ 276
PANEL_H = 160
LANE_HEAD = 38   # lane label + rail, above its panels
LANE_GAP = 22
TOP = 72         # first lane starts below the header strip
CYCLE = 10.0
EASE = "0.42 0 0.58 1"

MONO = "Consolas, 'SF Mono', monospace"
SANS = "Helvetica, Arial, sans-serif"

LANES = [
    {"id": "LANE 01", "name": "AGENTIC SYSTEMS", "color": "#22d3ee"},
    {"id": "LANE 02", "name": "INTELLIGENT SYSTEMS", "color": "#a855f7"},
    {"id": "LANE 03", "name": "ML · TOOLING · PRODUCT", "color": "#f5a623"},
]

SYSTEMS = [
    # ---- lane 01 : agentic ----
    {"lane": 0, "name": "AEGIS", "tag": "AGENTIC SYSTEM · ON-PREM", "color": "#22d3ee", "icon": "shield",
     "pitch": ["Sovereign agentic workbench — governed", "model routing, sandboxed code, signed audit."],
     "stack": ["FastAPI", "Next.js", "Ollama", "SQLite"], "live": False},
    {"lane": 0, "name": "multi-layer_orchestation", "tag": "AGENTIC SYSTEM · CHAKRAVIEW", "color": "#22d3ee",
     "icon": "layers",
     "pitch": ["Orchestration control plane — human-in-", "the-loop approval, RBAC, audit & replay."],
     "stack": ["Next.js", "Fastify", "Kafka", "Postgres"], "live": True},
    {"lane": 0, "name": "agent--flow", "tag": "AGENTIC SYSTEM · AGENTFLOW OS", "color": "#22d3ee", "icon": "flow",
     "pitch": ["Governance middleware — policy risk tiers", "(low → critical) with tiered human sign-off."],
     "stack": ["Next.js", "FastAPI", "Postgres", "Redis"], "live": False},
    # ---- lane 02 : intelligent ----
    {"lane": 1, "name": "Multimodal Evidence Console", "tag": "INTELLIGENT SYSTEM · RAG", "color": "#a855f7",
     "icon": "graph",
     "pitch": ["Video, audio, images & PDFs → a knowledge", "graph; every answer cites its exact source."],
     "stack": ["FastAPI", "React", "Neo4j", "Postgres"], "live": True},
    {"lane": 1, "name": "Kovidam-Skill-Graph", "tag": "INTELLIGENT SYSTEM · KOVIDAM", "color": "#a855f7",
     "icon": "score",
     "pitch": ["Explainable technical-hiring scoring and", "semantic shortlisting across coding signals."],
     "stack": ["FastAPI", "React", "Qdrant", "Alembic"], "live": False},
    {"lane": 1, "name": "kovidam-AI-Interview", "tag": "INTELLIGENT SYSTEM · KOVIDAM", "color": "#a855f7",
     "icon": "chat",
     "pitch": ["AI interview & candidate evaluation for", "recruiters — Groq-powered, dockerized stack."],
     "stack": ["FastAPI", "Next.js", "Redis", "Groq"], "live": False},
    # ---- lane 03 : ml / tooling / product ----
    {"lane": 2, "name": "RL-model-Negotiation", "tag": "ML SYSTEM · DEALFORGE", "color": "#22c55e", "icon": "rl",
     "pitch": ["Multi-agent RL — a Buyer agent trained with", "GRPO against Seller, Legal & Risk agents."],
     "stack": ["Python", "TRL", "GRPO", "Qwen2.5"], "live": False},
    {"lane": 2, "name": "JKY Terminal", "tag": "DEV TOOLING · DESKTOP", "color": "#f5a623", "icon": "terminal",
     "pitch": ["Local-first AI terminal — shells outlive the", "window; command output becomes live apps."],
     "stack": ["Rust", "Tauri", "React", "xterm.js"], "live": False},
    {"lane": 2, "name": "GitVeda", "tag": "AI PRODUCT · DEV LEARNING", "color": "#ec4899", "icon": "branch",
     "pitch": ["Gamified Git learning — a 30-level campaign", "with a real in-browser Git terminal."],
     "stack": ["React", "Vite", "Firebase"], "live": True},
]


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def smooth_animate(attr, values, dur, keyTimes="0;0.5;1", extra=""):
    """Sine-like ease (spline, not linear) breathing/pulse loop."""
    n = len(values.split(";"))
    splines = ";".join([EASE] * (n - 1))
    return (f'<animate attributeName="{attr}" values="{values}" keyTimes="{keyTimes}" '
            f'calcMode="spline" keySplines="{splines}" dur="{dur}" repeatCount="indefinite"{extra}/>')


def entrance(delay, dur=0.6):
    """One-shot fade-in that freezes visible. The element's own opacity stays 1,
    so a renderer that ignores SMIL still shows it."""
    return (f'<animate attributeName="opacity" values="0;0;1" keyTimes="0;{delay/(delay+dur):.4f};1" '
            f'dur="{delay+dur:.2f}s" fill="freeze" calcMode="spline" keySplines="{EASE};{EASE}"/>')


def cycle_blip(at, width=0.9, peak=0.9, cycle=CYCLE):
    """Opacity blip at `at` seconds into every `cycle`-second loop (border ripple)."""
    a = max(at / cycle, 0.0001)
    b = min((at + width / 2) / cycle, 0.9990)
    c = min((at + width) / cycle, 0.9995)
    return (f'<animate attributeName="opacity" values="0;0;{peak};0;0" '
            f'keyTimes="0;{a:.4f};{b:.4f};{c:.4f};1" dur="{cycle}s" repeatCount="indefinite"/>')


def text_w(s, size, bold=False, mono=False):
    """Rough rendered width — good enough to fit names and size chips."""
    factor = 0.6 if mono else (0.54 if bold else 0.5)
    return len(s) * size * factor


def starfield(w, h, seed=11, n=34):
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        x = rnd.uniform(24, w - 24)
        y = rnd.uniform(40, h - 30)
        r = rnd.uniform(0.5, 1.2)
        base = rnd.uniform(0.12, 0.4)
        dur = rnd.uniform(2.6, 5.5)
        delay = rnd.uniform(0, 3)
        vals = f"{base:.2f};{base*2.4:.2f};{base:.2f}"
        extra = f' begin="{delay:.1f}s"'
        out.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="#8a8a8a" opacity="{base:.2f}">'
            f'{smooth_animate("opacity", vals, f"{dur:.1f}s", extra=extra)}'
            f'</circle>'
        )
    return "".join(out)


# ------------------------------------------------------------------ icons
def icon(kind, cx, cy, c):
    """Small line-art glyph inside a node badge, drawn around (cx, cy)."""
    sw = 'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"'
    if kind == "shield":
        return (f'<path d="M{cx},{cy-8} L{cx+7},{cy-5} L{cx+7},{cy+1} C{cx+7},{cy+5} {cx+4},{cy+8} {cx},{cy+9} '
                f'C{cx-4},{cy+8} {cx-7},{cy+5} {cx-7},{cy+1} L{cx-7},{cy-5} Z" stroke="{c}" {sw}/>'
                f'<polyline points="{cx-3},{cy} {cx-1},{cy+3} {cx+4},{cy-3}" stroke="{c}" {sw}/>')
    if kind == "layers":
        return "".join(
            f'<path d="M{cx-8},{cy+dy} L{cx},{cy+dy-4} L{cx+8},{cy+dy} L{cx},{cy+dy+4} Z" stroke="{c}" {sw}/>'
            for dy in (-5, 0, 5))
    if kind == "flow":
        return (f'<circle cx="{cx-6}" cy="{cy-5}" r="2.4" stroke="{c}" {sw}/>'
                f'<circle cx="{cx+6}" cy="{cy-5}" r="2.4" stroke="{c}" {sw}/>'
                f'<circle cx="{cx}" cy="{cy+6}" r="2.4" stroke="{c}" {sw}/>'
                f'<path d="M{cx-4},{cy-3} L{cx-1.5},{cy+3.5} M{cx+4},{cy-3} L{cx+1.5},{cy+3.5} '
                f'M{cx-3.5},{cy-5} L{cx+3.5},{cy-5}" stroke="{c}" {sw}/>')
    if kind == "graph":
        pts = [(cx - 7, cy - 5), (cx + 6, cy - 7), (cx + 7, cy + 5), (cx - 5, cy + 7), (cx, cy)]
        edges = [(0, 4), (1, 4), (2, 4), (3, 4), (0, 1), (2, 3)]
        out = [f'<line x1="{pts[a][0]}" y1="{pts[a][1]}" x2="{pts[b][0]}" y2="{pts[b][1]}" stroke="{c}" '
               f'stroke-width="1" opacity="0.7"/>' for a, b in edges]
        out += [f'<circle cx="{x}" cy="{y}" r="1.9" fill="{c}"/>' for x, y in pts]
        return "".join(out)
    if kind == "score":
        return (f'<rect x="{cx-7}" y="{cy+1}" width="3.4" height="6" fill="{c}"/>'
                f'<rect x="{cx-1.7}" y="{cy-3}" width="3.4" height="10" fill="{c}"/>'
                f'<rect x="{cx+3.6}" y="{cy-7}" width="3.4" height="14" fill="{c}" opacity="0.6"/>')
    if kind == "chat":
        return (f'<path d="M{cx-8},{cy-6} h16 v10 h-9 l-4,4 v-4 h-3 Z" stroke="{c}" {sw}/>'
                f'<line x1="{cx-4}" y1="{cy-2}" x2="{cx+4}" y2="{cy-2}" stroke="{c}" stroke-width="1.3"/>'
                f'<line x1="{cx-4}" y1="{cy+1}" x2="{cx+1}" y2="{cy+1}" stroke="{c}" stroke-width="1.3"/>')
    if kind == "rl":
        return (f'<path d="M{cx-7},{cy-3} A7,7 0 0 1 {cx+6},{cy-4}" stroke="{c}" {sw}/>'
                f'<polyline points="{cx+3},{cy-7} {cx+6},{cy-4} {cx+2},{cy-2}" stroke="{c}" {sw}/>'
                f'<path d="M{cx+7},{cy+3} A7,7 0 0 1 {cx-6},{cy+4}" stroke="{c}" {sw}/>'
                f'<polyline points="{cx-3},{cy+7} {cx-6},{cy+4} {cx-2},{cy+2}" stroke="{c}" {sw}/>')
    if kind == "terminal":
        return (f'<rect x="{cx-9}" y="{cy-7}" width="18" height="14" rx="2" stroke="{c}" {sw}/>'
                f'<polyline points="{cx-5},{cy-2} {cx-2},{cy+1} {cx-5},{cy+4}" stroke="{c}" {sw}/>'
                f'<line x1="{cx}" y1="{cy+4}" x2="{cx+5}" y2="{cy+4}" stroke="{c}" stroke-width="1.5">'
                f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.5;1" dur="1.1s" '
                f'repeatCount="indefinite"/></line>')
    if kind == "branch":
        return (f'<circle cx="{cx-4}" cy="{cy-6}" r="2.2" stroke="{c}" {sw}/>'
                f'<circle cx="{cx-4}" cy="{cy+6}" r="2.2" stroke="{c}" {sw}/>'
                f'<circle cx="{cx+5}" cy="{cy-3}" r="2.2" stroke="{c}" {sw}/>'
                f'<path d="M{cx-4},{cy-3.8} L{cx-4},{cy+3.8} M{cx+5},{cy-0.8} C{cx+5},{cy+3} {cx-4},{cy+1} {cx-4},{cy+3.8}" '
                f'stroke="{c}" {sw}/>')
    return ""


def badge_motion(i, cx, cy, c):
    """Each badge gets its own ambient ring so no two panels move identically."""
    style = i % 3
    if style == 0:  # rotating dashed ring
        return (f'<g><animateTransform attributeName="transform" type="rotate" from="0 {cx} {cy}" '
                f'to="360 {cx} {cy}" dur="{12 + i}s" repeatCount="indefinite"/>'
                f'<circle cx="{cx}" cy="{cy}" r="22" fill="none" stroke="{c}" stroke-width="1" opacity="0.45" '
                f'stroke-dasharray="3 5"/></g>')
    if style == 1:  # expanding ping
        return (f'<circle cx="{cx}" cy="{cy}" r="18" fill="none" stroke="{c}" stroke-width="1.2" opacity="0.5">'
                f'{smooth_animate("r", "18;27;18", f"{3.0 + i * 0.15:.2f}s")}'
                f'{smooth_animate("opacity", "0.5;0;0.5", f"{3.0 + i * 0.15:.2f}s")}</circle>')
    # counter-rotating arc pair
    return (f'<g><animateTransform attributeName="transform" type="rotate" from="360 {cx} {cy}" '
            f'to="0 {cx} {cy}" dur="{9 + i}s" repeatCount="indefinite"/>'
            f'<path d="M{cx-22},{cy} A22,22 0 0 1 {cx},{cy-22}" fill="none" stroke="{c}" stroke-width="1.2" opacity="0.55"/>'
            f'<path d="M{cx+22},{cy} A22,22 0 0 1 {cx},{cy+22}" fill="none" stroke="{c}" stroke-width="1.2" opacity="0.55"/></g>')


# ------------------------------------------------------------------ pieces
def lane_y(lane_idx):
    return TOP + lane_idx * (LANE_HEAD + PANEL_H + LANE_GAP)


def render_lane(idx, lane, count, delay):
    y = lane_y(idx)
    c = lane["color"]
    label_y = y + 13
    rail_y = y + 24
    label = f'{lane["id"]} // {lane["name"]}'
    rail = f"M{PAD},{rail_y} L{W-PAD},{rail_y}"
    length = W - 2 * PAD
    out = [f'<g>{entrance(delay)}']
    out.append(f'<text x="{PAD}" y="{label_y}" font-family="{MONO}" font-size="10" letter-spacing="1" '
               f'fill="{c}">{esc(label)}</text>')
    out.append(f'<text x="{W-PAD}" y="{label_y}" text-anchor="end" font-family="{MONO}" font-size="9" '
               f'letter-spacing="1" fill="#555">{count} SYSTEMS</text>')
    # rail draws itself in once, then carries two traveling pulses forever
    out.append(f'<path d="{rail}" stroke="url(#rail{idx})" stroke-width="1" fill="none" '
               f'stroke-dasharray="{length:.0f}" stroke-dashoffset="0">'
               f'<animate attributeName="stroke-dashoffset" values="{length:.0f};{length:.0f};0" '
               f'keyTimes="0;{delay/(delay+1.0):.3f};1" dur="{delay+1.0:.2f}s" fill="freeze"/></path>')
    for k in range(2):
        dur = 5.5 + idx * 0.7
        begin = -(dur * k / 2) + idx * 0.4
        out.append(f'<circle r="2.4" fill="{c}" filter="url(#glow)">'
                   f'<animateMotion dur="{dur:.1f}s" begin="{begin:.1f}s" repeatCount="indefinite" path="{rail}"/>'
                   f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.1;0.9;1" '
                   f'dur="{dur:.1f}s" begin="{begin:.1f}s" repeatCount="indefinite"/></circle>')
    out.append('</g>')
    return "".join(out)


def render_panel(i, sysd, col, delay, ripple_at):
    lane = sysd["lane"]
    x = PAD + col * (PANEL_W + GAP)
    y = lane_y(lane) + LANE_HEAD
    c = sysd["color"]
    rail_y = lane_y(lane) + 24
    mid = x + PANEL_W / 2
    out = [f'<g>{entrance(delay)}']

    # tap from the lane rail down into the panel
    out.append(f'<line x1="{mid:.1f}" y1="{rail_y}" x2="{mid:.1f}" y2="{y}" stroke="{c}" stroke-width="1" opacity="0.3"/>')
    out.append(f'<circle cx="{mid:.1f}" cy="{rail_y}" r="2" fill="{c}" opacity="0.8"/>')

    # glass body + left accent bar (same card language as the journey timeline)
    out.append(f'<rect x="{x:.1f}" y="{y}" width="{PANEL_W:.1f}" height="{PANEL_H}" rx="10" fill="#101014" stroke="#1f1f24"/>')
    out.append(f'<rect x="{x:.1f}" y="{y}" width="{PANEL_W:.1f}" height="{PANEL_H}" rx="10" fill="url(#panelSheen)"/>')
    out.append(f'<rect x="{x+1:.1f}" y="{y+8}" width="3" height="{PANEL_H-16}" rx="1.5" fill="{c}"/>')
    # border ripple — replays once per CYCLE, panel by panel
    out.append(f'<rect x="{x:.1f}" y="{y}" width="{PANEL_W:.1f}" height="{PANEL_H}" rx="10" fill="none" '
               f'stroke="{c}" stroke-width="1.2" opacity="0" filter="url(#glowSoft)">{cycle_blip(ripple_at)}</rect>')

    # id + status pill
    out.append(f'<text x="{x+16:.1f}" y="{y+20}" font-family="{MONO}" font-size="9" letter-spacing="1" '
               f'fill="#555">N.{i+1:02d}</text>')
    if sysd["live"]:
        pw, ptxt, pcol = 54, "LIVE", "#22c55e"
    else:
        pw, ptxt, pcol = 64, "SOURCE", "#6b7280"
    px = x + PANEL_W - 12 - pw
    out.append(f'<rect x="{px:.1f}" y="{y+9}" width="{pw}" height="17" rx="8.5" fill="#0d0d10" stroke="{pcol}" opacity="0.85"/>')
    dot_anim = smooth_animate("opacity", "1;0.25;1", "1.6s") if sysd["live"] else ""
    out.append(f'<circle cx="{px+11:.1f}" cy="{y+17.5}" r="2.3" fill="{pcol}">{dot_anim}</circle>')
    out.append(f'<text x="{px+19:.1f}" y="{y+21}" font-family="{MONO}" font-size="8.5" letter-spacing="1" '
               f'fill="{pcol}">{ptxt}</text>')

    # icon badge
    bx, by = x + 36, y + 56
    out.append(f'<circle cx="{bx:.1f}" cy="{by}" r="22" fill="{c}" opacity="0.16" filter="url(#softBlur)"/>')
    out.append(badge_motion(i, round(bx, 1), by, c))
    out.append(f'<circle cx="{bx:.1f}" cy="{by}" r="17" fill="#0b0b0d" stroke="{c}" stroke-width="1.7"/>')
    out.append(icon(sysd["icon"], round(bx, 1), by, c))

    # name (auto-fit) + tag
    nx = x + 68
    max_w = x + PANEL_W - 14 - nx
    size = 14.5
    while size > 11.5 and text_w(sysd["name"], size, bold=True) > max_w:
        size -= 0.5
    out.append(f'<text x="{nx:.1f}" y="{y+54}" font-family="{SANS}" font-size="{size}" font-weight="700" '
               f'fill="#f2f2f2">{esc(sysd["name"])}</text>')
    out.append(f'<text x="{nx:.1f}" y="{y+71}" font-family="{MONO}" font-size="8.5" letter-spacing="0.8" '
               f'fill="{c}">{esc(sysd["tag"])}</text>')

    # divider + pitch
    out.append(f'<line x1="{x+16:.1f}" y1="{y+88}" x2="{x+PANEL_W-16:.1f}" y2="{y+88}" stroke="#1c1c22"/>')
    for k, line in enumerate(sysd["pitch"]):
        out.append(f'<text x="{x+16:.1f}" y="{y+106+k*16}" font-family="{SANS}" font-size="11" '
                   f'fill="#9a9a9a">{esc(line)}</text>')

    # stack chips
    cx_ = x + 16
    cy_ = y + PANEL_H - 27
    for chip in sysd["stack"]:
        cw = text_w(chip, 9, mono=True) + 16
        out.append(f'<rect x="{cx_:.1f}" y="{cy_}" width="{cw:.1f}" height="15" rx="4" fill="#0d0d10" stroke="#26262e"/>')
        out.append(f'<circle cx="{cx_+6:.1f}" cy="{cy_+7.5}" r="1.6" fill="{c}" opacity="0.8"/>')
        out.append(f'<text x="{cx_+10:.1f}" y="{cy_+11}" font-family="{MONO}" font-size="9" fill="#b8b8b8">{esc(chip)}</text>')
        cx_ += cw + 6

    out.append('</g>')
    return "".join(out)


def build_svg():
    n_lanes = len(LANES)
    body_bottom = lane_y(n_lanes - 1) + LANE_HEAD + PANEL_H
    H = body_bottom + 62
    live = sum(1 for s in SYSTEMS if s["live"])

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" '
                 f'role="img" aria-labelledby="constTitle constDesc">')
    parts.append('<title id="constTitle">Flagship Systems</title>')
    desc = "; ".join(f'{s["name"]} ({s["tag"].title()}: {" ".join(s["pitch"])} Stack: {", ".join(s["stack"])})'
                     for s in SYSTEMS)
    parts.append(f'<desc id="constDesc">{len(SYSTEMS)} flagship systems in {n_lanes} lanes — {esc(desc)}</desc>')

    parts.append('''<defs>
    <pattern id="dotgrid" width="28" height="28" patternUnits="userSpaceOnUse">
      <circle cx="1" cy="1" r="1" fill="#161616"/>
    </pattern>
    <filter id="glow" x="-250%" y="-250%" width="600%" height="600%"><feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="glowSoft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="1.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="softBlur" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="4"/></filter>
    <linearGradient id="panelSheen" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.035"/><stop offset="45%" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="scanGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#22d3ee" stop-opacity="0"/><stop offset="50%" stop-color="#22d3ee" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="#22d3ee" stop-opacity="0"/>
    </linearGradient>
{rail_grads}
    <linearGradient id="footGrad" gradientUnits="userSpaceOnUse" x1="{PAD}" y1="0" x2="{W-PAD}" y2="0">
      <stop offset="0%" stop-color="#22d3ee"/><stop offset="50%" stop-color="#a855f7"/><stop offset="100%" stop-color="#f5a623"/>
    </linearGradient>
  </defs>'''.replace("{PAD}", str(PAD)).replace("{W-PAD}", str(W - PAD)).replace("{rail_grads}", "".join(
        f'<linearGradient id="rail{i}" gradientUnits="userSpaceOnUse" x1="{PAD}" y1="0" x2="{W-PAD}" y2="0">'
        f'<stop offset="0%" stop-color="{ln["color"]}" stop-opacity="0.55"/>'
        f'<stop offset="100%" stop-color="{ln["color"]}" stop-opacity="0.08"/></linearGradient>'
        for i, ln in enumerate(LANES))))

    parts.append(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="14" fill="#0a0a0a" stroke="#1f1f1f"/>')
    parts.append(f'<rect x="14" y="14" width="{W-28}" height="{H-28}" fill="url(#dotgrid)"/>')
    parts.append(starfield(W, H))

    # scanline sweep — replays at the start of every CYCLE-second loop
    t_start, t_end = 0.15 / CYCLE, 1.6 / CYCLE
    parts.append(
        f'<rect x="14" y="14" width="{W-28}" height="6" fill="url(#scanGrad)" opacity="0">'
        f'<animateTransform attributeName="transform" type="translate" values="0,0;0,0;0,{H-40};0,{H-40}" '
        f'keyTimes="0;{t_start:.4f};{t_end:.4f};1" calcMode="spline" keySplines="{EASE};{EASE};{EASE}" '
        f'dur="{CYCLE}s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="0;1;1;0;0" keyTimes="0;{t_start:.4f};{t_start+0.08:.4f};{t_end:.4f};1" '
        f'dur="{CYCLE}s" repeatCount="indefinite"/></rect>'
    )

    # header
    parts.append(f'<g>{entrance(0.1)}')
    parts.append(f'<text x="{PAD}" y="30" font-family="{MONO}" font-size="10" letter-spacing="1" fill="#555">FLAGSHIP // 06</text>')
    parts.append(f'<circle cx="{PAD + 104}" cy="26.5" r="2.5" fill="#22c55e" filter="url(#glow)">'
                 f'{smooth_animate("opacity", "1;0.35;1", "1.8s")}</circle>')
    parts.append(f'<text x="{W-PAD}" y="30" text-anchor="end" font-family="{MONO}" font-size="10" letter-spacing="1" '
                 f'fill="#555">SYSTEM · CATEGORY · STACK · STATUS</text>')
    parts.append(f'<rect x="{PAD}" y="40" width="{W-2*PAD}" height="22" rx="6" fill="#101014" stroke="#242430"/>')
    parts.append(f'<text x="{PAD+12}" y="55" font-family="{MONO}" font-size="11" fill="#666">&gt;</text>')
    parts.append(f'<text x="{PAD+26}" y="55" font-family="{MONO}" font-size="11" fill="#c9c9c9">'
                 f'{len(SYSTEMS)} systems · {n_lanes} lanes · <tspan fill="#22c55e">{live} live</tspan> · '
                 f'<tspan fill="#22d3ee">agentic</tspan> → <tspan fill="#a855f7">intelligent</tspan> → '
                 f'<tspan fill="#f5a623">shipped</tspan></text>')
    parts.append('</g>')

    # lanes + panels
    per_lane = {}
    for s in SYSTEMS:
        per_lane.setdefault(s["lane"], []).append(s)
    order = 0
    for li, lane in enumerate(LANES):
        parts.append(render_lane(li, lane, len(per_lane.get(li, [])), delay=0.25 + li * 0.35))
    for li in range(n_lanes):
        for col, s in enumerate(per_lane.get(li, [])):
            idx = SYSTEMS.index(s)
            parts.append(render_panel(idx, s, col, delay=0.45 + order * 0.12, ripple_at=1.9 + order * 0.55))
            order += 1

    # footer: legend + pointer to the atlas
    fy = body_bottom + 24
    parts.append(f'<g>{entrance(1.8)}')
    parts.append(f'<line x1="{PAD}" y1="{fy}" x2="{W-PAD}" y2="{fy}" stroke="url(#footGrad)" stroke-width="1" opacity="0.35"/>')
    parts.append(f'<circle r="2.2" fill="#ffffff" filter="url(#glowSoft)">'
                 f'<animateMotion dur="7s" repeatCount="indefinite" path="M{PAD},{fy} L{W-PAD},{fy}"/></circle>')
    parts.append(f'<circle cx="{PAD+6}" cy="{fy+20}" r="2.6" fill="#22c55e"/>'
                 f'<text x="{PAD+14}" y="{fy+23.5}" font-family="{MONO}" font-size="9" letter-spacing="1" fill="#777">LIVE DEMO</text>'
                 f'<circle cx="{PAD+92}" cy="{fy+20}" r="2.6" fill="#6b7280"/>'
                 f'<text x="{PAD+100}" y="{fy+23.5}" font-family="{MONO}" font-size="9" letter-spacing="1" fill="#777">SOURCE</text>')
    parts.append(f'<text x="{W-PAD}" y="{fy+23.5}" text-anchor="end" font-family="{MONO}" font-size="9" letter-spacing="1" '
                 f'fill="#666">FLAGSHIPS ONLY — FULL MAP IN 04 ENGINEERING ATLAS</text>')
    parts.append('</g>')

    parts.append('</svg>')
    return "\n".join(parts)


def main():
    try:
        svg = build_svg()
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: constellation generation failed, leaving existing file untouched: {e}", file=sys.stderr)
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
