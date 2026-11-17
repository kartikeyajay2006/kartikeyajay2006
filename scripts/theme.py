"""One design system for every image on the profile.

Every generator draws from these tokens so the whole README reads as one piece:
the near-black ground and hairline frames of the live signal dashboard, a mono
kicker in the top-left corner ("SECTION // LIVE"), a sync stamp with a green dot
in the top-right, and one accent family -- violet, indigo, cyan, pink -- with
green kept for "this is live" and nothing else.

Domain colours are fixed so a project wears the same colour in every section:
agentic systems violet, developer tools cyan, intelligence & ML pink, products &
web indigo.
"""

# ground, panels, hairlines (from the signal dashboard)
BG = "#0a0a0a"
PANEL = "#0d0d10"
PANEL_2 = "#101014"
LINE = "#1f1f24"
LINE_2 = "#2a2a30"

# ink, brightest to faintest
INK = "#f4f4f5"
INK_2 = "#c9c9d1"
INK_3 = "#8a8a93"
INK_4 = "#5a5a63"

# accents
VIOLET = "#a78bfa"
VIOLET_DEEP = "#7c3aed"
INDIGO = "#818cf8"
CYAN = "#22d3ee"
PINK = "#f472b6"

# state -- used only for status, never as decoration
LIVE = "#22c55e"
WAKE = "#fbbf24"
DOWN = "#f87171"

DOMAIN = {
    "agentic": VIOLET,
    "tools": CYAN,
    "intel": PINK,
    "product": INDIGO,
}
DOMAIN_NAME = {
    "agentic": "AGENTIC SYSTEMS",
    "tools": "DEVELOPER TOOLS",
    "intel": "INTELLIGENCE & ML",
    "product": "PRODUCTS & WEB",
}

MONO = "ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
EASE = "0.42 0 0.58 1"


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text_w(s, size, mono=False, bold=False):
    """Rough advance width of a string, good enough to keep text inside its box."""
    return len(str(s)) * size * (0.61 if mono else (0.58 if bold else 0.53))


def fit(s, size, width, mono=False, bold=False, floor=8.5):
    while size > floor and text_w(s, size, mono, bold) > width:
        size -= 0.5
    return size


def breathe(attr, values, dur, begin="0s"):
    n = len(values.split(";"))
    kt = ";".join(f"{i / (n - 1):.3f}" for i in range(n))
    return (f'<animate attributeName="{attr}" values="{values}" keyTimes="{kt}" calcMode="spline" '
            f'keySplines="{";".join([EASE] * (n - 1))}" dur="{dur}" begin="{begin}" repeatCount="indefinite"/>')


def glow(fid, std=2.2):
    return (f'<filter id="{fid}" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="{std}" '
            f'result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')


def kicker(x, y, label, fill=INK_4, anchor="start", size=10):
    """The mono section label every panel carries, e.g. SELECTED WORK // 07 SYSTEMS."""
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{MONO}" font-size="{size}" '
            f'letter-spacing="1.2" fill="{fill}">{esc(label)}</text>')


def stamp(x, y, label, dot=True):
    """Right-aligned sync stamp with the breathing green dot."""
    out = [kicker(x - (14 if dot else 0), y, label, anchor="end")]
    if dot:
        out.append(f'<circle cx="{x - 4}" cy="{y - 3.5}" r="3" fill="{LIVE}">{breathe("opacity", "1;0.35;1", "2s")}</circle>')
    return "".join(out)


def frame(w, h, rx=14):
    """Outer panel: the same near-black card and hairline the signal dashboard uses."""
    return f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{rx}" fill="{BG}" stroke="{LINE}"/>'


def blueprint(w, h, col, fine=20, strong=100, a_fine=0.028, a_strong=0.07, x0=0, y0=0):
    """Engineering-paper grid in the accent colour."""
    g = []
    for x in range(x0 + fine, x0 + w, fine):
        g.append(f'<path d="M{x} {y0}V{y0 + h}" stroke="{col}" stroke-opacity="{a_strong if (x - x0) % strong == 0 else a_fine}"/>')
    for y in range(y0 + fine, y0 + h, fine):
        g.append(f'<path d="M{x0} {y}H{x0 + w}" stroke="{col}" stroke-opacity="{a_strong if (y - y0) % strong == 0 else a_fine}"/>')
    return "".join(g)


def fmt_bytes(b):
    if b >= 1_000_000:
        return f"{b / 1_000_000:.1f} MB"
    if b >= 1000:
        return f"{b / 1000:.0f} KB"
    return f"{b} B"


def fmt_ms(ms):
    return f"{ms / 1000:.1f} s" if ms >= 1000 else f"{ms} ms"
