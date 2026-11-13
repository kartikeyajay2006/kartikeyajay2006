#!/usr/bin/env python3
"""Generate assets/project-select.svg — the section 07 "Selected Projects"
opener: the Showroom, a turntable of holographic cards for the projects in
that section (an earlier version was a character-select screen).

  - a roster strip of the selected projects, each with its own emblem, and a
    P1 cursor that jumps from one to the next on its own;
  - for the selected one: a spotlit emblem, its name, class, a two-line
    pitch, its "signature move" (the feature its README leads with), its
    stack, and stat bars from the GitHub API — bytes of code, commits on
    the default branch, and its language mix;
  - ONLINE / WAKING / OFFLINE for the projects with a live demo, from the
    health checks this same script runs: every 3 hours GitHub Actions
    requests every deployment (and, where an app has one, its health
    endpoint) and appends the result to data/fleet-history.json.

Nothing on the screen is self-reported: every number is either from the
GitHub API or from a request the runner made. The pitch and signature move
are curated from each repository's own README.

SVG notes (see generate_signal.py): GitHub strips <script> and inline
<style>, so all motion is SMIL and nothing uses <use>/<mpath>. Without SMIL
the screen shows the first project selected.

Environment: GH_TOKEN (the same GH_CONTRIB_PAT the other workflows use) for
the repository stats; if the API is unavailable the last stats saved in
data/project-stats.json are used. FLEET_FIXTURE=<history.json> renders a saved
history without making requests; FLEET_NO_SAVE=1 checks live but leaves the
data files alone.

Never-fail contract: this script always exits 0. Any problem is logged to
stderr and files are only written after a successful render.
"""
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

LOGIN = os.environ.get("GH_LOGIN", "kartikeyajay2006")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT_PATH = os.environ.get("OUT_PATH", "assets/project-select.svg")
HISTORY_PATH = os.environ.get("HISTORY_PATH", "data/fleet-history.json")
STATS_PATH = os.environ.get("STATS_PATH", "data/project-stats.json")
FIXTURE = os.environ.get("FLEET_FIXTURE", "")
NO_SAVE = os.environ.get("FLEET_NO_SAVE", "") == "1"

TZ = timezone(timedelta(hours=5, minutes=30))
TZ_NAME = "IST"
CADENCE_H = 3
KEEP_RUNS = 240          # 30 days at one run every 3 hours
SLOW_MS = 3000
UA = "Mozilla/5.0 (compatible; fleet-status-check/1.0)"

W, H = 900, 520
MONO = "ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace"
SANS = "-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif"
EASE = "0.42 0 0.58 1"
SLOT = 3.2               # seconds each project stays selected

# Public deployments only. Two are left out on purpose until they are public
# again: Weather-App (Vercel answers with its login page) and
# ai-image-classifier (Streamlit answers with a sign-in page).
DEPLOYMENTS = [
    {"id": "kovidam", "name": "Kovidam", "url": "https://kovidam.co.in/"},
    {"id": "jky-radar", "name": "JKY-Radar", "url": "https://jky-radar.onrender.com/",
     "health": "https://jky-radar.onrender.com/api/v1/health", "sleeps": True},
    {"id": "shopkart", "name": "ShopKart", "url": "https://shopkart-black-one.vercel.app/",
     "health": "https://shopkart-black-one.vercel.app/api/health"},
    {"id": "chakraview", "name": "Chakraview", "url": "https://multi-layer-orchestation.vercel.app/"},
    {"id": "evidence", "name": "Multimodal Evidence Console", "url": "https://frontend-sigma-murex-82.vercel.app/"},
    {"id": "gitveda", "name": "GitVeda", "url": "https://git-veda-phi.vercel.app/"},
    {"id": "jky-terminal", "name": "JKY Terminal · site", "url": "https://kartikeyajay2006.github.io/jky-terminal/"},
    {"id": "agentra", "name": "Agentra", "url": "https://agentra-website-chi.vercel.app/"},
    {"id": "bloodconnect", "name": "BloodConnect", "url": "https://blood-group-donor-two.vercel.app/"},
    {"id": "club-ideas", "name": "AI-ML Club · project ideas", "url": "https://projectideas-ai-ml.vercel.app/"},
    {"id": "portfolio", "name": "Portfolio", "url": "https://kartikeya-portfolio-rx7w.vercel.app/"},
    {"id": "student-dost", "name": "Student-Dost", "url": "https://student-dost.vercel.app/"},
    {"id": "soundboard", "name": "SoundBoard", "url": "https://soundboard-six-phi.vercel.app/"},
]

W = 900
EASE = "0.42 0 0.58 1"
MONO = "ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
INK, INK2, INK3, INK4 = "#f4f4f5", "#a1a1aa", "#71717a", "#52525b"


# ------------------------------------------------------------------ checks
def fetch(url, timeout):
    """GET url following redirects. Returns (code, final_url, ms, body or None, error)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(65536)
            return resp.status, resp.geturl(), int((time.monotonic() - t0) * 1000), body, None
    except urllib.error.HTTPError as e:
        return e.code, e.geturl() if hasattr(e, "geturl") else url, int((time.monotonic() - t0) * 1000), None, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001  (timeouts, DNS, TLS, resets)
        return 0, url, int((time.monotonic() - t0) * 1000), None, type(e).__name__


def login_wall(original, final):
    """A deployment that redirects visitors to a sign-in page is not up for them."""
    o, f = urllib.parse.urlparse(original), urllib.parse.urlparse(final)
    path = (f.path + "?" + f.query).lower()
    if any(k in path for k in ("/login", "/signin", "/sign-in", "/sso", "/-/login")):
        return True
    return o.hostname != f.hostname and (f.hostname or "").endswith(("vercel.com", "streamlit.io", "share.streamlit.io"))


def read_health(body):
    """Pull api/db/version out of a JSON health payload, whatever its exact shape."""
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None
    flat = {}

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, (dict, list)):
                    walk(v)
                else:
                    flat.setdefault(k.lower(), v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    good = {"ok", "up", "pass", "passing", "healthy", "connected", "ready", "true"}
    api = None
    if "status" in flat:
        api = str(flat["status"]).lower() in good
    elif "success" in flat:
        api = flat["success"] is True
    db = None
    for k in ("db", "database", "mongo", "mongodb", "postgres"):
        if k in flat:
            db = str(flat[k]).lower() in good
            break
    ver = flat.get("engineversion") or flat.get("version")
    return {"api": api, "db": db, "ver": str(ver)[:16] if ver else None}


def check(dep):
    timeout = 90 if dep.get("sleeps") else 30
    t_start = time.monotonic()
    code, final, ms, _, err = fetch(dep["url"], timeout)
    # One quick retry so a single dropped packet does not paint a red bar. Free-tier hosts
    # that sleep can refuse requests (503) for a while as they wake, so they get patient
    # retries; when only a retry answers, the visitor would have waited that whole time.
    woke_page = False
    for wait in ((10, 20, 30) if dep.get("sleeps") else (5,)):
        if not err and 200 <= code < 400 and not login_wall(dep["url"], final):
            break
        woke_page = True
        time.sleep(wait)
        code, final, ms, _, err = fetch(dep["url"], timeout)
    out = {"code": code, "ms": ms}
    page_ok = not err and 200 <= code < 400 and not login_wall(dep["url"], final)
    if not page_ok:
        out["s"] = "down"
        out["why"] = "login wall" if (not err and login_wall(dep["url"], final)) else (err or f"HTTP {code}")
        return dep["id"], out
    out["s"] = "up" if ms < SLOW_MS else "slow"
    if woke_page and dep.get("sleeps"):
        out["s"] = "slow"
        out["ms"] = int((time.monotonic() - t_start) * 1000)
        out["why"] = "woke on retry"
    if dep.get("health"):
        # Serverless APIs can fail their first call while a cold instance connects to its
        # database. Retry once; if only the retry answers, a first visitor would have seen
        # the error, so the deployment counts as COLD rather than UP.
        woke = False
        for attempt in range(2):
            hcode, _, _, body, herr = fetch(dep["health"], timeout)
            health = read_health(body) if (body and 200 <= hcode < 300) else None
            healthy = bool(health and health["api"] is not False and health["db"] is not False)
            if healthy or attempt == 1:
                break
            woke = True
            time.sleep(5)
        out["api"] = bool(health and health["api"] is not False)
        out["db"] = None if not health else health["db"]
        if health and health.get("ver"):
            out["ver"] = health["ver"]
        if not out["api"] or out["db"] is False:
            out["s"] = "partial"
            out["why"] = herr or ("database" if out["db"] is False else "health check")
        elif woke:
            out["s"] = "slow"
            out["why"] = "API answered on retry"
    return dep["id"], out


def run_checks():
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(pool.map(check, DEPLOYMENTS))


# ------------------------------------------------------------------ history
def load_history(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        runs = data.get("runs", [])
        return runs if isinstance(runs, list) else []
    except FileNotFoundError:
        return []


def save_history(path, runs):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "cadence_hours": CADENCE_H, "runs": runs[-KEEP_RUNS:]}, f, indent=1)
        f.write("\n")


# ------------------------------------------------------------------ the roster
# Pitch and signature move are taken from each repository's own README.
ROSTER = [
    {"repo": "2nd-Year-MERN-P_S", "name": "ShopKart", "short": "SHOPKART", "icon": "bag", "color": "#4ade80",
     "cls": "E-COMMERCE · MERN", "pitch": ["A full-stack store with real orders and stock", "in MongoDB Atlas, served from Vercel."],
     "move": "Transactional cash-on-delivery checkout", "stack": ["React", "Express", "MongoDB", "Playwright"],
     "fleet": "shopkart"},
    {"repo": "codecrafters-shell-java", "name": "jsh", "short": "JSH", "icon": "terminal", "color": "#fbbf24",
     "cls": "SYSTEMS · JAVA", "pitch": ["A POSIX-style Unix shell written from", "scratch in one Java file."],
     "move": "Pipelines and background job control", "stack": ["Java", "JLine", "Maven"], "fleet": None},
    {"repo": "AI-Businesses", "name": "AI Merchant Copilot", "short": "COPILOT", "icon": "store", "color": "#f472b6",
     "cls": "AI PRODUCT · RETAIL", "pitch": ["A shop assistant for India's small merchants:", "stock, sales, a digital khata, forecasts."],
     "move": "Camera stock-in with GPT-4o-mini vision", "stack": ["React", "FastAPI", "OpenAI", "scikit-learn"],
     "fleet": None},
    {"repo": "AI-Video-Editor", "name": "AI Video Studio", "short": "VIDEO", "icon": "video", "color": "#f87171",
     "cls": "AI PRODUCT · MEDIA", "pitch": ["Upload a raw clip and get it back with styled", "captions timed to the speech."],
     "move": "Local Whisper, burned in by FFmpeg", "stack": ["Next.js", "FastAPI", "Whisper", "FFmpeg"], "fleet": None},
    {"repo": "Financial-Health-Score", "name": "Financial Health Card", "short": "FINHEALTH", "icon": "gauge",
     "color": "#22d3ee", "cls": "FINTECH · EXPLAINABLE ML",
     "pitch": ["Credit scoring for new-to-credit small", "businesses from GST, UPI and EPFO data."],
     "move": "An explainable score and a credit limit", "stack": ["React", "FastAPI", "scikit-learn", "Firebase"],
     "fleet": None},
    {"repo": "Cardano-BlockPhantom", "name": "BlockPhantom", "short": "BLOCKPHANTOM", "icon": "ghost", "color": "#a78bfa",
     "cls": "WEB3 · HACKATHON FINALIST", "pitch": ["Check a wallet before you send it money:", "a Cardano or Ethereum address in, a report out."],
     "move": "Wallet risk score and a PDF report", "stack": ["FastAPI", "React", "Blockfrost", "Alchemy"], "fleet": None},
    {"repo": "Agentra-Website", "name": "Agentra", "short": "AGENTRA", "icon": "spark", "color": "#e879f9",
     "cls": "WEB · TEAM BUILD", "pitch": ["A cinematic agency site with motion-driven", "pages and a Prisma-backed lead form."],
     "move": "An interactive 60 FPS 3D showcase", "stack": ["Next.js", "TypeScript", "Tailwind", "Prisma"],
     "fleet": "agentra"},
    {"repo": "blood-group-donor", "name": "BloodConnect", "short": "BLOODCONNECT", "icon": "drop", "color": "#fb7185",
     "cls": "SOCIAL IMPACT · WEB", "pitch": ["Find blood donors by blood group and city,", "with live stats."],
     "move": "One-tap donation requests", "stack": ["React", "Vite"], "fleet": "bloodconnect"},
    {"repo": "ai-image-classifier", "name": "AI Image Classifier", "short": "VISION", "icon": "eye", "color": "#38bdf8",
     "cls": "COMPUTER VISION", "pitch": ["Upload a JPG or PNG and get the top-3", "ImageNet predictions with confidence."],
     "move": "A MobileNetV2 verdict in about a second", "stack": ["Python", "TensorFlow", "Streamlit"], "fleet": None},
    {"repo": "project_ideas--AI-ML-CLUB", "name": "AI-ML Club Ideas", "short": "IDEAS", "icon": "bulb",
     "color": "#facc15", "cls": "COMMUNITY · AI-ML CLUB",
     "pitch": ["Six applied-AI project briefs for the club's", "Applied AI & Product Track."],
     "move": "Problem to first version to demo, six times", "stack": ["HTML", "Vercel"], "fleet": "club-ideas"},
]

STATUS = {"up": ("ONLINE", "#4ade80"), "slow": ("WAKING", "#fbbf24"), "partial": ("DEGRADED", "#fb923c"),
          "down": ("OFFLINE", "#f87171"), None: ("SOURCE", "#94a3b8")}

ICONS = {  # 24 x 24 line icons, drawn with the project's colour
    "bag": '<path d="M6 8h12l-1.2 12H7.2Z"/><path d="M9 8V6.6a3 3 0 0 1 6 0V8"/>',
    "terminal": '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/><path d="M7 10l3 2.5L7 15"/><path d="M12.5 15.5h4.5"/>',
    "store": '<path d="M4 10h16"/><path d="M5 10l1.5-5h11L19 10"/><path d="M5.5 10v9.5h13V10"/><path d="M10 19.5v-5h4v5"/>',
    "video": '<rect x="3" y="7.5" width="18" height="12.5" rx="2"/><path d="M4 7.5L7 4M9.5 7.5L12.5 4M15 7.5L18 4"/><path d="M10.5 11v6l5-3Z"/>',
    "gauge": '<path d="M4.5 17a7.5 7.5 0 1 1 15 0"/><path d="M12 17l3.8-4.6"/><path d="M7 12.5l1 .7M12 9.5v1.2M17 12.5l-1 .7"/><circle cx="12" cy="17" r="1"/>',
    "ghost": '<path d="M6.5 20V11a5.5 5.5 0 0 1 11 0v9l-1.85-1.4-1.85 1.4-1.8-1.4-1.85 1.4-1.8-1.4Z"/><circle cx="10" cy="11" r="0.9"/><circle cx="14" cy="11" r="0.9"/>',
    "spark": '<path d="M12 3l2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2Z"/>',
    "drop": '<path d="M12 3.5c3 4.2 6 7.7 6 11.2a6 6 0 0 1-12 0c0-3.5 3-7 6-11.2Z"/><path d="M9.3 15.2a2.7 2.7 0 0 0 2.7 2.6"/>',
    "eye": '<path d="M4 8V5h3M17 5h3v3M20 16v3h-3M7 19H4v-3"/><path d="M6.5 12s2-3.5 5.5-3.5 5.5 3.5 5.5 3.5-2 3.5-5.5 3.5S6.5 12 6.5 12Z"/><circle cx="12" cy="12" r="1.5"/>',
    "bulb": '<path d="M9.5 17.5h5M10.3 20.5h3.4"/><path d="M12 3.5a5.5 5.5 0 0 0-3.2 10c.7.6 1.2 1.5 1.2 2.4v1.6h4v-1.6c0-.9.5-1.8 1.2-2.4A5.5 5.5 0 0 0 12 3.5Z"/>',
}

STATS_Q = """{ %s }
fragment F on Repository {
  languages(first: 3, orderBy: {field: SIZE, direction: DESC}) { totalSize edges { size node { name color } } }
  defaultBranchRef { target { ... on Commit { history { totalCount } } } }
}"""


def fetch_stats():
    """Code size, commits and top languages per roster repo; cached so a run without a
    token (or with the API down) still draws the last known numbers."""
    cached = {}
    try:
        with open(STATS_PATH, encoding="utf-8") as f:
            cached = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    if not TOKEN or FIXTURE:
        return cached, False
    fields = " ".join(f'r{i}: repository(owner: "{LOGIN}", name: "{p["repo"]}") {{ ...F }}' for i, p in enumerate(ROSTER))
    body = json.dumps({"query": STATS_Q % fields}).encode("utf-8")
    req = urllib.request.Request("https://api.github.com/graphql", data=body, method="POST",
                                 headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json",
                                          "User-Agent": f"{LOGIN}-project-select"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8")).get("data") or {}
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: repository stats unavailable, using the cached ones: {e}", file=sys.stderr)
        return cached, False
    out = {}
    for i, proj in enumerate(ROSTER):
        node = data.get(f"r{i}")
        if not node:
            if proj["repo"] in cached:
                out[proj["repo"]] = cached[proj["repo"]]
            continue
        langs = node.get("languages") or {}
        hist = (((node.get("defaultBranchRef") or {}).get("target") or {}).get("history") or {})
        out[proj["repo"]] = {
            "bytes": langs.get("totalSize", 0),
            "commits": hist.get("totalCount", 0),
            "langs": [[e["node"]["name"], e["size"], e["node"]["color"] or "#8b949e"] for e in langs.get("edges") or []],
        }
    return out, True


# ------------------------------------------------------------------ helpers
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def breathe(attr, values, dur, begin="0s"):
    n = len(values.split(";"))
    kt = ";".join(f"{i / (n - 1):.3f}" for i in range(n))
    return (f'<animate attributeName="{attr}" values="{values}" keyTimes="{kt}" calcMode="spline" '
            f'keySplines="{";".join([EASE] * (n - 1))}" dur="{dur}" begin="{begin}" repeatCount="indefinite"/>')


def fmt_ms(ms):
    return f"{ms / 1000:.1f} s" if ms >= 1000 else f"{ms} ms"


def fmt_bytes(b):
    if b >= 1_000_000:
        return f"{b / 1_000_000:.1f} MB"
    if b >= 1000:
        return f"{b / 1000:.0f} KB"
    return f"{b} B"


def emblem(kind, col, cx, cy, size, sw):
    s = size / 24
    return (f'<g transform="translate({cx - size / 2:.1f},{cy - size / 2:.1f}) scale({s:.4f})" fill="none" '
            f'stroke="{col}" stroke-width="{sw / s:.3f}" stroke-linecap="round" stroke-linejoin="round">'
            f'{ICONS[kind]}</g>')



# ------------------------------------------------------------------ render: the showroom
# The roster stands on a turntable. Every STEP seconds it turns one place and
# the next project glides to the front: cards are placed on a tilted ellipse,
# shrink and dim with depth, and are drawn in depth bands (one copy per band,
# shown only while the card is in that band) so nearer cards always cover
# farther ones without any scripting.
HOLD, MOVE = 2.3, 0.8
STEP = HOLD + MOVE
TCX, TCY, TRX, TRY = 450, 262, 352, 52
CARD_W, CARD_H = 200, 268
BANDS = [(-1.01, -0.3), (-0.3, 0.42), (0.42, 0.96), (0.96, 1.01)]


def _ring_track(steps=1440):
    pts, cum = [], [0.0]
    for i in range(steps + 1):
        t = 4 * math.pi * i / steps               # two laps, so a card's path never wraps
        pts.append((TCX + TRX * math.cos(t), TCY + TRY * math.sin(t)))
        if i:
            cum.append(cum[-1] + math.dist(pts[-1], pts[-2]))
    return pts, cum


def _at(pts, cum, f):
    target = f * cum[-1]
    lo, hi = 0, len(cum) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    i = max(1, lo)
    seg = cum[i] - cum[i - 1] or 1.0
    k = (target - cum[i - 1]) / seg
    (x0, y0), (x1, y1) = pts[i - 1], pts[i]
    return x0 + (x1 - x0) * k, y0 + (y1 - y0) * k


def _wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    return lines + [cur]


def card_body(k, proj, st, r, n):
    col = proj["color"]
    w, h = CARD_W, CARD_H
    x0, y0 = -w / 2, -h / 2
    label, scol = STATUS[r["s"] if r else None]
    ping = f' · {fmt_ms(r["ms"])}' if r and r["s"] in ("up", "slow") else ""
    b = [f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" rx="18" fill="url(#shGlass)"/>',
         f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" rx="18" fill="{col}" fill-opacity="0.09"/>',
         f'<rect x="{x0 + 0.6}" y="{y0 + 0.6}" width="{w - 1.2}" height="{h - 1.2}" rx="17.5" fill="none" stroke="{col}" '
         f'stroke-opacity="0.75" stroke-width="1.3"/>',
         f'<rect x="{x0 + 24}" y="{y0}" width="64" height="2" rx="1" fill="{col}"/>',
         f'<text x="{x0 + 16}" y="{y0 + 24}" font-family="{MONO}" font-size="9" letter-spacing="1.2" fill="{col}">'
         f'{k + 1:02d} / {n:02d}</text>',
         f'<circle cx="0" cy="{y0 + 70}" r="34" fill="{col}" fill-opacity="0.12" stroke="{col}" stroke-opacity="0.55"/>',
         f'<circle cx="0" cy="{y0 + 70}" r="44" fill="none" stroke="{col}" stroke-opacity="0.2" stroke-dasharray="2 5"/>',
         emblem(proj["icon"], col, 0, y0 + 70, 38, 2.1),
         f'<text x="0" y="{y0 + 134}" text-anchor="middle" font-family="{SANS}" font-size="17" font-weight="800" '
         f'fill="#ffffff">{esc(proj["name"])}</text>',
         f'<text x="0" y="{y0 + 150}" text-anchor="middle" font-family="{MONO}" font-size="7.8" letter-spacing="1" '
         f'fill="{col}">{esc(proj["cls"])}</text>']
    for m, line in enumerate(_wrap(proj["move"], 30)[:2]):
        b.append(f'<text x="0" y="{y0 + 174 + m * 15}" text-anchor="middle" font-family="{SANS}" font-size="11.5" '
                 f'font-weight="600" fill="#e4e4e7">{esc(line)}</text>')
    if st:
        b.append(f'<text x="0" y="{y0 + 214}" text-anchor="middle" font-family="{MONO}" font-size="9" fill="#a1a1aa">'
                 f'{fmt_bytes(st.get("bytes", 0))} · {st.get("commits", 0)} COMMITS</text>')
        langs = st.get("langs") or []
        tot = sum(s for _, s, _ in langs) or 1
        lx = -66
        for _, size, lc in langs:
            seg = 132 * size / tot
            b.append(f'<rect x="{lx:.1f}" y="{y0 + 222}" width="{max(seg - 1.2, 1.2):.1f}" height="4" rx="2" fill="{lc}"/>')
            lx += seg
    cw = len(label + ping) * 6.4 + 26
    b.append(f'<rect x="{-cw / 2:.1f}" y="{y0 + 236}" width="{cw:.1f}" height="19" rx="9.5" fill="{scol}" fill-opacity="0.12" '
             f'stroke="{scol}" stroke-opacity="0.6"/>')
    b.append(f'<circle cx="{-cw / 2 + 11:.1f}" cy="{y0 + 245.5}" r="2.8" fill="{scol}"/>')
    b.append(f'<text x="{-cw / 2 + 19:.1f}" y="{y0 + 249}" font-family="{MONO}" font-size="9" font-weight="700" '
             f'letter-spacing="0.8" fill="{scol}">{label}{esc(ping)}</text>')
    return "".join(b)


def build(runs, stats):
    latest = runs[-1] if runs else {"results": {}, "at": None}
    res = latest.get("results", {})
    last_at = (datetime.fromisoformat(latest["at"].replace("Z", "+00:00")).astimezone(TZ)
               if latest.get("at") else None)
    n = len(ROSTER)
    T = n * STEP
    online = sum(1 for p in ROSTER if p["fleet"] and res.get(p["fleet"], {}).get("s") in ("up", "slow"))
    deployed = sum(1 for p in ROSTER if p["fleet"])
    pts, cum = _ring_track()
    L2 = cum[-1]
    front = 0.25 / 2                                # bottom of the ellipse on the two-lap track
    # one keyframe per hold/move edge, plus samples inside each move for depth
    times, progress = [], []
    for k in range(n):
        t0 = k * STEP
        times += [t0, t0 + HOLD]
        progress += [k / n, k / n]
        for s in range(1, 8):
            times.append(t0 + HOLD + MOVE * s / 8)
            progress.append((k + s / 8) / n)
    times.append(T)
    progress.append(1.0)
    kt = ";".join(f"{t / T:.5f}" for t in times)

    rows = []
    for proj in ROSTER:
        st = stats.get(proj["repo"], {})
        r = res.get(proj["fleet"]) if proj["fleet"] else None
        status = STATUS[r["s"] if r else None][0].lower()
        rows.append(f'{proj["name"]} ({proj["cls"].title()}): {proj["move"]}'
                    + (f', {fmt_bytes(st.get("bytes", 0))} of code, {st.get("commits", 0)} commits' if st else "")
                    + f", {status}" + (f' in {fmt_ms(r["ms"])}' if r and r["s"] in ("up", "slow") else ""))

    H = 540
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" aria-labelledby="shTitle shDesc">',
         '<title id="shTitle">The showroom — selected works on a turntable</title>',
         f'<desc id="shDesc">Ten selected projects stand as holographic cards on a turntable that turns every {STEP:.0f} '
         f'seconds, bringing each one to the front under a spotlight: its emblem, class, signature move, code size, commits '
         f'and languages from the GitHub API, and, for the {deployed} with a live demo, whether its last health check '
         f'found it online. {esc("; ".join(rows))}.</desc>',
         f'''<defs>
    <clipPath id="shFrame"><rect width="{W}" height="{H}" rx="16"/></clipPath>
    <radialGradient id="shBg" cx="0.5" cy="0.35" r="0.85"><stop offset="0" stop-color="#1d0d3a"/><stop offset="0.5" stop-color="#0b0618"/><stop offset="1" stop-color="#050309"/></radialGradient>
    <linearGradient id="shGlass" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1a1230"/><stop offset="1" stop-color="#0a0614"/></linearGradient>
    <linearGradient id="shChrome" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="0.46" stop-color="#c4b5fd"/><stop offset="0.5" stop-color="#312e81"/><stop offset="0.55" stop-color="#f0abfc"/><stop offset="1" stop-color="#fdf4ff"/></linearGradient>
    <radialGradient id="shStage" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#a78bfa" stop-opacity="0.35"/><stop offset="0.6" stop-color="#7c3aed" stop-opacity="0.12"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>
    <linearGradient id="shBeam" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e9d5ff" stop-opacity="0.32"/><stop offset="1" stop-color="#e9d5ff" stop-opacity="0"/></linearGradient>
    <linearGradient id="shSheen" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff" stop-opacity="0"/><stop offset="0.5" stop-color="#ffffff" stop-opacity="0.2"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient>
    <clipPath id="shCardClip"><rect x="{-CARD_W / 2}" y="{-CARD_H / 2}" width="{CARD_W}" height="{CARD_H}" rx="18"/></clipPath>
    <filter id="shGlow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="shBlur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="14"/></filter>
  </defs>''',
         '<g clip-path="url(#shFrame)">',
         f'<rect width="{W}" height="{H}" fill="url(#shBg)"/>']
    rnd = random.Random(70)
    for i in range(70):
        x, y = rnd.uniform(8, W - 8), rnd.uniform(8, 300)
        tw = (f'<animate attributeName="opacity" values="0.8;0.1;0.8" dur="{rnd.uniform(2, 5):.1f}s" '
              f'begin="{rnd.uniform(0, 4):.1f}s" repeatCount="indefinite"/>' if i % 3 == 0 else "")
        p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rnd.choice((0.5, 0.7, 0.9))}" fill="#e9d5ff" '
                 f'opacity="{rnd.uniform(0.25, 0.7):.2f}">{tw}</circle>')
    # spotlight from above onto the front of the stage
    p.append(f'<path d="M{TCX - 40},0 L{TCX + 40},0 L{TCX + 170},{TCY + TRY + 150} L{TCX - 170},{TCY + TRY + 150} Z" '
             f'fill="url(#shBeam)">{breathe("opacity", "0.75;1;0.75", "4s")}</path>')
    # the turntable: glowing floor, rings and a rotating dashed rim
    sy = TCY + 128
    p.append(f'<ellipse cx="{TCX}" cy="{sy}" rx="{TRX + 110}" ry="{TRY + 34}" fill="url(#shStage)"/>')
    for k, (dr, op) in enumerate(((0, 0.55), (40, 0.3), (80, 0.16))):
        p.append(f'<ellipse cx="{TCX}" cy="{sy}" rx="{TRX + 30 + dr}" ry="{TRY + 8 + dr * 0.18:.1f}" fill="none" '
                 f'stroke="#c084fc" stroke-opacity="{op}" stroke-width="1.2"/>')
    p.append(f'<ellipse cx="{TCX}" cy="{sy}" rx="{TRX + 30}" ry="{TRY + 8}" fill="none" stroke="#f0abfc" stroke-width="2.2" '
             f'stroke-dasharray="26 18" filter="url(#shGlow)" opacity="0.8">'
             f'<animate attributeName="stroke-dashoffset" values="0;-440" dur="{T / 2:.0f}s" repeatCount="indefinite"/></ellipse>')

    # ---- cards, one copy per depth band
    layers = [[] for _ in BANDS]
    for k, proj in enumerate(ROSTER):
        st = stats.get(proj["repo"], {})
        r = res.get(proj["fleet"]) if proj["fleet"] else None
        base = (front - k / (2 * n)) % 0.5            # where this card sits at time 0, on the first lap
        keypts = [base + pr / 2 for pr in progress]
        xy = [_at(pts, cum, f) for f in keypts]
        depth = [(y - TCY) / TRY for _, y in xy]
        x0, y0 = xy[0]
        rel = ";".join(f"{px - x0:.1f},{py - y0:.1f}" for px, py in xy)
        scale_vals = ";".join(f"{0.4 + 0.6 * ((d + 1) / 2) ** 3.2:.3f}" for d in depth)
        dim_vals = ";".join(f"{0.72 * (1 - ((d + 1) / 2) ** 2.5):.3f}" for d in depth)
        body = card_body(k, proj, st, r, n)
        for bi, (lo, hi) in enumerate(BANDS):
            vis = ";".join("1" if lo <= d < hi else "0" for d in depth)
            base_vis = 1 if lo <= depth[0] < hi else 0
            extra = ""
            if bi == len(BANDS) - 1:   # the card in front gets the holographic sheen and a halo
                extra = (f'<g clip-path="url(#shCardClip)"><rect x="-200" y="{-CARD_H / 2}" width="90" height="{CARD_H}" '
                         f'fill="url(#shSheen)" transform="skewX(-18)"><animate attributeName="x" values="-260;-260;220" '
                         f'keyTimes="0;0.4;1" dur="{STEP}s" repeatCount="indefinite"/></rect></g>')
                halo = (f'<rect x="{-CARD_W / 2 - 6}" y="{-CARD_H / 2 - 6}" width="{CARD_W + 12}" height="{CARD_H + 12}" rx="22" '
                        f'fill="{proj["color"]}" opacity="0.3" filter="url(#shBlur)"/>')
            else:
                halo = ""
            layers[bi].append(
                f'<g transform="translate({x0:.1f},{y0:.1f})" opacity="{base_vis}">'
                f'<animate attributeName="opacity" values="{vis}" keyTimes="{kt}" calcMode="discrete" dur="{T}s" repeatCount="indefinite"/>'
                f'<animateMotion values="{rel}" keyTimes="{kt}" calcMode="linear" dur="{T}s" repeatCount="indefinite"/>'
                f'<g transform="scale({scale_vals.split(";")[0]})">'
                f'<animateTransform attributeName="transform" type="scale" values="{scale_vals}" keyTimes="{kt}" dur="{T}s" repeatCount="indefinite"/>'
                f'{halo}{body}{extra}'
                f'<rect x="{-CARD_W / 2}" y="{-CARD_H / 2}" width="{CARD_W}" height="{CARD_H}" rx="18" fill="#05030a" '
                f'opacity="{dim_vals.split(";")[0]}"><animate attributeName="opacity" values="{dim_vals}" keyTimes="{kt}" '
                f'dur="{T}s" repeatCount="indefinite"/></rect></g></g>')
    for layer in layers:
        p.append("".join(layer))

    # ---- title and readouts
    p.append(f'<text x="28" y="36" font-family="{MONO}" font-size="10" letter-spacing="1.8" fill="#a78bfa">SYSTEM // 07 · THE SHOWROOM</text>')
    p.append(f'<text x="26" y="74" font-family="{SANS}" font-size="38" font-weight="900" font-style="italic" letter-spacing="-0.6" '
             f'fill="url(#shChrome)" stroke="#f0abfc" stroke-width="0.6">SELECTED WORKS</text>')
    p.append(f'<text x="28" y="94" font-family="{MONO}" font-size="9.5" letter-spacing="1.2" fill="#8b7fb8">'
             f'{n} PROJECTS ON THE TURNTABLE · ONE TURN EVERY {STEP:.0f} S</text>')
    bx = W - 236
    p.append(f'<rect x="{bx}" y="22" width="210" height="58" rx="12" fill="#0b0716" fill-opacity="0.85" stroke="#2e1f4f"/>')
    p.append(f'<text x="{bx + 16}" y="42" font-family="{MONO}" font-size="8.5" letter-spacing="1.3" fill="#8b7fb8">ONLINE</text>')
    p.append(f'<circle cx="{bx + 66}" cy="39" r="3" fill="#4ade80" filter="url(#shGlow)">{breathe("opacity", "1;0.25;1", "1.2s")}</circle>')
    p.append(f'<text x="{bx + 16}" y="68" font-family="{SANS}" font-size="22" font-weight="800" fill="#4ade80">{online}'
             f'<tspan font-size="12" fill="#6b7280">/{deployed} live demos</tspan></text>')
    p.append(f'<text x="{bx + 194}" y="42" text-anchor="end" font-family="{MONO}" font-size="8.5" letter-spacing="1.3" fill="#8b7fb8">CHECKED</text>')
    p.append(f'<text x="{bx + 194}" y="68" text-anchor="end" font-family="{SANS}" font-size="17" font-weight="800" fill="#c4b5fd">'
             f'{last_at.strftime("%H:%M") if last_at else "--:--"}<tspan font-family="{MONO}" font-size="8" font-weight="400" '
             f'fill="#8b7fb8"> {TZ_NAME}</tspan></text>')
    p.append(f'<text x="{W / 2}" y="{H - 16}" text-anchor="middle" font-family="{MONO}" font-size="8.8" letter-spacing="1.1" '
             f'fill="#8b7fb8">STATS FROM THE GITHUB API · <tspan fill="#4ade80">●</tspan> ONLINE = PASSED ITS LAST HEALTH CHECK '
             f'(EVERY {CADENCE_H} H) · FULL DETAILS IN THE TABLE BELOW</text>')
    p.append('</g>')
    p.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="16" fill="none" stroke="#2a1650"/>')
    p.append('</svg>')
    return "\n".join(p)


def main():
    try:
        if FIXTURE:
            runs = load_history(FIXTURE)
        else:
            runs = load_history(HISTORY_PATH)
            results = run_checks()
            runs.append({"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "results": results})
            runs = runs[-KEEP_RUNS:]
            for dep_id, r in results.items():
                print(f"  {dep_id:14s} {r['s']:8s} {r.get('code')} {r.get('ms')} ms {r.get('why', '')}")
        stats, fresh = fetch_stats()
        svg = build(runs, stats)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: project select failed, leaving existing files untouched: {e}", file=sys.stderr)
        return 0
    try:
        os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            f.write(svg)
        if not FIXTURE and not NO_SAVE:
            save_history(HISTORY_PATH, runs)
            if fresh:
                with open(STATS_PATH, "w", encoding="utf-8") as f:
                    json.dump(stats, f, indent=1, sort_keys=True)
                    f.write("\n")
        print(f"Wrote {OUT_PATH}")
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: failed to write output files: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
