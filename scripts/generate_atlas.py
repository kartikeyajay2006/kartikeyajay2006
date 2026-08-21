#!/usr/bin/env python3
"""Generate assets/engineering-atlas.svg — the section 04 "Engineering Atlas":
a holographic core (identity nameplate) orbited by rings, radiating animated
energy connections out to four floating domain modules.

Honesty note (see also generate_identity.py / generate_neon.py): SVG has no
real 3D, hover, or JavaScript, and GitHub strips both <script> and any inline
<style> from rendered README markdown — this holds whether the SVG is
embedded via <img> or written inline, so there is no way to express
:hover here. "Alive" comes entirely from continuous ambient SMIL animation
(orbiting particles, pulsing core, traveling energy dots) rather than any
pointer interaction. Panel text itself never moves — only glow/particles
animate, so labels stay readable. Pulses/glows ease with calcMode="spline"
(sine-like acceleration) rather than linear ping-pong. The whole scene
dematerializes and replays its staggered entrance every CYCLE (10s) via
cycle_reveal(), an infinite version of the one-shot reveal identity-core
uses. Every animated element is fully self-contained (own path/values, no
<use>/<mpath> href indirection), because GitHub's image proxy strips
internal href/xlink:href fragment references.

Content is curated, not fetched: the domains/systems below are the same
real, public repositories the previous version of this diagram listed —
no invented systems, no fabricated stats. There is no live-data workflow
for this asset (same as project-constellation.svg / hero-banner.svg).

Never-fail contract: this script always exits 0. Any problem is logged
to stderr and the script leaves the existing output file untouched.
"""
import os
import random
import sys

OUT_PATH = os.environ.get("OUT_PATH", "assets/engineering-atlas.svg")

W = 1150

CORE = {
    "name": "KARTIKEYA",
    "tagline": "AI/ML ENGINEER · FOUNDER · SYSTEM BUILDER",
    "cx": 575, "cy": 108,
}

DOMAINS = [
    {
        "id": "A1", "cx": 160, "name": "AGENTIC SYSTEMS", "color": "#22d3ee",
        "items": ["multi-layer_orchestation", "agent--flow"],
        "muted": False,
    },
    {
        "id": "A2", "cx": 420, "name": "INTELLIGENT SYSTEMS", "color": "#a855f7",
        "items": [
            "Kovidam-Skill-Graph", "kovidam-AI-Interview", "RL-model-Negotiation",
            "AI-Video-Editor", "Financial-Health-Score", "ai-image-classifier",
        ],
        "muted": False,
    },
    {
        "id": "A3", "cx": 680, "name": "PRODUCTS", "color": "#f5a623",
        "items": ["GitVeda", "blood-group-donor"],
        "muted": False,
    },
    {
        "id": "A4", "cx": 940, "name": "WEB3 · EXPERIMENTAL", "color": "#6b7280",
        "items": ["Cardano-BlockPhantom"],
        "muted": True,
    },
]

PANEL_W = 210
RAIL_Y = 205
PANEL_TOP = 224
CYCLE = 10.0  # whole scene fades out and re-materializes every CYCLE seconds
EASE = "0.42 0 0.58 1"


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


def panel_height(n_items):
    return 34 + n_items * 24 + 20


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


def starfield(h, seed=7, n=46):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        x = rnd.uniform(24, W - 24)
        y = rnd.uniform(40, h - 30)
        r = rnd.uniform(0.5, 1.3)
        base = rnd.uniform(0.15, 0.5)
        dur = rnd.uniform(2.6, 5.5)
        delay = rnd.uniform(0, 3)
        extra = f' begin="{delay:.1f}s"'
        vals = f"{base:.2f};{base*2.4:.2f};{base:.2f}"
        out.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="#8a8a8a" opacity="{base:.2f}">'
            f'{smooth_animate("opacity", vals, f"{dur:.1f}s", extra=extra)}'
            f'</circle>'
        )
    return "".join(out)


def render_orbit_ring(cx, cy, rx, ry, color, dur, reverse, n_particles=2):
    frm, to = ("360", "0") if reverse else ("0", "360")
    epath = ellipse_path(cx, cy, rx, ry)
    out = [
        f'<g>'
        f'<animateTransform attributeName="transform" type="rotate" '
        f'from="{frm} {cx} {cy}" to="{to} {cx} {cy}" dur="{dur*6:.0f}s" repeatCount="indefinite"/>'
        f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="none" stroke="{color}" '
        f'stroke-width="1" opacity="0.3" stroke-dasharray="2 5"/>'
        f'</g>'
    ]
    for p in range(n_particles):
        begin = -(dur * p / n_particles)
        out.append(
            f'<circle r="2.1" fill="{color}" filter="url(#glowSoft)">'
            f'<animateMotion dur="{dur}s" begin="{begin:.1f}s" repeatCount="indefinite" path="{epath}"/>'
            f'</circle>'
        )
    return "".join(out)


def render_connector(x0, y0, x1, y1, x2, y2, color, delay):
    path = f"M{x0:.1f},{y0:.1f} L{x0:.1f},{y1:.1f} L{x2:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}"
    out = [
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1" opacity="0.28"/>',
        f'<circle r="2.6" fill="{color}" filter="url(#glow)">'
        f'<animateMotion dur="3.6s" begin="{delay:.1f}s" repeatCount="indefinite" path="{path}" '
        f'keyPoints="0;1;1;0;0" keyTimes="0;0.46;0.54;0.98;1" calcMode="linear"/>'
        f'<animate attributeName="opacity" values="0;1;1;1;0" keyTimes="0;0.08;0.5;0.92;1" '
        f'dur="3.6s" begin="{delay:.1f}s" repeatCount="indefinite"/>'
        f'</circle>',
    ]
    return "".join(out)


def render_domain(domain, appear_start, appear_end, pulse_dur):
    cx = domain["cx"]
    color = domain["color"]
    items = domain["items"]
    h = panel_height(len(items))
    x = cx - PANEL_W / 2
    y = PANEL_TOP
    stroke_w = "1" if domain["muted"] else "1.2"
    dash = ' stroke-dasharray="4 3"' if domain["muted"] else ""
    title_size = "11.5" if domain["muted"] else "12"

    parts = [f'<g opacity="0">{cycle_reveal(appear_start, appear_end)}']

    # vertical stem from rail down to panel
    parts.append(f'<line x1="{cx}" y1="{RAIL_Y}" x2="{cx}" y2="{y}" stroke="#3a3a3a" stroke-width="1"/>')
    parts.append(f'<text x="{x-6:.1f}" y="{RAIL_Y+16}" font-family="Consolas, monospace" font-size="9" '
                 f'fill="#4a4a4a">{domain["id"]}</text>')

    # glass panel body (static — text does not move, only glow/particles animate)
    parts.append(f'<rect x="{x:.1f}" y="{y}" width="{PANEL_W}" height="{h}" rx="8" '
                 f'fill="#101014" opacity="0.9"/>')
    parts.append(f'<rect x="{x:.1f}" y="{y}" width="{PANEL_W}" height="{h}" rx="8" fill="none" '
                 f'stroke="{color}" stroke-width="{stroke_w}"{dash} filter="url(#glowSoft)"/>')
    parts.append(f'<rect x="{x:.1f}" y="{y}" width="{PANEL_W}" height="30" rx="8" fill="{color}" opacity="0.08"/>')

    # corner pulse indicator
    parts.append(f'<circle cx="{x+PANEL_W-12:.1f}" cy="{y+12}" r="2.2" fill="{color}" filter="url(#glow)">'
                 f'{smooth_animate("opacity", "1;0.25;1", f"{pulse_dur:.2f}s")}</circle>')

    parts.append(f'<text x="{cx}" y="{y+21}" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" '
                 f'font-size="{title_size}" font-weight="600" letter-spacing="1" fill="{color}">{esc(domain["name"])}</text>')

    for i, item in enumerate(items):
        iy = y + 34 + i * 24 + 12
        item_color = "#5a5a5a" if domain["muted"] else color
        text_color = "#808080" if domain["muted"] else "#d0d0d0"
        parts.append(f'<circle cx="{x+13:.1f}" cy="{iy-4}" r="2.1" fill="{item_color}"/>')
        parts.append(f'<text x="{x+24:.1f}" y="{iy}" font-family="Consolas, \'SF Mono\', monospace" '
                     f'font-size="12" fill="{text_color}">{esc(item)}</text>')

    parts.append('</g>')  # reveal group
    return "".join(parts), h


def build_svg():
    final_h = PANEL_TOP + max(panel_height(len(d["items"])) for d in DOMAINS) + 34 + 14

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {final_h:.0f}" width="100%" '
                 f'role="img" aria-labelledby="atlasTitle atlasDesc">')
    parts.append('<title id="atlasTitle">Engineering Atlas — system architecture map</title>')
    parts.append('<desc id="atlasDesc">Kartikeya Yadav at the center, connected to four engineering '
                 'domains: Agentic Systems (multi-layer_orchestation, agent--flow), Intelligent Systems '
                 '(Kovidam-Skill-Graph, kovidam-AI-Interview, RL-model-Negotiation, AI-Video-Editor, '
                 'Financial-Health-Score, ai-image-classifier), Products (GitVeda, blood-group-donor), '
                 'and Web3 (Cardano-BlockPhantom, marked experimental).</desc>')

    parts.append('''<defs>
    <pattern id="dotgrid" width="28" height="28" patternUnits="userSpaceOnUse">
      <circle cx="1" cy="1" r="1" fill="#161616"/>
    </pattern>
    <filter id="glow" x="-250%" y="-250%" width="600%" height="600%"><feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="glowSoft" x="-250%" y="-250%" width="600%" height="600%"><feGaussianBlur stdDeviation="1.3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <radialGradient id="coreGrad" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#fff6e6"/><stop offset="40%" stop-color="#f5a623"/>
      <stop offset="100%" stop-color="#f5a623" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="scanGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#f5a623" stop-opacity="0"/><stop offset="50%" stop-color="#f5a623" stop-opacity="0.5"/>
      <stop offset="100%" stop-color="#f5a623" stop-opacity="0"/>
    </linearGradient>
  </defs>''')

    parts.append(f'<rect x="0.5" y="0.5" width="{W-1}" height="{final_h-1:.0f}" rx="14" fill="#0a0a0a" stroke="#1f1f1f"/>')
    parts.append(f'<rect x="14" y="14" width="{W-28}" height="{final_h-28:.0f}" fill="url(#dotgrid)"/>')
    parts.append(starfield(h=final_h))

    # telemetry header
    parts.append('<text x="20" y="26" font-family="Consolas, \'SF Mono\', monospace" font-size="10" fill="#555">ATLAS // 04</text>')
    parts.append(f'<circle cx="105" cy="22.5" r="2.5" fill="#22c55e" filter="url(#glow)">'
                 f'{smooth_animate("opacity", "1;0.35;1", "1.8s")}</circle>')
    parts.append(f'<text x="{W-20}" y="26" text-anchor="end" font-family="Consolas, \'SF Mono\', monospace" '
                 f'font-size="10" fill="#555">DOMAIN · SYSTEM · CONNECTION</text>')

    # scanline sweep — replays at the start of every CYCLE-second loop
    sweep_end_t = 0.15 + 1.3
    t_sweep = sweep_end_t / CYCLE
    t_start = 0.15 / CYCLE
    parts.append(
        f'<rect x="14" y="14" width="{W-28}" height="6" fill="url(#scanGrad)">'
        f'<animateTransform attributeName="transform" type="translate" '
        f'values="0,0;0,0;0,{final_h-40:.0f};0,{final_h-40:.0f}" '
        f'keyTimes="0;{t_start:.4f};{t_sweep:.4f};1" calcMode="spline" '
        f'keySplines="{EASE};{EASE};{EASE}" dur="{CYCLE}s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="0;1;1;0;0" '
        f'keyTimes="0;{t_start:.4f};{(t_start+0.08):.4f};{t_sweep:.4f};1" calcMode="spline" '
        f'keySplines="{EASE};{EASE};{EASE};{EASE}" dur="{CYCLE}s" repeatCount="indefinite"/></rect>'
    )

    cx, cy = CORE["cx"], CORE["cy"]

    # ---- central core: orbit rings + nameplate ----
    parts.append(f'<g opacity="0">{cycle_reveal(0.5, 1.2)}')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="60" fill="url(#coreGrad)" opacity="0.5">'
                 f'{smooth_animate("r", "55;65;55", "3.2s")}'
                 f'{smooth_animate("opacity", "0.4;0.6;0.4", "3.2s")}</circle>')
    parts.append(render_orbit_ring(cx, cy, 150, 34, "#22d3ee", 9, False))
    parts.append(render_orbit_ring(cx, cy, 190, 46, "#f5a623", 12, True))
    # expanding ping ring
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="26" fill="none" stroke="#f5a623" stroke-width="1.4" opacity="0.5">'
                 f'{smooth_animate("r", "26;70;26", "4s")}'
                 f'{smooth_animate("opacity", "0.5;0;0.5", "4s")}</circle>')

    parts.append(f'<rect x="{cx-100}" y="{cy-23}" width="200" height="46" rx="6" fill="#141414" '
                 f'stroke="#f5a623" stroke-width="1.2" filter="url(#glowSoft)"/>')
    parts.append(f'<text x="{cx}" y="{cy+6}" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" '
                 f'font-size="18" font-weight="700" letter-spacing="2" fill="#f5a623">{CORE["name"]}</text>')
    parts.append(f'<text x="{cx}" y="{cy+45}" text-anchor="middle" font-family="Consolas, \'SF Mono\', monospace" '
                 f'font-size="10.5" letter-spacing="1" fill="#8a8a8a">{CORE["tagline"]}</text>')
    parts.append('</g>')

    # ---- rail ----
    parts.append(f'<g opacity="0">{cycle_reveal(1.0, 1.5)}')
    parts.append(f'<line x1="{cx}" y1="{cy+80}" x2="{cx}" y2="{RAIL_Y}" stroke="#3a3a3a" stroke-width="1"/>')
    x_left, x_right = DOMAINS[0]["cx"], DOMAINS[-1]["cx"]
    parts.append(f'<line x1="{x_left}" y1="{RAIL_Y}" x2="{x_right}" y2="{RAIL_Y}" stroke="#3a3a3a" stroke-width="1"/>')
    parts.append('</g>')

    # ---- connectors (energy pulses core -> module, staggered) ----
    for i, d in enumerate(DOMAINS):
        parts.append(f'<g opacity="0">{cycle_reveal(1.1 + i * 0.1, 1.5 + i * 0.1)}')
        parts.append(render_connector(cx, cy + 80, d["cx"], RAIL_Y, d["cx"], PANEL_TOP,
                                       d["color"], delay=1.3 + i * 0.35))
        parts.append('</g>')

    # ---- modules ----
    pulse_durs = [2.0, 2.3, 2.6, 2.15]
    max_bottom = PANEL_TOP
    for i, d in enumerate(DOMAINS):
        appear_start = 1.2 + i * 0.18
        svg, h = render_domain(d, appear_start=appear_start, appear_end=appear_start + 0.6, pulse_dur=pulse_durs[i])
        parts.append(svg)
        max_bottom = max(max_bottom, PANEL_TOP + h)

    footer_y = max_bottom + 34
    parts.append(f'<line x1="20" y1="{footer_y-18:.0f}" x2="{W-20}" y2="{footer_y-18:.0f}" stroke="#1f1f1f" stroke-width="1"/>')
    parts.append(f'<text x="{cx}" y="{footer_y:.0f}" text-anchor="middle" font-family="Consolas, \'SF Mono\', monospace" '
                 f'font-size="10" fill="#666">ARCHITECTURE MAP — DOMAINS, SYSTEMS, AND HOW THEY CONNECT</text>')

    parts.append('</svg>')
    return "\n".join(parts)


def main():
    try:
        svg = build_svg()
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: atlas generation failed, leaving existing file untouched: {e}", file=sys.stderr)
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
