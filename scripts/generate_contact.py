#!/usr/bin/env python3
"""Generate the section 12 "Contact" finale:

  assets/contact-terminal.svg  — a jump to hyperspace. Star streaks rush out
                                 of a neon tunnel around "LET'S BUILD"; the
                                 last word decrypts and glitches through
                                 BUILD -> SHIP -> SCALE -> TALK, the line under
                                 it types itself out, and chevrons point down
                                 to the channel buttons.
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


# ------------------------------------------------------------------ the banner
def build_banner(synced):
    rnd = random.Random(1307)
    p = []
    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-labelledby="cTitle cDesc">')
    p.append('<title id="cTitle">Contact — let\'s build</title>')
    p.append('<desc id="cDesc">A jump to hyperspace closes the profile: star streaks rush out of a neon tunnel around '
             '"Let\'s build", whose last word decrypts and glitches through ship, scale and talk. Open to '
             'collaborations, opportunities and ambitious builds. The GitHub, Portfolio, LinkedIn, Kovidam and Email '
             'buttons directly below this image are real links.</desc>')
    p.append(f'''<defs>
    <clipPath id="cFrame"><rect x="0" y="0" width="{W}" height="{H}" rx="16"/></clipPath>
    <radialGradient id="cSpace" cx="0.5" cy="0.44" r="0.75"><stop offset="0" stop-color="#1a0b3a"/><stop offset="0.45" stop-color="#0a0418"/><stop offset="1" stop-color="#030108"/></radialGradient>
    <radialGradient id="cCore" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#ffffff" stop-opacity="0.95"/><stop offset="0.18" stop-color="#e9d5ff" stop-opacity="0.75"/><stop offset="0.5" stop-color="#8b5cf6" stop-opacity="0.25"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>
    <radialGradient id="cVignette" cx="0.5" cy="0.45" r="0.7"><stop offset="0.5" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.72"/></radialGradient>
    <radialGradient id="cHalo" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#05020c" stop-opacity="0.85"/><stop offset="0.6" stop-color="#05020c" stop-opacity="0.45"/><stop offset="1" stop-color="#05020c" stop-opacity="0"/></radialGradient>
    <linearGradient id="cChrome" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#f5fbff"/><stop offset="0.45" stop-color="#93c5fd"/><stop offset="0.5" stop-color="#1e1b4b"/>
      <stop offset="0.55" stop-color="#f0abfc"/><stop offset="1" stop-color="#fff1fb"/>
    </linearGradient>
    <linearGradient id="cRule" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#a78bfa" stop-opacity="0"/><stop offset="0.5" stop-color="#a78bfa" stop-opacity="0.6"/><stop offset="1" stop-color="#22d3ee" stop-opacity="0"/></linearGradient>
    <linearGradient id="cBand" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#05020c" stop-opacity="0"/><stop offset="0.18" stop-color="#05020c" stop-opacity="0.82"/><stop offset="0.82" stop-color="#05020c" stop-opacity="0.82"/><stop offset="1" stop-color="#05020c" stop-opacity="0"/></linearGradient>
    <filter id="cGlow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="cBloom" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="9"/></filter>
    <clipPath id="cType"><rect x="{CX - 330}" y="{CY + 52}" width="660" height="22">
      <animate attributeName="width" values="0;0;660" keyTimes="0;0.25;1" dur="2.8s" fill="freeze"/></rect></clipPath>
  </defs>''')
    p.append('<g clip-path="url(#cFrame)">')
    p.append(f'<rect width="{W}" height="{H}" fill="url(#cSpace)"/>')

    # ---- the tunnel: rings rushing past
    ring_cols = ("#8b5cf6", "#22d3ee", "#ec4899")
    for k in range(7):
        col = ring_cols[k % 3]
        begin = -k * 0.58
        p.append(f'<circle cx="{CX}" cy="{CY}" r="6" fill="none" stroke="{col}" stroke-width="0.6" opacity="0">'
                 f'<animate attributeName="r" values="6;640" dur="4.06s" begin="{begin:.2f}s" calcMode="spline" '
                 f'keyTimes="0;1" keySplines="{ACCEL}" repeatCount="indefinite"/>'
                 f'<animate attributeName="stroke-width" values="0.4;9" dur="4.06s" begin="{begin:.2f}s" calcMode="spline" '
                 f'keyTimes="0;1" keySplines="{ACCEL}" repeatCount="indefinite"/>'
                 f'<animate attributeName="opacity" values="0;0.42;0.25;0" keyTimes="0;0.2;0.7;1" dur="4.06s" '
                 f'begin="{begin:.2f}s" repeatCount="indefinite"/></circle>')

    # ---- star streaks: short dashes near the centre, scaled out past the edges, accelerating
    palette = ["#ffffff"] * 8 + ["#a5f3fc"] * 4 + ["#c4b5fd"] * 4 + ["#f0abfc"] * 3 + ["#fde68a"]
    streaks = []
    for _ in range(170):
        a = rnd.uniform(0, 2 * math.pi)
        r0 = rnd.uniform(12, 46)
        ln = rnd.uniform(2.2, 6.5)
        dur = rnd.uniform(1.2, 2.6)
        begin = -rnd.uniform(0, dur)
        c, s = math.cos(a), math.sin(a)
        streaks.append(
            f'<line x1="{r0 * c:.1f}" y1="{r0 * s:.1f}" x2="{(r0 + ln) * c:.1f}" y2="{(r0 + ln) * s:.1f}" '
            f'stroke="{rnd.choice(palette)}" stroke-width="{rnd.uniform(0.16, 0.3):.2f}" stroke-linecap="round" opacity="0.55">'
            f'<animateTransform attributeName="transform" type="scale" values="1;16" dur="{dur:.2f}s" begin="{begin:.2f}s" '
            f'calcMode="spline" keyTimes="0;1" keySplines="{ACCEL}" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="0;1;1;0.3" keyTimes="0;0.25;0.8;1" dur="{dur:.2f}s" '
            f'begin="{begin:.2f}s" repeatCount="indefinite"/></line>')
    p.append(f'<g transform="translate({CX},{CY})">{"".join(streaks)}</g>')

    # ---- the light at the end of the tunnel
    p.append(f'<circle cx="{CX}" cy="{CY}" r="92" fill="url(#cCore)">{breathe("r", "84;100;84", "2.8s")}</circle>')
    p.append(f'<rect width="{W}" height="{H}" fill="url(#cVignette)"/>')
    # a dark halo behind the words keeps them readable over the bright core
    p.append(f'<ellipse cx="{CX}" cy="{CY + 22}" rx="300" ry="86" fill="url(#cHalo)"/>')

    # ---- LET'S ...
    p.append(f'<text x="{CX + 8}" y="{CY - 42}" text-anchor="middle" font-family="{SANS}" font-size="21" font-weight="800" '
             f'letter-spacing="16" fill="#ede9fe" filter="url(#cGlow)">LET’S</text>')
    wy = CY + 38
    slot = 1.0 / len(WORDS)
    for k, word in enumerate(WORDS):
        t0 = k * slot
        on, off = t0 + 0.03, t0 + slot
        first = k == 0
        # two frames of noise, then the word lands with an RGB split
        for f, (a0, a1) in enumerate(((t0, t0 + 0.015), (t0 + 0.015, t0 + 0.03))):
            p.append(f'<text x="{CX}" y="{wy}" text-anchor="middle" font-family="{MONO}" font-size="66" font-weight="700" '
                     f'fill="{"#22d3ee" if f == 0 else "#f0abfc"}" opacity="0">{window(a0, a1)}{esc(scramble(word, rnd))}</text>')
        for dx, col in ((-5, "#22d3ee"), (5, "#ff2fd6")):
            p.append(f'<text x="{CX + dx}" y="{wy}" text-anchor="middle" font-family="{SANS}" font-size="86" '
                     f'font-weight="800" font-style="italic" letter-spacing="-1" fill="{col}" opacity="0">'
                     f'{window(on, on + 0.035)}{esc(word)}</text>')
        p.append(f'<text x="{CX}" y="{wy}" text-anchor="middle" font-family="{SANS}" font-size="86" font-weight="800" '
                 f'font-style="italic" letter-spacing="-1" fill="url(#cChrome)" stroke="#f0abfc" stroke-width="0.7" '
                 f'opacity="{1 if first else 0}">{window(on, off)}{esc(word)}</text>')
        # a soft bloom under the word while it is on screen
        p.append(f'<text x="{CX}" y="{wy}" text-anchor="middle" font-family="{SANS}" font-size="86" font-weight="800" '
                 f'font-style="italic" letter-spacing="-1" fill="#c084fc" filter="url(#cBloom)" '
                 f'opacity="{0.55 if first else 0}">'
                 f'<animate attributeName="opacity" values="0;0.55;0" keyTimes="0;{on:.4f};{min(off, 0.9999):.4f}" '
                 f'calcMode="discrete" dur="{CYCLE}s" repeatCount="indefinite"/>{esc(word)}</text>')

    # ---- the line under it types itself out
    p.append(f'<rect x="{CX - 380}" y="{CY + 52}" width="760" height="22" fill="url(#cBand)"/>')
    p.append(f'<g clip-path="url(#cType)"><text x="{CX}" y="{CY + 67}" text-anchor="middle" font-family="{MONO}" '
             f'font-size="12" letter-spacing="0.6" fill="#ddd6fe">{esc(SUBTITLE)}</text></g>')

    # ---- what the channel is open to: pills with marching neon borders
    widths = [len(t) * 7.2 + 34 for t, _ in PILLS]
    gap = 14
    x = CX - (sum(widths) + gap * (len(PILLS) - 1)) / 2
    py = CY + 84
    for (label, col), w in zip(PILLS, widths):
        p.append(f'<rect x="{x:.1f}" y="{py}" width="{w:.1f}" height="24" rx="12" fill="#07040f" fill-opacity="0.92"/>')
        p.append(f'<rect x="{x:.1f}" y="{py}" width="{w:.1f}" height="24" rx="12" fill="{col}" fill-opacity="0.1"/>')
        p.append(f'<rect x="{x:.1f}" y="{py}" width="{w:.1f}" height="24" rx="12" fill="none" stroke="{col}" '
                 f'stroke-width="1.2" stroke-dasharray="7 5" filter="url(#cGlow)">'
                 f'<animate attributeName="stroke-dashoffset" values="0;-24" dur="1.1s" repeatCount="indefinite"/></rect>')
        p.append(f'<circle cx="{x + 14:.1f}" cy="{py + 12}" r="3" fill="{col}">{breathe("opacity", "1;0.25;1", "1.4s")}</circle>')
        p.append(f'<text x="{x + 24:.1f}" y="{py + 16.2}" font-family="{MONO}" font-size="10.5" font-weight="700" '
                 f'letter-spacing="1.2" fill="{col}">{esc(label)}</text>')
        x += w + gap

    # ---- HUD
    p.append(f'<text x="26" y="34" font-family="{MONO}" font-size="10" letter-spacing="1.6" fill="#a78bfa" opacity="0.9">'
             f'// SYSTEM.12 &gt; OPEN_CHANNEL.EXE</text>')
    bx = W - 196
    for i in range(10):
        hs = ";".join(f"{rnd.uniform(2, 13):.1f}" for _ in range(6))
        p.append(f'<rect x="{bx + i * 5}" y="22" width="3" height="13" fill="#4ade80" opacity="0.75" '
                 f'transform="translate(0,35) scale(1,-1) translate(0,-22)">'
                 f'<animate attributeName="height" values="{hs};{hs.split(";")[0]}" dur="{rnd.uniform(1.1, 1.8):.2f}s" '
                 f'repeatCount="indefinite"/></rect>')
    p.append(f'<circle cx="{W - 132}" cy="30.5" r="3.2" fill="#4ade80" filter="url(#cGlow)">{breathe("opacity", "1;0.25;1", "1.2s")}</circle>')
    p.append(f'<text x="{W - 124}" y="34" font-family="{MONO}" font-size="10" font-weight="700" letter-spacing="1.6" '
             f'fill="#4ade80">CHANNEL OPEN</text>')

    # ---- down to the buttons
    fy = H - 66
    p.append(f'<rect x="{CX - 150}" y="{fy - 15}" width="300" height="52" fill="url(#cBand)"/>')
    p.append(f'<text x="{CX}" y="{fy}" text-anchor="middle" font-family="{MONO}" font-size="10" letter-spacing="3" '
             f'fill="#c4b5fd">PICK A CHANNEL</text>')
    for k in range(3):
        y = fy + 10 + k * 8
        p.append(f'<polyline points="{CX - 9},{y} {CX},{y + 6} {CX + 9},{y}" fill="none" stroke="#c4b5fd" stroke-width="1.8" '
                 f'stroke-linecap="round" stroke-linejoin="round" opacity="0.2">'
                 f'<animate attributeName="opacity" values="0.15;1;0.15" keyTimes="0;0.3;1" dur="1.2s" '
                 f'begin="{k * 0.18:.2f}s" repeatCount="indefinite"/></polyline>')
    p.append(f'<line x1="26" y1="{H - 30}" x2="{W - 26}" y2="{H - 30}" stroke="url(#cRule)"/>')
    p.append(f'<text x="26" y="{H - 13}" font-family="{MONO}" font-size="9" letter-spacing="1.4" fill="#6b5f8a">'
             f'// END OF README · THANKS FOR SCROLLING THIS FAR</text>')
    p.append(f'<text x="{W - 26}" y="{H - 13}" text-anchor="end" font-family="{MONO}" font-size="9" letter-spacing="1.2" '
             f'fill="#6b5f8a">SYNCED {synced}</text>')
    p.append('</g>')
    p.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="16" fill="none" stroke="#2a1650"/>')
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
