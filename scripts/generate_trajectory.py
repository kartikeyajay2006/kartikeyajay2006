#!/usr/bin/env python3
"""Generate assets/trajectory.svg — the section 10 "Engineering Journey"
timeline: a gradient spine of milestone nodes, each with its own icon badge
and card, a scoreboard strip tallied from those milestones, and a year-by-
year progress rail at the bottom.

Honesty note (see also generate_atlas.py / generate_constellation.py): SVG
has no hover or JavaScript on GitHub, so "alive" is ambient SMIL only — a
pulse traveling down the spine, breathing node halos, a ping on the latest
milestone, blinking ACTIVE dots. Card text never moves or fades, and no
element starts hidden, so a renderer that ignores SMIL shows the full
timeline. Gradients painted on straight lines use gradientUnits=
"userSpaceOnUse": an objectBoundingBox gradient on a zero-width/zero-height
line has an empty bounding box and is not rendered at all (that is why the
previous hand-written version's spine never showed up).

Content is curated, not fetched: milestones are self-reported career
markers supplied by the profile owner, not derived from repository
activity. The scoreboard numbers are counted from the MILESTONES list
below — nothing is typed in separately. There is no live-data workflow for
this asset (same as engineering-atlas.svg / project-constellation.svg).

Never-fail contract: this script always exits 0. Any problem is logged
to stderr and the script leaves the existing output file untouched.
"""
import os
import sys

OUT_PATH = os.environ.get("OUT_PATH", "assets/trajectory.svg")

W = 900
SPINE_X = 90
CARD_X = 128
CARD_W = 732
FIRST_CY = 184
STEP = 94
EASE = "0.42 0 0.58 1"
GRAD = "url(#rushGrad)"  # colour token for the gradient ("Gradient Rush") milestone

MONO = "Consolas, 'SF Mono', monospace"
SANS = "Helvetica, Arial, sans-serif"

# tally: which scoreboard bucket a milestone counts toward (None = not counted)
MILESTONES = [
    {"year": "2022", "color": "#f5a623", "icon": "code", "badge": "FOUNDATION",
     "title": "Started coding", "sub": "Took the first step into the world of code."},
    {"year": "2023", "color": "#eab308", "icon": "net", "badge": "BREAKTHROUGH",
     "title": "Discovered Machine Learning", "sub": "Fell in love with patterns, data &amp; intelligence."},
    {"year": "2024", "color": "#22c55e", "icon": "spark", "badge": "EXPLORATION",
     "title": "Discovered AI", "sub": "Explored models, agents &amp; intelligent systems."},
    {"year": "2024", "color": "#22d3ee", "icon": "trophy", "badge": "ACHIEVEMENT",
     "title": "Young AI — Winner", "tally": "win"},
    {"year": "2025", "color": "#3b82f6", "icon": "rocket", "badge": "ACHIEVEMENT",
     "title": "Auraverse Hackathon — Winner", "tally": "win"},
    {"year": "2025", "color": "#a855f7", "icon": "medal", "badge": "RECOGNITION",
     "title": "Cardano Hackathon, Asia — Finalist", "tally": "finalist"},
    {"year": "2026", "color": "#ec4899", "icon": "chart", "badge": "PLACEMENT",
     "title": "Mela VC Ventures — 2nd Place", "tally": "runner"},
    {"year": "2026", "color": "#ffffff", "icon": "stack", "badge": "FOUNDER",
     "title": "Co-founded Kovidam", "sub": "AI talent-intelligence platform — building and shipping real products.",
     "tally": "role", "active": True},
    {"year": "2026", "month": "SEP", "color": GRAD, "icon": "cup", "badge": "ACHIEVEMENT",
     "title": "Gradient Rush Hackathon — Winner", "sub": "First place — September 2026.",
     "tally": "win", "latest": True},
    {"year": "2026", "color": "#a3e635", "icon": "people", "badge": "LEADERSHIP",
     "title": "Product &amp; Applied AI Lead — AI-ML Club",
     "sub": "Leading product and applied-AI work at the college AI-ML Club.", "tally": "role", "active": True},
]

SCOREBOARD = [
    ("win", "WINS", "#f5a623"),
    ("runner", "RUNNER-UP", "#ec4899"),
    ("finalist", "FINALIST", "#a855f7"),
    ("role", "ACTIVE ROLES", "#22c55e"),
]

ERAS = [  # bottom progress rail
    ("2022", "FOUNDATION"), ("2023", "LEARNING"), ("2024", "EXPLORATION"),
    ("2025", "RECOGNITION"), ("2026", "BUILDING · LEADING"),
]


def smooth_animate(attr, values, dur, keyTimes="0;0.5;1", extra=""):
    n = len(values.split(";"))
    splines = ";".join([EASE] * (n - 1))
    return (f'<animate attributeName="{attr}" values="{values}" keyTimes="{keyTimes}" '
            f'calcMode="spline" keySplines="{splines}" dur="{dur}" repeatCount="indefinite"{extra}/>')


def solid(c):
    """A plain colour stand-in for the gradient token where a gradient won't do (halos, spine stops)."""
    return "#c084fc" if c == GRAD else c


# ------------------------------------------------------------------ icons
def icon(kind, cx, cy, c):
    sw = f'fill="none" stroke="{c}" stroke-linecap="round" stroke-linejoin="round"'
    if kind == "code":
        return (f'<polyline points="{cx-7},{cy-6} {cx-11},{cy} {cx-7},{cy+6}" {sw} stroke-width="1.7"/>'
                f'<polyline points="{cx+7},{cy-6} {cx+11},{cy} {cx+7},{cy+6}" {sw} stroke-width="1.7"/>')
    if kind == "net":
        a, b, d = (cx, cy - 7), (cx - 7, cy + 6), (cx + 7, cy + 6)
        return (f'<polygon points="{a[0]},{a[1]} {b[0]},{b[1]} {d[0]},{d[1]}" {sw} stroke-width="1.3"/>'
                + "".join(f'<circle cx="{x}" cy="{y}" r="2.1" fill="{c}"/>' for x, y in (a, b, d)))
    if kind == "spark":
        return (f'<path d="M{cx},{cy-10} L{cx+2.5},{cy-2.5} L{cx+10},{cy} L{cx+2.5},{cy+2.5} L{cx},{cy+10} '
                f'L{cx-2.5},{cy+2.5} L{cx-10},{cy} L{cx-2.5},{cy-2.5} Z" fill="{c}"/>')
    if kind in ("trophy", "cup"):
        out = (f'<path d="M{cx-8},{cy-6} h16 v5 a8,8 0 0 1 -16,0 Z" {sw} stroke-width="1.6"/>'
               f'<path d="M{cx-8},{cy-5} h-4 a4,4 0 0 0 4,7" {sw} stroke-width="1.3"/>'
               f'<path d="M{cx+8},{cy-5} h4 a4,4 0 0 1 -4,7" {sw} stroke-width="1.3"/>'
               f'<line x1="{cx}" y1="{cy+7}" x2="{cx}" y2="{cy+11}" {sw} stroke-width="1.6"/>'
               f'<line x1="{cx-5}" y1="{cy+11}" x2="{cx+5}" y2="{cy+11}" {sw} stroke-width="1.6"/>')
        if kind == "cup":  # star inside the cup marks the latest win
            out += (f'<path d="M{cx},{cy-4.5} L{cx+1.2},{cy-2} L{cx+3.8},{cy-1.7} L{cx+1.9},{cy} L{cx+2.4},{cy+2.6} '
                    f'L{cx},{cy+1.3} L{cx-2.4},{cy+2.6} L{cx-1.9},{cy} L{cx-3.8},{cy-1.7} L{cx-1.2},{cy-2} Z" fill="{c}"/>')
        return out
    if kind == "rocket":
        return (f'<path d="M{cx},{cy-9} c5,3 6,10 3,15 l-3,3 l-3,-3 c-3,-5 -2,-12 3,-15 Z" {sw} stroke-width="1.5"/>'
                f'<circle cx="{cx}" cy="{cy-2}" r="2" fill="{c}"/>'
                f'<line x1="{cx-4}" y1="{cy+9}" x2="{cx-7}" y2="{cy+15}" {sw} stroke-width="1.3"/>'
                f'<line x1="{cx+4}" y1="{cy+9}" x2="{cx+7}" y2="{cy+15}" {sw} stroke-width="1.3"/>')
    if kind == "medal":
        return (f'<line x1="{cx-2}" y1="{cy+6}" x2="{cx-5.5}" y2="{cy+16}" {sw} stroke-width="1.8"/>'
                f'<line x1="{cx+2}" y1="{cy+6}" x2="{cx+5.5}" y2="{cy+16}" {sw} stroke-width="1.8"/>'
                f'<circle cx="{cx}" cy="{cy-3}" r="8" fill="#0b0b0d" stroke="{c}" stroke-width="1.8"/>'
                f'<path d="M{cx},{cy-7.5} L{cx+1.6},{cy-4.1} L{cx+5.2},{cy-3.6} L{cx+2.6},{cy-1.1} L{cx+3.3},{cy+2.5} '
                f'L{cx},{cy+0.7} L{cx-3.3},{cy+2.5} L{cx-2.6},{cy-1.1} L{cx-5.2},{cy-3.6} L{cx-1.6},{cy-4.1} Z" fill="{c}"/>')
    if kind == "chart":
        return (f'<rect x="{cx-10}" y="{cy+4}" width="4" height="6" fill="{c}"/>'
                f'<rect x="{cx-3}" y="{cy-1}" width="4" height="11" fill="{c}"/>'
                f'<rect x="{cx+4}" y="{cy-7}" width="4" height="17" fill="{c}"/>'
                f'<polyline points="{cx-10},{cy-2} {cx-3},{cy-9} {cx+4},{cy-6} {cx+10},{cy-14}" {sw} stroke-width="1.4"/>')
    if kind == "stack":
        return (f'<rect x="{cx-7}" y="{cy-8}" width="14" height="3.4" rx="1.5" {sw} stroke-width="1.2"/>'
                f'<rect x="{cx-7}" y="{cy-2}" width="14" height="3.4" rx="1.5" {sw} stroke-width="1.2"/>'
                f'<rect x="{cx-7}" y="{cy+4}" width="14" height="3.4" rx="1.5" fill="{c}"/>')
    if kind == "people":
        return (f'<circle cx="{cx-4}" cy="{cy-4}" r="3.2" {sw} stroke-width="1.5"/>'
                f'<path d="M{cx-10},{cy+8} a6,6 0 0 1 12,0" {sw} stroke-width="1.5"/>'
                f'<circle cx="{cx+5}" cy="{cy-2}" r="2.6" {sw} stroke-width="1.4"/>'
                f'<path d="M{cx+3.5},{cy+3.4} a5,5 0 0 1 7,4.6" {sw} stroke-width="1.4"/>')
    return ""


# ------------------------------------------------------------------ pieces
def render_scoreboard(y):
    counts = {k: sum(1 for m in MILESTONES if m.get("tally") == k) for k, _, _ in SCOREBOARD}
    detail = {}
    for k, _, _ in SCOREBOARD:
        items = [m for m in MILESTONES if m.get("tally") == k]
        if k == "win":
            detail[k] = " · ".join(dict.fromkeys(m["year"] for m in items))
        elif k == "role":
            detail[k] = "Kovidam · AI-ML Club"
        else:
            detail[k] = " · ".join(m["title"].split(" — ")[0].replace("Hackathon, ", "") + f' · {m["year"]}'
                                   for m in items)
    gap = 12
    tw = (860 - gap * (len(SCOREBOARD) - 1)) / len(SCOREBOARD)
    out = []
    for i, (k, label, c) in enumerate(SCOREBOARD):
        x = 20 + i * (tw + gap)
        out.append(f'<rect x="{x:.1f}" y="{y}" width="{tw:.1f}" height="50" rx="8" fill="#101014" stroke="#1f1f24"/>')
        out.append(f'<rect x="{x+1:.1f}" y="{y+10}" width="2.5" height="30" rx="1.2" fill="{c}"/>')
        out.append(f'<text x="{x+16:.1f}" y="{y+33}" font-family="{MONO}" font-size="22" font-weight="700" '
                   f'fill="{c}">{counts[k]:02d}</text>')
        out.append(f'<text x="{x+56:.1f}" y="{y+21}" font-family="{MONO}" font-size="9.5" letter-spacing="1.2" '
                   f'fill="#d0d0d0">{label}</text>')
        out.append(f'<text x="{x+56:.1f}" y="{y+36}" font-family="{SANS}" font-size="10" fill="#6f6f6f">'
                   f'{detail[k]}</text>')
        if k == "role":
            out.append(f'<circle cx="{x+tw-12:.1f}" cy="{y+12}" r="2.4" fill="{c}">'
                       f'{smooth_animate("opacity", "1;0.25;1", "1.6s")}</circle>')
    return "".join(out)


def render_node(i, m, cy):
    c = m["color"]
    halo = solid(c)
    top = cy - 32
    out = ['<g>']

    # year column
    out.append(f'<text x="16" y="{cy-2}" font-family="{MONO}" font-size="19" font-weight="700" fill="{c}">{m["year"]}</text>')
    sub = f'&gt;&gt; {m["month"]}' if m.get("month") else "&gt;&gt;"
    out.append(f'<text x="16" y="{cy+14}" font-family="{MONO}" font-size="10" letter-spacing="1" '
               f'fill="{halo if m.get("month") else "#4a4a4a"}">{sub}</text>')

    # badge: breathing halo, optional ping, ring, icon
    out.append(f'<circle cx="{SPINE_X}" cy="{cy}" r="25" fill="{halo}" opacity="0.22" filter="url(#softBlur)">'
               f'{smooth_animate("opacity", "0.14;0.32;0.14", f"{3.2 + (i % 4) * 0.35:.2f}s")}</circle>')
    if m.get("latest"):
        out.append(f'<circle cx="{SPINE_X}" cy="{cy}" r="20" fill="none" stroke="{halo}" stroke-width="1.4">'
                   f'{smooth_animate("r", "20;34;34", "2.4s", keyTimes="0;0.8;1")}'
                   f'{smooth_animate("opacity", "0.8;0;0", "2.4s", keyTimes="0;0.8;1")}</circle>')
    out.append(f'<circle cx="{SPINE_X}" cy="{cy}" r="20" fill="#0b0b0d" stroke="{c}" stroke-width="2"/>')
    out.append(icon(m["icon"], SPINE_X, cy, c))

    # card
    out.append(f'<rect x="{CARD_X}" y="{top}" width="{CARD_W}" height="64" rx="10" fill="#101014" stroke="#1f1f24"/>')
    if m.get("latest"):
        out.append(f'<rect x="{CARD_X}" y="{top}" width="{CARD_W}" height="64" rx="10" fill="none" stroke="{c}" '
                   f'stroke-width="1" opacity="0.55"/>')
    out.append(f'<rect x="{CARD_X+1}" y="{top+6}" width="3" height="52" rx="1.5" fill="{c}"/>')

    # category pill, right-aligned
    bw = len(m["badge"]) * 6.4 + 24
    bx = 846 - bw
    out.append(f'<rect x="{bx:.1f}" y="{top+10}" width="{bw:.1f}" height="18" rx="9" fill="#0d0d10" stroke="{c}" opacity="0.8"/>')
    out.append(f'<text x="{bx+8:.1f}" y="{top+22.5}" font-family="{MONO}" font-size="9" letter-spacing="1" '
               f'fill="{c}">{m["badge"]}</text>')
    out.append(f'<circle cx="838" cy="{top+19}" r="2" fill="{c}"/>')

    # status under the pill
    if m.get("active"):
        out.append(f'<circle cx="{846-46}" cy="{top+44}" r="2.4" fill="#22c55e">'
                   f'{smooth_animate("opacity", "1;0.25;1", "1.6s")}</circle>')
        out.append(f'<text x="846" y="{top+47.5}" text-anchor="end" font-family="{MONO}" font-size="9" '
                   f'letter-spacing="1" fill="#22c55e">ACTIVE</text>')
    if m.get("latest"):
        out.append(f'<text x="846" y="{top+47.5}" text-anchor="end" font-family="{MONO}" font-size="9" '
                   f'letter-spacing="1.5" font-weight="700" fill="{c}">LATEST'
                   f'{smooth_animate("opacity", "1;0.35;1", "1.8s")}</text>')

    # title / subtitle
    if m.get("sub"):
        out.append(f'<text x="146" y="{cy-4}" font-family="{SANS}" font-size="14" font-weight="700" fill="#f2f2f2">{m["title"]}</text>')
        out.append(f'<text x="146" y="{cy+15}" font-family="{SANS}" font-size="11" fill="#8f8f8f">{m["sub"]}</text>')
    else:
        out.append(f'<text x="146" y="{cy+4}" font-family="{SANS}" font-size="14" font-weight="700" fill="#f2f2f2">{m["title"]}</text>')
    out.append('</g>')
    return "".join(out)


def build_svg():
    n = len(MILESTONES)
    last_cy = FIRST_CY + (n - 1) * STEP
    div_y = last_cy + 54
    rail_y = div_y + 28
    H = rail_y + 106

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
                 f'aria-labelledby="trajTitle trajDesc">')
    parts.append('<title id="trajTitle">Engineering Journey Timeline</title>')
    desc = "; ".join(f'{m.get("month", "")} {m["year"]} — {m["title"]}'.strip() for m in MILESTONES)
    parts.append(f'<desc id="trajDesc">Timeline from {MILESTONES[0]["year"]} to {MILESTONES[-1]["year"]}: {desc}. '
                 f'Milestones are self-reported career markers, not derived from repository activity.</desc>')

    stops = "".join(
        f'<stop offset="{(i / (n - 1)) * 100:.1f}%" stop-color="{solid(m["color"])}"/>' for i, m in enumerate(MILESTONES))
    parts.append(f'''<defs>
    <filter id="softBlur" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="4"/></filter>
    <filter id="glow" x="-250%" y="-250%" width="600%" height="600%"><feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <linearGradient id="spineGrad" gradientUnits="userSpaceOnUse" x1="0" y1="{FIRST_CY}" x2="0" y2="{last_cy}">{stops}</linearGradient>
    <linearGradient id="rushGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#22d3ee"/><stop offset="50%" stop-color="#a855f7"/><stop offset="100%" stop-color="#ec4899"/>
    </linearGradient>
    <linearGradient id="footerGrad" gradientUnits="userSpaceOnUse" x1="60" y1="0" x2="820" y2="0">
      <stop offset="0%" stop-color="#f5a623"/><stop offset="35%" stop-color="#22c55e"/>
      <stop offset="70%" stop-color="#a855f7"/><stop offset="100%" stop-color="#ffffff"/>
    </linearGradient>
  </defs>''')

    parts.append(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="14" fill="#0a0a0a" stroke="#1f1f1f"/>')

    # header
    parts.append(f'<text x="20" y="26" font-family="{MONO}" font-size="10" letter-spacing="1" fill="#555">'
                 f'JOURNEY // TIMELINE · {n} MILESTONES</text>')
    parts.append(f'<text x="872" y="26" text-anchor="end" font-family="{MONO}" font-size="10" letter-spacing="1" fill="#555">SYSTEM // 10</text>')
    parts.append(f'<circle cx="880" cy="22" r="3" fill="#a855f7">'
                 f'<animate attributeName="opacity" values="1;0.3;1" dur="2.4s" repeatCount="indefinite"/></circle>')

    # terminal intro strip
    parts.append('<rect x="20" y="36" width="860" height="30" rx="6" fill="#101014" stroke="#242430"/>')
    parts.append(f'<text x="34" y="56" font-family="{MONO}" font-size="12" fill="#666">&gt;</text>')
    parts.append(f'<text x="48" y="56" font-family="{MONO}" font-size="12" fill="#c9c9c9">A timeline of '
                 f'<tspan fill="#3b82f6">learning</tspan>, <tspan fill="#22c55e">building</tspan>, '
                 f'<tspan fill="#a855f7">competing</tspan>, <tspan fill="#a3e635">leading</tspan> and '
                 f'<tspan fill="#f5a623">growing</tspan>.<tspan fill="#c9c9c9"> ▍'
                 f'<animate attributeName="fill-opacity" values="1;1;0;0" keyTimes="0;0.5;0.5;1" dur="1.1s" '
                 f'repeatCount="indefinite"/></tspan></text>')

    parts.append(render_scoreboard(78))

    # spine: soft glow + crisp line + a pulse that travels to the latest milestone
    parts.append(f'<line x1="{SPINE_X}" y1="{FIRST_CY}" x2="{SPINE_X}" y2="{last_cy}" stroke="url(#spineGrad)" '
                 f'stroke-width="6" opacity="0.18" filter="url(#softBlur)"/>')
    parts.append(f'<line x1="{SPINE_X}" y1="{FIRST_CY}" x2="{SPINE_X}" y2="{last_cy}" stroke="url(#spineGrad)" stroke-width="2"/>')
    for k in range(2):
        parts.append(f'<circle r="3" fill="#ffffff" filter="url(#glow)">'
                     f'<animateMotion dur="7s" begin="{-3.5 * k:.1f}s" repeatCount="indefinite" '
                     f'path="M{SPINE_X},{FIRST_CY} L{SPINE_X},{last_cy}" calcMode="spline" keyPoints="0;1" '
                     f'keyTimes="0;1" keySplines="{EASE}"/>'
                     f'<animate attributeName="opacity" values="0;0.9;0.9;0" keyTimes="0;0.08;0.9;1" dur="7s" '
                     f'begin="{-3.5 * k:.1f}s" repeatCount="indefinite"/></circle>')

    for i, m in enumerate(MILESTONES):
        parts.append(render_node(i, m, FIRST_CY + i * STEP))

    parts.append(f'<line x1="20" y1="{div_y}" x2="880" y2="{div_y}" stroke="#1f1f1f" stroke-width="1"/>')

    # progress rail
    xs = [60 + i * 152 for i in range(len(ERAS))]
    era_color = {}
    for m in MILESTONES:
        era_color.setdefault(m["year"], solid(m["color"]))
    now_x = xs[-1]
    p = [f'<g font-family="{MONO}">']
    p.append(f'<line x1="60" y1="{rail_y}" x2="820" y2="{rail_y}" stroke="url(#footerGrad)" stroke-width="3" '
             f'opacity="0.2" filter="url(#softBlur)"/>')
    p.append(f'<line x1="60" y1="{rail_y}" x2="820" y2="{rail_y}" stroke="url(#footerGrad)" stroke-width="1.4"/>')
    p.append(f'<path d="M812,{rail_y-5} L822,{rail_y} L812,{rail_y+5} Z" fill="#ffffff"/>')
    p.append(f'<circle r="2.4" fill="#ffffff" filter="url(#glow)">'
             f'<animateMotion dur="5s" repeatCount="indefinite" path="M60,{rail_y} L{now_x},{rail_y}"/>'
             f'<animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.1;0.85;1" dur="5s" repeatCount="indefinite"/></circle>')
    for (year, label), x in zip(ERAS, xs):
        is_now = x == now_x
        p.append(f'<circle cx="{x}" cy="{rail_y}" r="3" fill="{era_color.get(year, "#888")}"/>')
        p.append(f'<text x="{x}" y="{rail_y-14}" text-anchor="middle" font-size="10" font-weight="700" '
                 f'fill="{"#ffffff" if is_now else "#e0e0e0"}">{year}</text>')
        p.append(f'<text x="{x}" y="{rail_y+20}" text-anchor="middle" font-size="9" letter-spacing="0.5" '
                 f'fill="{"#a3e635" if is_now else "#666"}">{label}</text>')
    p.append(f'<circle cx="{now_x}" cy="{rail_y}" r="3" fill="none" stroke="#a3e635" stroke-width="1.2">'
             f'{smooth_animate("r", "3;11;11", "2.2s", keyTimes="0;0.8;1")}'
             f'{smooth_animate("opacity", "0.9;0;0", "2.2s", keyTimes="0;0.8;1")}</circle>')
    p.append(f'<text x="{now_x}" y="{rail_y+33}" text-anchor="middle" font-size="8.5" letter-spacing="1.5" '
             f'font-weight="700" fill="#a3e635">▲ NOW</text>')
    p.append(f'<text x="822" y="{rail_y+5}" font-size="15" font-weight="700" fill="#ffffff">∞</text>')
    p.append(f'<text x="822" y="{rail_y+20}" text-anchor="middle" font-size="9" letter-spacing="0.5" fill="#666">BEYOND</text>')
    p.append('</g>')
    parts.append("".join(p))

    parts.append(f'<text x="450" y="{rail_y+66}" text-anchor="middle" font-family="{MONO}" font-size="13" '
                 f'font-weight="700" letter-spacing="2" fill="#e8e8e8">THE JOURNEY CONTINUES...</text>')
    parts.append(f'<text x="450" y="{rail_y+86}" text-anchor="middle" font-family="{SANS}" font-size="11" fill="#777">'
                 f'From 2022 to Beyond — learning, building, failing, winning, leading &amp; evolving every single day.</text>')

    parts.append('</svg>')
    return "\n".join(parts)


def main():
    try:
        svg = build_svg()
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: trajectory generation failed, leaving existing file untouched: {e}", file=sys.stderr)
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
