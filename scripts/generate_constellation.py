#!/usr/bin/env python3
"""Generate assets/project-constellation.svg — the section 06 "Flagship
Systems" topology: six systems arranged in the same sequence as before,
connected by curved traces carrying traveling energy pulses.

Honesty note (see also generate_atlas.py): SVG has no real 3D, hover, or
JavaScript, and GitHub strips both <script> and any inline <style> from
rendered README markdown — this holds whether the SVG is embedded via <img>
or written inline, so there is no way to express :hover or cursor-tracking
here. "Alive" comes entirely from continuous ambient SMIL animation (glow,
orbiting particles, traveling pulses, rotating rings) rather than any
pointer interaction. Panel text itself never moves — only glow/particles/
rings animate around it — matching the fix already applied to the
Engineering Atlas asset (stop text bobbing, sine easing). The whole scene
dematerializes and replays its staggered entrance every CYCLE (10s) via
cycle_reveal(), the same helper generate_atlas.py uses. Every animated
element is fully self-contained (own path/values, no <use>/<mpath> href
indirection), because GitHub's image proxy strips internal href/xlink:href
fragment references.

Content is curated, not fetched: the six systems below are the same real,
public repositories the previous static version of this diagram listed —
no invented systems, no fabricated stats. There is no live-data workflow
for this asset (same as engineering-atlas.svg / hero-banner.svg).

Never-fail contract: this script always exits 0. Any problem is logged
to stderr and the script leaves the existing output file untouched.
"""
import os
import random
import sys

OUT_PATH = os.environ.get("OUT_PATH", "assets/project-constellation.svg")

W = 1150
H = 460
CYCLE = 10.0  # whole scene fades out and re-materializes every CYCLE seconds
EASE = "0.42 0 0.58 1"

COLORS = {
    "cyan": "#22d3ee",
    "purple": "#a855f7",
    "amber": "#f5a623",
}

NODES = [
    {
        "id": "N.01", "name": "multi-layer_orchestation", "category": "AGENTIC SYSTEM",
        "tech": "Next.js · Fastify · Kafka", "cx": 200, "cy": 140, "color": COLORS["cyan"],
        "motif": "float",
    },
    {
        "id": "N.02", "name": "agent--flow", "category": "AGENTIC SYSTEM",
        "tech": "Next.js · FastAPI · Postgres", "cx": 575, "cy": 140, "color": COLORS["cyan"],
        "motif": "orbit",
    },
    {
        "id": "N.03", "name": "Kovidam-Skill-Graph", "category": "INTELLIGENT SYSTEM",
        "tech": "FastAPI · React · Qdrant", "cx": 950, "cy": 140, "color": COLORS["purple"],
        "motif": "pulse",
    },
    {
        "id": "N.04", "name": "kovidam-AI-Interview", "category": "INTELLIGENT SYSTEM",
        "tech": "FastAPI · Next.js · Groq", "cx": 950, "cy": 320, "color": COLORS["purple"],
        "motif": "scan",
    },
    {
        "id": "N.05", "name": "RL-model-Negotiation", "category": "INTELLIGENT SYSTEM",
        "tech": "Python · GRPO / TRL", "cx": 575, "cy": 320, "color": COLORS["purple"],
        "motif": "ring",
    },
    {
        "id": "N.06", "name": "GitVeda", "category": "PRODUCT",
        "tech": "React · Vite · Firebase", "cx": 200, "cy": 320, "color": COLORS["amber"],
        "motif": "diamond",
    },
]

# sequential connections, same order as the original diagram
LINKS = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def smooth_animate(attr, values, dur, keyTimes="0;0.5;1", extra=""):
    """Sine-like ease (spline, not linear) breathing/pulse loop."""
    n = len(values.split(";"))
    splines = ";".join([EASE] * (n - 1))
    return (f'<animate attributeName="{attr}" values="{values}" keyTimes="{keyTimes}" '
            f'calcMode="spline" keySplines="{splines}" dur="{dur}" repeatCount="indefinite"{extra}/>')


def cycle_reveal(appear_start, appear_end, fade_out_dur=0.6, cycle=CYCLE):
    """Opacity animate for a group that materializes at [appear_start, appear_end]
    seconds into a `cycle`-second loop, holds visible, then dematerializes just
    before the loop repeats — the whole scene re-opens every `cycle` seconds."""
    a0, a1 = appear_start / cycle, appear_end / cycle
    b0 = (cycle - fade_out_dur) / cycle
    splines = ";".join([EASE] * 4)
    return (f'<animate attributeName="opacity" values="0;0;1;1;0" '
            f'keyTimes="0;{a0:.4f};{a1:.4f};{b0:.4f};1" calcMode="spline" keySplines="{splines}" '
            f'dur="{cycle}s" repeatCount="indefinite"/>')


def starfield(w, h, seed=11, n=40):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        x = rnd.uniform(24, w - 24)
        y = rnd.uniform(40, h - 30)
        r = rnd.uniform(0.5, 1.3)
        base = rnd.uniform(0.15, 0.5)
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


def curve_path(x1, y1, x2, y2, bow):
    """Quadratic-bezier trace between two node centers with a gentle sag/bow,
    for a fiber-optic-channel feel instead of a bare straight line."""
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    if y1 == y2:  # horizontal segment — bow vertically
        cx_, cy_ = mx, my + bow
    else:  # vertical segment — bow horizontally
        cx_, cy_ = mx + bow, my
    return f"M{x1:.1f},{y1:.1f} Q{cx_:.1f},{cy_:.1f} {x2:.1f},{y2:.1f}"


def render_connector(path, color, delay):
    return (
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1" opacity="0.22"/>'
        f'<circle r="2.4" fill="{color}" filter="url(#glow)">'
        f'<animateMotion dur="3.4s" begin="{delay:.1f}s" repeatCount="indefinite" path="{path}" '
        f'keyPoints="0;1;1;0;0" keyTimes="0;0.46;0.54;0.98;1" calcMode="linear"/>'
        f'<animate attributeName="opacity" values="0;1;1;1;0" keyTimes="0;0.08;0.5;0.92;1" '
        f'dur="3.4s" begin="{delay:.1f}s" repeatCount="indefinite"/>'
        f'</circle>'
    )


def render_motif(motif, cx, cy, color):
    """Each node's own idle animation — never identical across nodes.
    Only the marker/halo moves; the text labels stay put and only pulse."""
    if motif == "float":
        return (
            f'<g><animateTransform attributeName="transform" type="translate" '
            f'values="0,0;0,-4;0,0" calcMode="spline" keySplines="{EASE};{EASE}" '
            f'keyTimes="0;0.5;1" dur="6s" repeatCount="indefinite"/>'
            f'<circle cx="{cx}" cy="{cy}" r="10" fill="#141414" stroke="{color}" stroke-width="1.5"/>'
            f'<circle cx="{cx}" cy="{cy}" r="3" fill="{color}" filter="url(#glow)"/>'
            f'</g>'
        )
    if motif == "orbit":
        epath = ellipse_path(cx, cy, 22, 8)
        return (
            f'<circle cx="{cx}" cy="{cy}" r="10" fill="#141414" stroke="{color}" stroke-width="1.5"/>'
            f'<circle cx="{cx}" cy="{cy}" r="3" fill="{color}" filter="url(#glow)"/>'
            f'<g><animateTransform attributeName="transform" type="rotate" '
            f'from="0 {cx} {cy}" to="360 {cx} {cy}" dur="14s" repeatCount="indefinite"/>'
            f'<ellipse cx="{cx}" cy="{cy}" rx="22" ry="8" fill="none" stroke="{color}" '
            f'stroke-width="1" opacity="0.35" stroke-dasharray="2 4"/></g>'
            f'<circle r="1.8" fill="{color}" filter="url(#glowSoft)">'
            f'<animateMotion dur="7s" repeatCount="indefinite" path="{epath}"/></circle>'
        )
    if motif == "pulse":
        return (
            f'<circle cx="{cx}" cy="{cy}" r="16" fill="none" stroke="{color}" stroke-width="1.2" opacity="0.5">'
            f'{smooth_animate("r", "16;30;16", "3.2s")}{smooth_animate("opacity", "0.5;0;0.5", "3.2s")}</circle>'
            f'<circle cx="{cx}" cy="{cy}" r="10" fill="#141414" stroke="{color}" stroke-width="1.5"/>'
            f'<circle cx="{cx}" cy="{cy}" r="3" fill="{color}" filter="url(#glow)">'
            f'{smooth_animate("opacity", "1;0.4;1", "1.6s")}</circle>'
        )
    if motif == "scan":
        return (
            f'<circle cx="{cx}" cy="{cy}" r="10" fill="#141414" stroke="{color}" stroke-width="1.5"/>'
            f'<circle cx="{cx}" cy="{cy}" r="3" fill="{color}" filter="url(#glow)"/>'
            f'<rect x="{cx-11}" y="{cy-11}" width="22" height="3" fill="url(#scanGrad)" opacity="0.9">'
            f'<animateTransform attributeName="transform" type="translate" '
            f'values="0,0;0,19;0,0" calcMode="spline" keySplines="{EASE};{EASE}" '
            f'keyTimes="0;0.5;1" dur="4s" repeatCount="indefinite"/></rect>'
        )
    if motif == "ring":
        return (
            f'<circle cx="{cx}" cy="{cy}" r="10" fill="#141414" stroke="{color}" stroke-width="1.5"/>'
            f'<circle cx="{cx}" cy="{cy}" r="3" fill="{color}" filter="url(#glow)"/>'
            f'<g><animateTransform attributeName="transform" type="rotate" '
            f'from="0 {cx} {cy}" to="360 {cx} {cy}" dur="11s" repeatCount="indefinite"/>'
            f'<circle cx="{cx}" cy="{cy}" r="17" fill="none" stroke="{color}" stroke-width="1" '
            f'opacity="0.4" stroke-dasharray="3 5"/></g>'
        )
    if motif == "diamond":
        return (
            f'<circle cx="{cx}" cy="{cy}" r="10" fill="#141414" stroke="{color}" stroke-width="1.5"/>'
            f'<circle cx="{cx}" cy="{cy}" r="3" fill="{color}" filter="url(#glow)"/>'
            f'<g><animateTransform attributeName="transform" type="rotate" '
            f'from="0 {cx} {cy}" to="360 {cx} {cy}" dur="18s" repeatCount="indefinite"/>'
            f'<rect x="{cx-13}" y="{cy-13}" width="26" height="26" fill="none" stroke="{color}" '
            f'stroke-width="1" opacity="0.3" transform="rotate(45 {cx} {cy})"/></g>'
        )
    return ""


def corner_ticks(cx, cy, color, half_w=76, top=-58, bottom=64):
    """Small HUD-style bracket accents framing a node's label block — a cheap
    stand-in for a glass panel that doesn't require boxing the whole node."""
    x0, x1 = cx - half_w, cx + half_w
    y0, y1 = cy + top, cy + bottom
    ln = 8
    segs = [
        (x0, y0, x0 + ln, y0), (x0, y0, x0, y0 + ln),
        (x1, y0, x1 - ln, y0), (x1, y0, x1, y0 + ln),
        (x0, y1, x0 + ln, y1), (x0, y1, x0, y1 - ln),
        (x1, y1, x1 - ln, y1), (x1, y1, x1, y1 - ln),
    ]
    out = []
    for sx, sy, ex, ey in segs:
        out.append(f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
                    f'stroke="{color}" stroke-width="1" opacity="0.25"/>')
    return "".join(out)


def render_node(node, appear_start, appear_end):
    cx, cy, color = node["cx"], node["cy"], node["color"]
    parts = [f'<g opacity="0">{cycle_reveal(appear_start, appear_end)}']
    parts.append(corner_ticks(cx, cy, color))
    parts.append(f'<text x="{cx}" y="{cy-42}" text-anchor="middle" font-family="Consolas, \'SF Mono\', monospace" '
                 f'font-size="10" fill="#666">{node["id"]}</text>')
    parts.append(render_motif(node["motif"], cx, cy, color))
    parts.append(f'<text x="{cx}" y="{cy+28}" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" '
                 f'font-size="13" font-weight="700" fill="#eaeaea">{esc(node["name"])}</text>')
    parts.append(f'<text x="{cx}" y="{cy+46}" text-anchor="middle" font-family="Consolas, monospace" '
                 f'font-size="9.5" letter-spacing="1" fill="{color}">{esc(node["category"])}</text>')
    parts.append(f'<text x="{cx}" y="{cy+62}" text-anchor="middle" font-family="Consolas, monospace" '
                 f'font-size="10" fill="#8a8a8a">{esc(node["tech"])}</text>')
    parts.append('</g>')
    return "".join(parts)


def build_svg():
    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" '
                 f'role="img" aria-labelledby="constTitle constDesc">')
    parts.append('<title id="constTitle">Project Constellation</title>')
    parts.append('<desc id="constDesc">Six flagship systems connected in sequence: '
                 'multi-layer_orchestation, agent--flow, Kovidam-Skill-Graph, kovidam-AI-Interview, '
                 'RL-model-Negotiation, and GitVeda, each labeled with category and primary technology.</desc>')

    parts.append('''<defs>
    <pattern id="dotgrid" width="28" height="28" patternUnits="userSpaceOnUse">
      <circle cx="1" cy="1" r="1" fill="#161616"/>
    </pattern>
    <filter id="glow" x="-250%" y="-250%" width="600%" height="600%"><feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="glowSoft" x="-250%" y="-250%" width="600%" height="600%"><feGaussianBlur stdDeviation="1.3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <linearGradient id="scanGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#22d3ee" stop-opacity="0"/><stop offset="50%" stop-color="#22d3ee" stop-opacity="0.6"/>
      <stop offset="100%" stop-color="#22d3ee" stop-opacity="0"/>
    </linearGradient>
  </defs>''')

    parts.append(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="14" fill="#0a0a0a" stroke="#1f1f1f"/>')

    bg = ['<g opacity="0">', cycle_reveal(0, 0.5)]
    bg.append(f'<rect x="14" y="14" width="{W-28}" height="{H-28}" fill="url(#dotgrid)"/>')
    bg.append(starfield(W, H))
    bg.append('</g>')
    parts.append("".join(bg))

    # scanline sweep — replays at the start of every CYCLE-second loop
    sweep_end_t = 0.15 + 1.1
    t_sweep = sweep_end_t / CYCLE
    t_start = 0.15 / CYCLE
    parts.append(
        f'<rect x="14" y="14" width="{W-28}" height="6" fill="url(#scanGrad)">'
        f'<animateTransform attributeName="transform" type="translate" '
        f'values="0,0;0,0;0,{H-40};0,{H-40}" '
        f'keyTimes="0;{t_start:.4f};{t_sweep:.4f};1" calcMode="spline" '
        f'keySplines="{EASE};{EASE};{EASE}" dur="{CYCLE}s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="0;1;1;0;0" '
        f'keyTimes="0;{t_start:.4f};{(t_start+0.08):.4f};{t_sweep:.4f};1" calcMode="spline" '
        f'keySplines="{EASE};{EASE};{EASE};{EASE}" dur="{CYCLE}s" repeatCount="indefinite"/></rect>'
    )

    # header
    header = ['<g opacity="0">', cycle_reveal(0.1, 0.4)]
    header.append('<text x="20" y="26" font-family="Consolas, \'SF Mono\', monospace" font-size="10" '
                   'fill="#555">ATLAS // 02</text>')
    header.append(f'<circle cx="98" cy="22.5" r="2.5" fill="#22c55e" filter="url(#glow)">'
                  f'{smooth_animate("opacity", "1;0.35;1", "1.8s")}</circle>')
    header.append(f'<text x="{W-20}" y="26" text-anchor="end" font-family="Consolas, \'SF Mono\', monospace" '
                  f'font-size="10" fill="#555">SYSTEM · CATEGORY · STACK</text>')
    header.append('</g>')
    parts.append("".join(header))

    # connectors, staggered right after both endpoint nodes have appeared
    stagger = 0.15
    node_appear = [0.55 + i * stagger for i in range(len(NODES))]
    for i, (a, b) in enumerate(LINKS):
        n1, n2 = NODES[a], NODES[b]
        path = curve_path(n1["cx"], n1["cy"], n2["cx"], n2["cy"], bow=14)
        start = max(node_appear[a], node_appear[b]) + 0.25
        seg = [f'<g opacity="0">', cycle_reveal(start, start + 0.3)]
        seg.append(render_connector(path, n1["color"], delay=1.2 + i * 0.35))
        seg.append('</g>')
        parts.append("".join(seg))

    # nodes
    for i, node in enumerate(NODES):
        parts.append(render_node(node, node_appear[i], node_appear[i] + 0.4))

    footer = ['<g opacity="0">', cycle_reveal(2.0, 2.4)]
    footer.append(f'<text x="{W/2:.0f}" y="{H-24}" text-anchor="middle" font-family="Consolas, \'SF Mono\', monospace" '
                  f'font-size="10" fill="#666">Flagship systems only — full map in the Engineering Atlas.</text>')
    footer.append('</g>')
    parts.append("".join(footer))

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
