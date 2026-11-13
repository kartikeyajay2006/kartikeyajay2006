#!/usr/bin/env python3
"""Generate the section 12 "Contact" finale:

  assets/contact-terminal.svg  — the event horizon: the README ends at a
                                 black hole with a spinning Keplerian
                                 accretion disk, a lensed halo, a photon
                                 ring, polar jets and infalling matter, above
                                 "LET'S BUILD" and chevrons pointing down to
                                 the channel buttons.
  assets/channels/*.svg        — the five channel buttons (GitHub, Portfolio,
                                 LinkedIn, Kovidam, Email): neon glass with a
                                 light sweep, a breathing glow and a small
                                 animated icon.

No GitHub API needed — only the run timestamp.

IMPORTANT: an SVG shown through <img> cannot hold a working link. The banner
is decoration; every button is its own image wrapped in a real <a href> in
the README, so the links work exactly like ordinary markdown links.

SVG notes (see generate_signal.py): all motion is SMIL, nothing uses
<use>/<mpath>, and anything readable is visible without SMIL.

Never-fail contract: this script always exits 0. Any problem is logged to
stderr and the existing files are left untouched.
"""
import math
import os
import random
import sys
from datetime import datetime, timezone

OUT_PATH = os.environ.get("OUT_PATH", "assets/contact-terminal.svg")
CHANNEL_DIR = os.environ.get("CHANNEL_DIR", "assets/channels")
NOW = os.environ.get("CONTACT_NOW", "")

W, H = 900, 392
CX, CY = 450, 172                       # vanishing point of the tunnel
MONO = "ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace"
SANS = "-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif"
EASE = "0.42 0 0.58 1"
ACCEL = "0.62 0 0.95 0.55"              # slow out of the centre, then rushing past

WORDS = ["BUILD", "SHIP", "SCALE", "TALK"]
CYCLE = 12.0                            # seconds for all four words
SUBTITLE = "AI systems · Agentic architectures · Backend systems · Ambitious products"
PILLS = [("COLLABORATIONS", "#a78bfa"), ("OPPORTUNITIES", "#22d3ee"), ("AMBITIOUS BUILDS", "#4ade80")]

CHANNELS = [
    # file, label, sub-label, colour
    ("github", "GITHUB", "@kartikeyajay2006", "#a78bfa"),
    ("portfolio", "PORTFOLIO", "my website", "#22d3ee"),
    ("linkedin", "LINKEDIN", "in/kartikeya2006", "#38bdf8"),
    ("kovidam", "KOVIDAM", "kovidam.co.in", "#fbbf24"),
    ("email", "EMAIL", "say hello", "#f472b6"),
]


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def breathe(attr, values, dur, begin="0s"):
    n = len(values.split(";"))
    kt = ";".join(f"{i / (n - 1):.3f}" for i in range(n))
    return (f'<animate attributeName="{attr}" values="{values}" keyTimes="{kt}" calcMode="spline" '
            f'keySplines="{";".join([EASE] * (n - 1))}" dur="{dur}" begin="{begin}" repeatCount="indefinite"/>')


def window(t_on, t_off):
    """Discrete opacity: on between t_on and t_off (fractions of the word cycle)."""
    if t_on <= 0:
        vals, kts = "1;0", f"0;{t_off:.4f}"
    elif t_off >= 1:
        vals, kts = "0;1", f"0;{t_on:.4f}"
    else:
        vals, kts = "0;1;0", f"0;{t_on:.4f};{t_off:.4f}"
    return (f'<animate attributeName="opacity" values="{vals}" keyTimes="{kts}" calcMode="discrete" '
            f'dur="{CYCLE}s" repeatCount="indefinite"/>')


def scramble(word, rnd):
    glyphs = "#$%&@!?*<>/\\01ΞΣΔ"
    return "".join(rnd.choice(glyphs) if rnd.random() < 0.6 else ch for ch in word)


# ------------------------------------------------------------------ the banner: the event horizon
# The README ends at a black hole. A spinning accretion disk (inner rings faster,
# Keplerian), its far side lensed up and over the shadow into a halo, a photon
# ring, Doppler beaming (the approaching side burns brighter), polar jets,
# matter spiralling in and vanishing at the horizon, and starlight smeared into
# arcs around it. The near half of every ring is drawn over the shadow and the
# far half under it, using two half-plane clips.
BH_W, BH_H = 900, 470
HX, HY, RS = 450, 176, 54          # centre and radius of the shadow
TILT = 0.15                        # disk flattening (ry / rx)


def _ellipse_perim(rx, ry):
    return math.pi * (3 * (rx + ry) - math.sqrt((3 * rx + ry) * (rx + 3 * ry)))


def build_banner(synced):
    rnd = random.Random(1307)
    W_, H_ = BH_W, BH_H
    p = []
    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W_} {H_}" width="100%" role="img" '
             f'aria-labelledby="cTitle cDesc">')
    p.append('<title id="cTitle">Contact — the event horizon</title>')
    p.append('<desc id="cDesc">The profile ends at a black hole: a white-hot accretion disk spins around a black shadow, '
             'its far side bent up over the top by gravity into a glowing halo, with a thin photon ring, blue jets from '
             'the poles and matter spiralling in until it vanishes at the horizon. Below it: Let\'s build — AI systems, '
             'agentic architectures, backend systems, ambitious products; open to collaborations, opportunities and '
             'ambitious builds. The GitHub, Portfolio, LinkedIn, Kovidam and Email buttons directly below this image are '
             'real links.</desc>')
    p.append(f'''<defs>
    <clipPath id="bhFrame"><rect width="{W_}" height="{H_}" rx="16"/></clipPath>
    <clipPath id="bhFar"><rect x="0" y="0" width="{W_}" height="{HY}"/></clipPath>
    <clipPath id="bhNear"><rect x="0" y="{HY}" width="{W_}" height="{H_ - HY}"/></clipPath>
    <radialGradient id="bhSpace" cx="0.5" cy="0.38" r="0.8"><stop offset="0" stop-color="#160a06"/><stop offset="0.45" stop-color="#07040a"/><stop offset="1" stop-color="#020104"/></radialGradient>
    <linearGradient id="bhDisk" gradientUnits="userSpaceOnUse" x1="{HX - 330}" y1="0" x2="{HX + 330}" y2="0">
      <stop offset="0" stop-color="#fff4dc"/><stop offset="0.22" stop-color="#ffd27a"/><stop offset="0.55" stop-color="#ff9a3c"/>
      <stop offset="0.8" stop-color="#e2541f"/><stop offset="1" stop-color="#8a1f12"/></linearGradient>
    <linearGradient id="bhHalo" gradientUnits="userSpaceOnUse" x1="0" y1="{HY - 110}" x2="0" y2="{HY + 110}">
      <stop offset="0" stop-color="#fff1cf"/><stop offset="0.45" stop-color="#ffb35c"/><stop offset="0.7" stop-color="#ff7a2e" stop-opacity="0.55"/>
      <stop offset="1" stop-color="#c2410c" stop-opacity="0.25"/></linearGradient>
    <radialGradient id="bhBloom" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#ff9f43" stop-opacity="0.45"/><stop offset="0.5" stop-color="#ff6b1a" stop-opacity="0.12"/><stop offset="1" stop-color="#ff6b1a" stop-opacity="0"/></radialGradient>
    <linearGradient id="bhJetUp" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#a5f3fc" stop-opacity="0.75"/><stop offset="0.4" stop-color="#60a5fa" stop-opacity="0.35"/><stop offset="1" stop-color="#6366f1" stop-opacity="0"/></linearGradient>
    <linearGradient id="bhJetDown" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a5f3fc" stop-opacity="0.75"/><stop offset="0.4" stop-color="#60a5fa" stop-opacity="0.35"/><stop offset="1" stop-color="#6366f1" stop-opacity="0"/></linearGradient>
    <linearGradient id="bhTitle" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="0.45" stop-color="#ffe2a8"/><stop offset="0.5" stop-color="#7c2d12"/><stop offset="0.56" stop-color="#ffb35c"/><stop offset="1" stop-color="#fff4dc"/></linearGradient>
    <linearGradient id="bhRule" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ff9a3c" stop-opacity="0"/><stop offset="0.5" stop-color="#ff9a3c" stop-opacity="0.55"/><stop offset="1" stop-color="#ff9a3c" stop-opacity="0"/></linearGradient>
    <filter id="bhGlow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="bhSoft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="7"/></filter>
    <clipPath id="bhType"><rect x="{HX - 340}" y="{H_ - 128}" width="680" height="22">
      <animate attributeName="width" values="0;0;680" keyTimes="0;0.3;1" dur="3s" fill="freeze"/></rect></clipPath>
  </defs>''')
    p.append('<g clip-path="url(#bhFrame)">')
    p.append(f'<rect width="{W_}" height="{H_}" fill="url(#bhSpace)"/>')

    # ---- stars, and starlight smeared into arcs near the hole
    for i in range(110):
        x, y = rnd.uniform(6, W_ - 6), rnd.uniform(6, H_ - 6)
        if math.hypot(x - HX, (y - HY) * 1.4) < 150:
            continue
        tw = (f'<animate attributeName="opacity" values="0.9;0.1;0.9" dur="{rnd.uniform(2, 6):.1f}s" '
              f'begin="{rnd.uniform(0, 5):.1f}s" repeatCount="indefinite"/>' if i % 3 == 0 else "")
        p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rnd.choice((0.45, 0.6, 0.8, 1.0))}" '
                 f'fill="{rnd.choice(("#ffffff", "#fff3d6", "#dbeafe"))}" opacity="{rnd.uniform(0.3, 0.85):.2f}">{tw}</circle>')
    for i in range(12):
        r = rnd.uniform(118, 168)
        span = rnd.uniform(14, 34)
        a0 = rnd.uniform(188, 352 - span)   # above the hole, clear of the words
        x0, y0 = HX + r * math.cos(math.radians(a0)), HY + r * math.sin(math.radians(a0))
        x1, y1 = HX + r * math.cos(math.radians(a0 + span)), HY + r * math.sin(math.radians(a0 + span))
        p.append(f'<path d="M{x0:.1f},{y0:.1f} A{r:.1f},{r:.1f} 0 0 1 {x1:.1f},{y1:.1f}" fill="none" stroke="#dbeafe" '
                 f'stroke-width="{rnd.uniform(0.5, 1.1):.2f}" stroke-linecap="round" opacity="0.35">'
                 f'{breathe("opacity", "0.45;0.08;0.45", f"{rnd.uniform(3, 7):.1f}s", f"{rnd.uniform(0, 4):.1f}s")}</path>')

    # ---- relativistic jets from the poles
    for grad, y_tip, sign in (("bhJetUp", 0, -1), ("bhJetDown", HY + 78, 1)):
        y_base = HY + sign * (RS - 6)
        p.append(f'<path d="M{HX - 5},{y_base} L{HX - 26},{y_tip} L{HX + 26},{y_tip} L{HX + 5},{y_base} Z" fill="url(#{grad})" '
                 f'filter="url(#bhGlow)">{breathe("opacity", "0.55;1;0.7;1;0.55", "2.6s")}</path>')
        for k in range(4):
            dur = rnd.uniform(1.2, 2.0)
            p.append(f'<circle cx="{HX + rnd.uniform(-4, 4):.1f}" cy="{y_base}" r="1.6" fill="#e0f2fe" opacity="0">'
                     f'<animate attributeName="cy" values="{y_base};{y_tip}" dur="{dur:.2f}s" begin="{-k * dur / 4:.2f}s" repeatCount="indefinite"/>'
                     f'<animate attributeName="opacity" values="0;1;0" dur="{dur:.2f}s" begin="{-k * dur / 4:.2f}s" repeatCount="indefinite"/></circle>')

    # ---- bloom, then the lensed halo (far side of the disk bent over the shadow)
    p.append(f'<ellipse cx="{HX}" cy="{HY}" rx="340" ry="150" fill="url(#bhBloom)"/>')
    p.append(f'<circle cx="{HX}" cy="{HY}" r="{RS + 26}" fill="none" stroke="url(#bhHalo)" stroke-width="30" opacity="0.5" filter="url(#bhSoft)"/>')
    for i in range(9):
        r = RS + 8 + i * 4.2
        per = 2 * math.pi * r
        dash = f"{rnd.uniform(10, 40):.0f} {rnd.uniform(4, 16):.0f} {rnd.uniform(2, 10):.0f} {rnd.uniform(6, 14):.0f}"
        dur = 2.2 + i * 0.55
        p.append(f'<circle cx="{HX}" cy="{HY}" r="{r:.1f}" fill="none" stroke="url(#bhHalo)" stroke-width="{3.2 - i * 0.22:.2f}" '
                 f'stroke-dasharray="{dash}" opacity="{0.95 - i * 0.07:.2f}" filter="url(#bhGlow)">'
                 f'<animate attributeName="stroke-dashoffset" values="0;{-per:.0f}" dur="{dur:.2f}s" repeatCount="indefinite"/></circle>')

    # ---- the disk: Keplerian rings, each drawn as a far half (under the shadow) and a near half (over it)
    rings = []
    for i in range(17):
        rx = 74 + i * 15.5
        ry = rx * TILT
        per = _ellipse_perim(rx, ry)
        dash = f"{rnd.uniform(18, 70):.0f} {rnd.uniform(6, 26):.0f} {rnd.uniform(4, 22):.0f} {rnd.uniform(8, 30):.0f}"
        dur = 1.4 * (rx / 74) ** 1.5           # Kepler: farther rings orbit slower
        width = max(0.8, 4.2 - i * 0.2)
        op = max(0.25, 1 - i * 0.045)
        rings.append(f'<ellipse cx="{HX}" cy="{HY}" rx="{rx:.1f}" ry="{ry:.1f}" fill="none" stroke="url(#bhDisk)" '
                     f'stroke-width="{width:.2f}" stroke-dasharray="{dash}" opacity="{op:.2f}">'
                     f'<animate attributeName="stroke-dashoffset" values="0;{-per:.0f}" dur="{dur:.2f}s" repeatCount="indefinite"/></ellipse>')
    disk_glow = (f'<ellipse cx="{HX}" cy="{HY}" rx="230" ry="{230 * TILT:.1f}" fill="none" stroke="url(#bhDisk)" '
                 f'stroke-width="44" opacity="0.28" filter="url(#bhSoft)"/>')
    p.append(f'<g clip-path="url(#bhFar)" filter="url(#bhGlow)">{disk_glow}{"".join(rings)}</g>')

    # matter spiralling in, fading at the horizon
    for k in range(26):
        a0 = rnd.uniform(0, 2 * math.pi)
        r0 = rnd.uniform(200, 330)
        turns = rnd.uniform(1.4, 2.4)
        pts = []
        for s in range(61):
            t = s / 60
            r = r0 * (1 - t) ** 1.6 + (RS + 2) * (1 - (1 - t) ** 1.6)
            a = a0 + turns * 2 * math.pi * t ** 0.8
            pts.append(f"{HX + r * math.cos(a):.1f},{HY + r * math.sin(a) * TILT:.1f}")
        dur = rnd.uniform(5, 9)
        col = rnd.choice(("#fff4dc", "#ffd27a", "#ff9a3c"))
        p.append(f'<circle r="{rnd.uniform(0.9, 1.8):.1f}" fill="{col}" opacity="0" filter="url(#bhGlow)">'
                 f'<set attributeName="opacity" to="0.9" begin="0s"/>'
                 f'<animateMotion path="M{" L".join(pts)}" dur="{dur:.2f}s" begin="{-rnd.uniform(0, dur):.2f}s" repeatCount="indefinite"/>'
                 f'</circle>')

    # ---- the shadow and its photon ring
    p.append(f'<circle cx="{HX}" cy="{HY}" r="{RS}" fill="#000"/>')
    p.append(f'<circle cx="{HX}" cy="{HY}" r="{RS + 1.6}" fill="none" stroke="#fff4dc" stroke-width="1.8" filter="url(#bhGlow)">'
             f'{breathe("opacity", "1;0.6;1", "1.6s")}</circle>')
    p.append(f'<circle cx="{HX}" cy="{HY}" r="{RS - 3}" fill="none" stroke="#ff9a3c" stroke-width="0.8" opacity="0.35"/>')
    # near halves of the disk pass in front of the shadow
    p.append(f'<g clip-path="url(#bhNear)" filter="url(#bhGlow)">{disk_glow}{"".join(rings)}</g>')

    # ---- words
    ty = H_ - 160
    p.append(f'<text x="{HX + 7}" y="{ty - 48}" text-anchor="middle" font-family="{MONO}" font-size="10" letter-spacing="7" '
             f'fill="#ffb35c" opacity="0.9">YOU HAVE REACHED THE EVENT HORIZON</text>')
    p.append(f'<text x="{HX}" y="{ty + 18}" text-anchor="middle" font-family="{SANS}" font-size="64" font-weight="900" '
             f'font-style="italic" letter-spacing="-1" fill="#ff7a1a" opacity="0.45" filter="url(#bhSoft)">LET’S BUILD</text>')
    p.append(f'<text x="{HX}" y="{ty + 18}" text-anchor="middle" font-family="{SANS}" font-size="64" font-weight="900" '
             f'font-style="italic" letter-spacing="-1" fill="url(#bhTitle)" stroke="#ffb35c" stroke-width="0.6">LET’S BUILD</text>')
    p.append(f'<g clip-path="url(#bhType)"><text x="{HX}" y="{H_ - 112}" text-anchor="middle" font-family="{MONO}" '
             f'font-size="12" letter-spacing="0.6" fill="#ffe2a8">{esc(SUBTITLE)}</text></g>')
    pills = [("COLLABORATIONS", "#ffd27a"), ("OPPORTUNITIES", "#7dd3fc"), ("AMBITIOUS BUILDS", "#ff9a3c")]
    widths = [len(t) * 7.2 + 34 for t, _ in pills]
    x = HX - (sum(widths) + 14 * 2) / 2
    py = H_ - 94
    for (label, col), w in zip(pills, widths):
        p.append(f'<rect x="{x:.1f}" y="{py}" width="{w:.1f}" height="24" rx="12" fill="#0a0508" fill-opacity="0.9"/>')
        p.append(f'<rect x="{x:.1f}" y="{py}" width="{w:.1f}" height="24" rx="12" fill="none" stroke="{col}" stroke-width="1.2" '
                 f'stroke-dasharray="7 5" filter="url(#bhGlow)"><animate attributeName="stroke-dashoffset" values="0;-24" '
                 f'dur="1.1s" repeatCount="indefinite"/></rect>')
        p.append(f'<circle cx="{x + 14:.1f}" cy="{py + 12}" r="3" fill="{col}">{breathe("opacity", "1;0.25;1", "1.4s")}</circle>')
        p.append(f'<text x="{x + 24:.1f}" y="{py + 16.2}" font-family="{MONO}" font-size="10.5" font-weight="700" '
                 f'letter-spacing="1.2" fill="{col}">{esc(label)}</text>')
        x += w + 14
    fy = H_ - 46
    p.append(f'<text x="{HX}" y="{fy}" text-anchor="middle" font-family="{MONO}" font-size="10" letter-spacing="3" '
             f'fill="#ffd27a">PICK A CHANNEL BEFORE YOU CROSS IT</text>')
    for k in range(3):
        y = fy + 8 + k * 7
        p.append(f'<polyline points="{HX - 8},{y} {HX},{y + 5} {HX + 8},{y}" fill="none" stroke="#ffd27a" stroke-width="1.7" '
                 f'stroke-linecap="round" stroke-linejoin="round" opacity="0.2">'
                 f'<animate attributeName="opacity" values="0.15;1;0.15" keyTimes="0;0.3;1" dur="1.2s" begin="{k * 0.18:.2f}s" '
                 f'repeatCount="indefinite"/></polyline>')

    # ---- HUD
    p.append(f'<text x="26" y="34" font-family="{MONO}" font-size="10" letter-spacing="1.6" fill="#ffb35c" opacity="0.85">'
             f'// SYSTEM.12 &gt; EVENT_HORIZON.EXE</text>')
    p.append(f'<circle cx="{W_ - 132}" cy="30.5" r="3.2" fill="#4ade80" filter="url(#bhGlow)">{breathe("opacity", "1;0.25;1", "1.2s")}</circle>')
    p.append(f'<text x="{W_ - 124}" y="34" font-family="{MONO}" font-size="10" font-weight="700" letter-spacing="1.6" '
             f'fill="#4ade80">CHANNEL OPEN</text>')
    p.append(f'<line x1="26" y1="{H_ - 28}" x2="{W_ - 26}" y2="{H_ - 28}" stroke="url(#bhRule)"/>')
    p.append(f'<text x="26" y="{H_ - 12}" font-family="{MONO}" font-size="9" letter-spacing="1.4" fill="#8a6a55">'
             f'// END OF README · THANKS FOR SCROLLING THIS FAR</text>')
    p.append(f'<text x="{W_ - 26}" y="{H_ - 12}" text-anchor="end" font-family="{MONO}" font-size="9" letter-spacing="1.2" '
             f'fill="#8a6a55">SYNCED {synced}</text>')
    p.append('</g>')
    p.append(f'<rect x="0.5" y="0.5" width="{W_ - 1}" height="{H_ - 1}" rx="16" fill="none" stroke="#3a1d0f"/>')
    p.append('</svg>')
    return "\n".join(p)


# ------------------------------------------------------------------ the channel buttons
def icon(kind, col):
    sw = f'fill="none" stroke="{col}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'
    if kind == "github":   # </> with a blinking slash
        return (f'<polyline points="21,21 17,26 21,31" {sw}/><polyline points="31,21 35,26 31,31" {sw}/>'
                f'<line x1="28" y1="19.5" x2="24" y2="32.5" stroke="{col}" stroke-width="1.6" stroke-linecap="round">'
                f'<animate attributeName="opacity" values="1;1;0.2;0.2" keyTimes="0;0.5;0.55;1" dur="1.1s" repeatCount="indefinite"/></line>')
    if kind == "portfolio":  # a globe with a turning meridian
        return (f'<circle cx="26" cy="26" r="8" {sw}/><line x1="18" y1="26" x2="34" y2="26" stroke="{col}" stroke-width="1.2"/>'
                f'<ellipse cx="26" cy="26" rx="3.5" ry="8" {sw}>'
                f'<animate attributeName="rx" values="0.5;7.5;0.5" dur="3s" repeatCount="indefinite"/></ellipse>')
    if kind == "linkedin":  # an "in" tile
        return (f'<rect x="18" y="18" width="16" height="16" rx="3.5" {sw}/>'
                f'<text x="26" y="30.2" text-anchor="middle" font-family="{SANS}" font-size="10" font-weight="800" fill="{col}">in</text>')
    if kind == "kovidam":  # a K in a diamond that slowly turns
        return (f'<g><animateTransform attributeName="transform" type="rotate" values="0 26 26;90 26 26;90 26 26;180 26 26" '
                f'keyTimes="0;0.25;0.75;1" dur="6s" repeatCount="indefinite"/>'
                f'<rect x="19.5" y="19.5" width="13" height="13" rx="2" transform="rotate(45 26 26)" {sw}/></g>'
                f'<text x="26" y="29.6" text-anchor="middle" font-family="{SANS}" font-size="9.5" font-weight="800" fill="{col}">K</text>')
    # email: an envelope whose flap opens
    return (f'<rect x="17.5" y="20" width="17" height="12.5" rx="2" {sw}/>'
            f'<polyline points="18,21 26,27.5 34,21" {sw}>'
            f'<animate attributeName="points" values="18,21 26,27.5 34,21;18,21 26,15.5 34,21;18,21 26,27.5 34,21" '
            f'dur="2.6s" repeatCount="indefinite"/></polyline>')


def build_button(i, kind, label, sub, col):
    bw, bh = 156, 52
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {bw} {bh}" width="{bw}" height="{bh}" role="img" '
         f'aria-label="{esc(label.title())} — {esc(sub)}">',
         f'<title>{esc(label.title())} — {esc(sub)}</title>',
         f'''<defs>
    <clipPath id="b{i}c"><rect x="1" y="1" width="{bw - 2}" height="{bh - 2}" rx="12"/></clipPath>
    <linearGradient id="b{i}t" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{col}" stop-opacity="0.2"/><stop offset="1" stop-color="{col}" stop-opacity="0.03"/></linearGradient>
    <linearGradient id="b{i}s" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff" stop-opacity="0"/><stop offset="0.5" stop-color="#ffffff" stop-opacity="0.22"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient>
    <linearGradient id="b{i}b" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{col}"/><stop offset="0.5" stop-color="#ffffff" stop-opacity="0.85"/><stop offset="1" stop-color="{col}"/></linearGradient>
    <filter id="b{i}g" x="-20%" y="-40%" width="140%" height="180%"><feGaussianBlur stdDeviation="2.4"/></filter>
  </defs>''',
         f'<rect x="1" y="1" width="{bw - 2}" height="{bh - 2}" rx="12" fill="#0b0716"/>',
         f'<rect x="1" y="1" width="{bw - 2}" height="{bh - 2}" rx="12" fill="url(#b{i}t)"/>',
         f'<g clip-path="url(#b{i}c)"><rect x="-70" y="0" width="54" height="{bh}" fill="url(#b{i}s)" transform="skewX(-22)">'
         f'<animate attributeName="x" values="-70;-70;200" keyTimes="0;0.55;1" dur="3.4s" begin="{i * 0.45:.2f}s" '
         f'repeatCount="indefinite"/></rect></g>',
         f'<rect x="1.5" y="1.5" width="{bw - 3}" height="{bh - 3}" rx="11.5" fill="none" stroke="{col}" stroke-width="2.4" '
         f'filter="url(#b{i}g)" opacity="0.5">{breathe("opacity", "0.25;0.75;0.25", f"{2.4 + i * 0.3:.1f}s")}</rect>',
         f'<rect x="1.5" y="1.5" width="{bw - 3}" height="{bh - 3}" rx="11.5" fill="none" stroke="url(#b{i}b)" stroke-width="1.2"/>',
         f'<circle cx="26" cy="26" r="15" fill="{col}" fill-opacity="0.12" stroke="{col}" stroke-opacity="0.45"/>',
         icon(kind, col),
         f'<text x="49" y="24" font-family="{MONO}" font-size="11.5" font-weight="700" letter-spacing="1.4" fill="#f5f3ff">{esc(label)}</text>',
         f'<text x="49" y="38" font-family="{MONO}" font-size="8.6" fill="{col}" opacity="0.9">{esc(sub)}</text>',
         f'<g><animateTransform attributeName="transform" type="translate" values="0,0;1.6,-1.6;0,0" dur="1.6s" '
         f'repeatCount="indefinite"/><polyline points="139,13 144,13 144,18" fill="none" stroke="{col}" stroke-width="1.4" '
         f'stroke-linecap="round" stroke-linejoin="round" opacity="0.8"/><line x1="138" y1="19" x2="144" y2="13" '
         f'stroke="{col}" stroke-width="1.4" stroke-linecap="round" opacity="0.8"/></g>',
         '</svg>']
    return "\n".join(p)


def write(path, text):
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    print(f"Wrote {path} ({len(text):,} bytes)")


def main():
    try:
        when = datetime.fromisoformat(NOW).astimezone(timezone.utc) if NOW else datetime.now(timezone.utc)
        banner = build_banner(when.strftime("%Y-%m-%d %H:%M UTC"))
        buttons = {kind: build_button(i, kind, label, sub, col) for i, (kind, label, sub, col) in enumerate(CHANNELS)}
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: could not build the contact assets: {e}. Leaving existing files untouched.", file=sys.stderr)
        return 0
    try:
        write(OUT_PATH, banner)
        for kind, svg in buttons.items():
            write(os.path.join(CHANNEL_DIR, f"{kind}.svg"), svg)
    except OSError as e:
        print(f"WARNING: could not write contact assets: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
