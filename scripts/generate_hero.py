#!/usr/bin/env python3
"""Generate assets/hero-banner.svg — the top-of-profile name/role banner.

Static branding content (name, roles, tagline, the four K/0N category
cards) — no GitHub API needed, nothing here is a data claim, so there's
no never-fail contract to worry about beyond "don't crash." Built as an
SVG (not styled HTML) because GitHub strips inline <style> and most CSS
from rendered README markdown, so a gradient name / bordered icon cards
/ custom typography can only survive as an image, the same reasoning
behind every other asset in this profile.

IMPORTANT: the PORTFOLIO / KOVIDAM / LINKEDIN / GITHUB nav links stay as
real markdown links directly above this image in the README, not inside
it — an <img> is not interactive, so anything clickable has to live
outside the SVG (see contact-terminal.svg for the same rule).
"""
import os
import sys

OUT_PATH = os.environ.get("OUT_PATH", "assets/hero-banner.svg")

CARDS = [
    ("K/01", "AI SYSTEMS", "brain", "#60a5fa"),
    ("K/02", "AGENTIC AI", "nodes", "#818cf8"),
    ("K/03", "BACKEND", "layers", "#a78bfa"),
    ("K/04", "PRODUCTS", "cube", "#c084fc"),
]


def icon(kind, cx, cy, color):
    if kind == "brain":
        return (f'<circle cx="{cx}" cy="{cy}" r="10" fill="none" stroke="{color}" stroke-width="1.5"/>'
                f'<path d="M{cx-4},{cy-6} Q{cx},{cy} {cx-4},{cy+6}" fill="none" stroke="{color}" stroke-width="1.2"/>'
                f'<path d="M{cx+4},{cy-6} Q{cx},{cy} {cx+4},{cy+6}" fill="none" stroke="{color}" stroke-width="1.2"/>'
                f'<circle cx="{cx}" cy="{cy}" r="1.6" fill="{color}"/>')
    if kind == "nodes":
        pts = [(cx, cy - 9), (cx - 9, cy + 6), (cx + 9, cy + 6)]
        lines = "".join(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{color}" stroke-width="1.1"/>'
                         for a, b in [(pts[0], pts[1]), (pts[1], pts[2]), (pts[2], pts[0])])
        dots = "".join(f'<circle cx="{p[0]}" cy="{p[1]}" r="2.4" fill="{color}"/>' for p in pts)
        return lines + dots
    if kind == "layers":
        return "".join(
            f'<rect x="{cx-9}" y="{cy-8+i*6.5}" width="18" height="4" rx="1.4" fill="none" stroke="{color}" stroke-width="1.3"/>'
            for i in range(3)
        )
    if kind == "cube":
        return (f'<rect x="{cx-8}" y="{cy-8}" width="16" height="16" rx="2.5" fill="none" stroke="{color}" stroke-width="1.5"/>'
                f'<line x1="{cx-8}" y1="{cy}" x2="{cx+8}" y2="{cy}" stroke="{color}" stroke-width="1" opacity="0.6"/>'
                f'<line x1="{cx}" y1="{cy-8}" x2="{cx}" y2="{cy+8}" stroke="{color}" stroke-width="1" opacity="0.6"/>')
    return ""


def build_svg():
    W, H = 900, 360
    left, right = 20, 880
    inner_w = right - left

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" '
                  f'role="img" aria-labelledby="hTitle hDesc">')
    parts.append('<title id="hTitle">Kartikeya Yadav — AI/ML Engineer, Founder, System Builder</title>')
    parts.append('<desc id="hDesc">Building intelligent systems across AI, Agents, ML, Backend, and Products. '
                 'Four focus areas: AI Systems, Agentic AI, Backend, Products.</desc>')

    parts.append('''<defs>
    <linearGradient id="nameGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#eef2ff"/>
      <stop offset="45%" stop-color="#93c5fd"/>
      <stop offset="100%" stop-color="#c084fc"/>
    </linearGradient>
    <radialGradient id="heroHalo" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#7c3aed" stop-opacity="0.22"/>
      <stop offset="100%" stop-color="#7c3aed" stop-opacity="0"/>
    </radialGradient>
    <filter id="glowSoft" x="-250%" y="-250%" width="600%" height="600%">
      <feGaussianBlur stdDeviation="1.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>''')

    parts.append(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="16" fill="#0a0a0a" stroke="#1f1f1f"/>')

    cx = W / 2
    parts.append(f'<ellipse cx="{cx}" cy="70" rx="260" ry="90" fill="url(#heroHalo)"/>')

    parts.append(f'<text x="{cx}" y="76" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" '
                 f'font-size="46" font-weight="800" letter-spacing="6" fill="url(#nameGrad)">KARTIKEYA YADAV</text>')

    div_y = 106
    parts.append(f'<line x1="{cx-170}" y1="{div_y}" x2="{cx-56}" y2="{div_y}" stroke="#3b2a5e" stroke-width="1"/>')
    parts.append(f'<path d="M{cx-60},{div_y-4} L{cx-52},{div_y} L{cx-60},{div_y+4}" fill="none" stroke="#a78bfa" stroke-width="1.2"/>')
    parts.append(f'<text x="{cx}" y="{div_y+4}" text-anchor="middle" font-family="Consolas, \'SF Mono\', monospace" '
                 f'font-size="11" letter-spacing="2" fill="#a78bfa">K / 01</text>')
    parts.append(f'<path d="M{cx+60},{div_y-4} L{cx+52},{div_y} L{cx+60},{div_y+4}" fill="none" stroke="#a78bfa" stroke-width="1.2"/>')
    parts.append(f'<line x1="{cx+56}" y1="{div_y}" x2="{cx+170}" y2="{div_y}" stroke="#3b2a5e" stroke-width="1"/>')

    parts.append(f'<text x="{cx}" y="136" text-anchor="middle" font-family="Consolas, monospace" font-size="13" '
                 f'letter-spacing="3" fill="#c9c9c9">AI/ML ENGINEER &#183; FOUNDER &#183; SYSTEM BUILDER</text>')

    parts.append(f'<text x="{cx}" y="168" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" '
                 f'font-size="14" fill="#9a9a9a">Building intelligent systems across</text>')
    parts.append(f'<text x="{cx}" y="190" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="15">'
                 f'<tspan fill="#60a5fa" font-weight="700">AI</tspan><tspan fill="#666"> &#183; </tspan>'
                 f'<tspan fill="#818cf8" font-weight="700">Agents</tspan><tspan fill="#666"> &#183; </tspan>'
                 f'<tspan fill="#a78bfa" font-weight="700">ML</tspan><tspan fill="#666"> &#183; </tspan>'
                 f'<tspan fill="#c084fc" font-weight="700">Backend</tspan><tspan fill="#666"> &#183; </tspan>'
                 f'<tspan fill="#e879f9" font-weight="700">Products</tspan></text>')

    card_y, card_h = 216, 92
    gap = 16
    card_w = (inner_w - 3 * gap) / 4
    for i, (code, label, kind, color) in enumerate(CARDS):
        cxp = left + i * (card_w + gap)
        mid = cxp + card_w / 2
        parts.append(f'<rect x="{cxp:.1f}" y="{card_y}" width="{card_w:.1f}" height="{card_h}" rx="12" '
                     f'fill="#101014" stroke="{color}" stroke-opacity="0.45"/>')
        icx, icy = mid, card_y + 30
        parts.append(f'<circle cx="{icx:.1f}" cy="{icy}" r="17" fill="{color}" opacity="0.12" filter="url(#glowSoft)"/>')
        parts.append(icon(kind, icx, icy, color))
        parts.append(f'<text x="{mid:.1f}" y="{card_y+58}" text-anchor="middle" font-family="Consolas, monospace" '
                     f'font-size="10" letter-spacing="1.5" fill="{color}">{code}</text>')
        parts.append(f'<text x="{mid:.1f}" y="{card_y+74}" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" '
                     f'font-size="11" font-weight="700" letter-spacing="0.5" fill="#e5e5e5">{label}</text>')
        parts.append(f'<circle cx="{mid:.1f}" cy="{card_y+card_h-8}" r="2" fill="{color}">'
                     f'<animate attributeName="opacity" values="1;0.3;1" dur="2s" begin="{i*0.35}s" repeatCount="indefinite"/></circle>')

    pill_y = 336
    pill_w, pill_h = 108, 22
    px = cx - pill_w / 2
    parts.append(f'<rect x="{px:.1f}" y="{pill_y-15}" width="{pill_w}" height="{pill_h}" rx="11" '
                 f'fill="#101014" stroke="#a78bfa" stroke-opacity="0.6"/>')
    parts.append(f'<circle cx="{px+16:.1f}" cy="{pill_y-4}" r="3" fill="#22c55e" filter="url(#glowSoft)">'
                 f'<animate attributeName="opacity" values="1;0.35;1" dur="1.8s" repeatCount="indefinite"/></circle>')
    parts.append(f'<text x="{px+26:.1f}" y="{pill_y}" font-family="Consolas, monospace" font-size="10" '
                 f'letter-spacing="1.5" fill="#c9b8f5">SYSTEM // 01</text>')

    parts.append('</svg>')
    return "\n".join(parts)


def main():
    svg = build_svg()
    if "<svg" not in svg or "</svg>" not in svg:
        print("WARNING: generated SVG failed a basic sanity check. Leaving existing file untouched.", file=sys.stderr)
        return
    tmp_path = OUT_PATH + ".tmp"
    os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(svg)
    os.replace(tmp_path, OUT_PATH)
    print(f"Wrote {OUT_PATH} ({len(svg):,} bytes)")


if __name__ == "__main__":
    main()
