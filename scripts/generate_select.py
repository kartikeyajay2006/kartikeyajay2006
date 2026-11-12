#!/usr/bin/env python3
"""Generate assets/project-select.svg — the section 07 "Selected Projects"
opener: a video-game character-select screen for the projects in that
section.

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


def turn(k, n, offsets, values, final, T, attr=None, kind=None):
    """An effect that plays at the start of project k's turn, every cycle: values[i] lands
    offsets[i] (as a share of one turn) into the turn, then holds at final until next time."""
    s0, f = k / n, 1 / n
    kts = [s0 + o * f for o in offsets]
    if k == 0:
        kt, vals = kts + [1], values + [final]
    else:
        kt, vals = [0] + kts + [1], [final] + values + [final]
    kt_s = ";".join(f"{t:.4f}" for t in kt)
    if kind:
        return (f'<animateTransform attributeName="transform" type="{kind}" additive="sum" values="{";".join(vals)}" '
                f'keyTimes="{kt_s}" dur="{T}s" repeatCount="indefinite"/>')
    return f'<animate attributeName="{attr}" values="{";".join(vals)}" keyTimes="{kt_s}" dur="{T}s" repeatCount="indefinite"/>'


# ------------------------------------------------------------------ render
def build(runs, stats):
    latest = runs[-1] if runs else {"results": {}, "at": None}
    res = latest.get("results", {})
    last_at = (datetime.fromisoformat(latest["at"].replace("Z", "+00:00")).astimezone(TZ)
               if latest.get("at") else None)
    n = len(ROSTER)
    T = n * SLOT
    online = sum(1 for p in ROSTER if p["fleet"] and res.get(p["fleet"], {}).get("s") in ("up", "slow"))
    deployed = sum(1 for p in ROSTER if p["fleet"])
    max_bytes = max([stats.get(p["repo"], {}).get("bytes", 0) for p in ROSTER] + [1])
    max_commits = max([stats.get(p["repo"], {}).get("commits", 0) for p in ROSTER] + [1])
    p = []

    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-labelledby="selTitle selDesc">')
    p.append('<title id="selTitle">Select your project</title>')
    rows = []
    for proj in ROSTER:
        st = stats.get(proj["repo"], {})
        r = res.get(proj["fleet"]) if proj["fleet"] else None
        status = STATUS[r["s"] if r else None][0]
        bits = [f'{proj["name"]} ({proj["cls"].title()}): {proj["move"]}']
        if st:
            bits.append(f'{fmt_bytes(st.get("bytes", 0))} of code, {st.get("commits", 0)} commits')
        bits.append(status.lower() + (f' in {fmt_ms(r["ms"])}' if r and r["s"] in ("up", "slow") else ""))
        rows.append(", ".join(bits))
    p.append(f'<desc id="selDesc">A video-game character-select screen for {n} selected projects. A cursor moves '
             f'through the roster and each project in turn shows its emblem, class, pitch, signature move, stack, code '
             f'size, commits and languages from the GitHub API, and, for the {deployed} with a live demo, whether its '
             f'last health check found it online. {esc("; ".join(rows))}.</desc>')

    p.append(f'''<defs>
    <clipPath id="selFrame"><rect width="{W}" height="{H}" rx="16"/></clipPath>
    <linearGradient id="selBg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b0618"/><stop offset="0.55" stop-color="#070411"/><stop offset="1" stop-color="#120624"/></linearGradient>
    <linearGradient id="selTitleInk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="0.48" stop-color="#fde68a"/><stop offset="0.52" stop-color="#f97316"/><stop offset="1" stop-color="#fef3c7"/></linearGradient>
    <linearGradient id="selStripe" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#a78bfa" stop-opacity="0"/><stop offset="0.5" stop-color="#a78bfa" stop-opacity="0.07"/><stop offset="1" stop-color="#a78bfa" stop-opacity="0"/></linearGradient>
    <radialGradient id="selSpot" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#ffffff" stop-opacity="0.16"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></radialGradient>
    <linearGradient id="selShine" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff" stop-opacity="0"/><stop offset="0.5" stop-color="#ffffff" stop-opacity="0.35"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient>
    <filter id="selGlow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="selBlur" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="16"/></filter>
    <pattern id="selHex" width="22" height="38" patternUnits="userSpaceOnUse"><path d="M11 0 L22 6.3 L22 19 L11 25.3 L0 19 L0 6.3 Z M11 25.3 L11 38" fill="none" stroke="#a78bfa" stroke-opacity="0.07"/></pattern>
  </defs>''')
    p.append('<g clip-path="url(#selFrame)">')
    p.append(f'<rect width="{W}" height="{H}" fill="url(#selBg)"/>')
    p.append(f'<rect width="{W}" height="{H}" fill="url(#selHex)"/>')
    # diagonal speed bands drifting across the arena
    for i in range(6):
        x = -300 + i * 220
        p.append(f'<rect x="{x}" y="-60" width="70" height="{H + 120}" fill="url(#selStripe)" transform="skewX(-24)">'
                 f'<animate attributeName="x" values="{x};{x + 220}" dur="7s" repeatCount="indefinite"/></rect>')

    # ---- title bar
    p.append(f'<text x="28" y="34" font-family="{MONO}" font-size="10" letter-spacing="1.8" fill="#a78bfa">'
             f'SYSTEM // 07 · PLAYER 1</text>')
    p.append(f'<text x="26" y="78" font-family="{SANS}" font-size="44" font-weight="900" font-style="italic" '
             f'letter-spacing="-0.5" fill="url(#selTitleInk)" stroke="#7c2d12" stroke-width="1" '
             f'paint-order="stroke">SELECT YOUR PROJECT</text>')
    p.append(f'<rect x="{W - 252}" y="20" width="226" height="58" rx="10" fill="#0b0716" stroke="#2e1f4f"/>')
    p.append(f'<text x="{W - 238}" y="40" font-family="{MONO}" font-size="9" letter-spacing="1.4" fill="#8b7fb8">ROSTER</text>')
    p.append(f'<text x="{W - 238}" y="66" font-family="{SANS}" font-size="24" font-weight="800" fill="#f5f3ff">{n}</text>')
    p.append(f'<text x="{W - 160}" y="40" font-family="{MONO}" font-size="9" letter-spacing="1.4" fill="#8b7fb8">ONLINE</text>')
    p.append(f'<text x="{W - 160}" y="66" font-family="{SANS}" font-size="24" font-weight="800" fill="#4ade80">'
             f'{online}<tspan font-size="13" fill="#6b7280">/{deployed}</tspan></text>')
    p.append(f'<circle cx="{W - 112}" cy="36.5" r="3.2" fill="#4ade80" filter="url(#selGlow)">{breathe("opacity", "1;0.25;1", "1.2s")}</circle>')
    p.append(f'<text x="{W - 96}" y="40" font-family="{MONO}" font-size="9" letter-spacing="1.4" fill="#8b7fb8">CHECKED</text>')
    p.append(f'<text x="{W - 96}" y="66" font-family="{SANS}" font-size="17" font-weight="800" fill="#c4b5fd">'
             f'{last_at.strftime("%H:%M") if last_at else "--:--"}<tspan font-family="{MONO}" font-size="8.5" '
             f'font-weight="400" fill="#8b7fb8"> {TZ_NAME}</tspan></text>')

    # ---- portrait stage (left) and the stats board (right)
    sx, sy, sw_, sh = 24, 96, 300, 272
    p.append(f'<rect x="{sx}" y="{sy}" width="{sw_}" height="{sh}" rx="18" fill="#0b0716" stroke="#2e1f4f"/>')
    p.append(f'<rect x="344" y="{sy}" width="{W - 368}" height="{sh}" rx="18" fill="#0b0716" fill-opacity="0.82" stroke="#2e1f4f"/>')
    pcx, pcy = sx + sw_ / 2, sy + 124
    # rotating rings behind every portrait
    p.append(f'<g><animateTransform attributeName="transform" type="rotate" from="0 {pcx} {pcy}" to="360 {pcx} {pcy}" '
             f'dur="16s" repeatCount="indefinite"/><circle cx="{pcx}" cy="{pcy}" r="92" fill="none" stroke="#a78bfa" '
             f'stroke-opacity="0.35" stroke-dasharray="3 9"/></g>')
    p.append(f'<g><animateTransform attributeName="transform" type="rotate" from="360 {pcx} {pcy}" to="0 {pcx} {pcy}" '
             f'dur="11s" repeatCount="indefinite"/><circle cx="{pcx}" cy="{pcy}" r="76" fill="none" stroke="#e9d5ff" '
             f'stroke-opacity="0.25" stroke-dasharray="40 14 6 14"/></g>')

    tile_w, tile_h, gap = 78, 74, 6.2
    rx0 = (W - (n * tile_w + (n - 1) * gap)) / 2
    ry0 = 392

    for k, proj in enumerate(ROSTER):
        col = proj["color"]
        s0, s1 = k / n, (k + 1) / n
        first = k == 0
        if first:
            vis = f'<animate attributeName="opacity" values="1;0" keyTimes="0;{s1:.4f}" calcMode="discrete" dur="{T}s" repeatCount="indefinite"/>'
        elif k == n - 1:
            vis = f'<animate attributeName="opacity" values="0;1" keyTimes="0;{s0:.4f}" calcMode="discrete" dur="{T}s" repeatCount="indefinite"/>'
        else:
            vis = (f'<animate attributeName="opacity" values="0;1;0" keyTimes="0;{s0:.4f};{s1:.4f}" calcMode="discrete" '
                   f'dur="{T}s" repeatCount="indefinite"/>')

        st = stats.get(proj["repo"], {})
        r = res.get(proj["fleet"]) if proj["fleet"] else None
        label, scol = STATUS[r["s"] if r else None]

        g = [f'<g opacity="{1 if first else 0}">{vis}']
        # spotlight and emblem
        g.append(f'<circle cx="{pcx}" cy="{pcy}" r="88" fill="{col}" opacity="0.22" filter="url(#selBlur)"/>')
        g.append(f'<circle cx="{pcx}" cy="{pcy}" r="58" fill="url(#selSpot)"/>')
        g.append(f'<circle cx="{pcx}" cy="{pcy}" r="58" fill="none" stroke="{col}" stroke-width="2" opacity="0.8" filter="url(#selGlow)"/>')
        sc = [0.55, 1.12, 1.0]
        offs = [0.0, 0.06, 0.1]
        g.append('<g>' + turn(k, n, offs, [f"{pcx * (1 - v):.1f},{pcy * (1 - v):.1f}" for v in sc], "0,0", T, kind="translate")
                 + turn(k, n, offs, [f"{v}" for v in sc], "1", T, kind="scale")
                 + emblem(proj["icon"], col, pcx, pcy, 84, 2.7) + '</g>')
        g.insert(1, f'<text x="{sx + 16}" y="{sy + 70}" font-family="{SANS}" font-size="72" font-weight="900" '
                    f'font-style="italic" fill="none" stroke="{col}" stroke-width="1.4" opacity="0.32">{k + 1:02d}</text>')
        g.append(f'<text x="{pcx}" y="{sy + sh - 44}" text-anchor="middle" font-family="{SANS}" font-size="12" '
                 f'font-weight="800" letter-spacing="3" fill="{col}">{esc(proj["short"])}</text>')
        g.append(f'<text x="{pcx}" y="{sy + sh - 24}" text-anchor="middle" font-family="{MONO}" font-size="9" '
                 f'letter-spacing="1.2" fill="#8b7fb8">{k + 1:02d} / {n:02d}</text>')
        # a white flash as the pick lands
        g.append(f'<rect x="{sx}" y="{sy}" width="{sw_}" height="{sh}" rx="18" fill="#ffffff" opacity="0">'
                 + turn(k, n, [0.0, 0.11], ["0.55", "0"], "0", T, attr="opacity") + '</rect>')

        # stats board
        bx = 368
        g.append(f'<text x="{bx}" y="{sy + 28}" font-family="{MONO}" font-size="10" letter-spacing="1.6" fill="{col}">'
                 f'{esc(proj["cls"])}</text>')
        ping = f' · {fmt_ms(r["ms"])}' if r and r["s"] in ("up", "slow") else ""
        sw_w = len(label + ping) * 7.0 + 30
        g.append(f'<rect x="{W - 40 - sw_w:.1f}" y="{sy + 14}" width="{sw_w:.1f}" height="21" rx="10.5" fill="{scol}" '
                 f'fill-opacity="0.12" stroke="{scol}" stroke-opacity="0.6"/>')
        g.append(f'<circle cx="{W - 40 - sw_w + 12:.1f}" cy="{sy + 24.5}" r="3.2" fill="{scol}">'
                 f'{breathe("opacity", "1;0.25;1", "1.1s") if r else ""}</circle>')
        g.append(f'<text x="{W - 40 - sw_w + 21:.1f}" y="{sy + 28.5}" font-family="{MONO}" font-size="10" font-weight="700" '
                 f'letter-spacing="1" fill="{scol}">{label}{esc(ping)}</text>')
        g.append(f'<text x="{bx - 2}" y="{sy + 66}" font-family="{SANS}" font-size="34" font-weight="900" font-style="italic" '
                 f'letter-spacing="-0.5" fill="#ffffff">'
                 + turn(k, n, [0.0, 0.08], [f"{bx + 40}", f"{bx - 2}"], f"{bx - 2}", T, attr="x")
                 + f'{esc(proj["name"])}</text>')
        for m, line in enumerate(proj["pitch"]):
            g.append(f'<text x="{bx}" y="{sy + 90 + m * 17}" font-family="{SANS}" font-size="13" fill="#a1a1aa">{esc(line)}</text>')
        g.append(f'<text x="{bx}" y="{sy + 138}" font-family="{MONO}" font-size="9" letter-spacing="1.6" fill="{col}">SIGNATURE MOVE</text>')
        g.append(f'<text x="{bx}" y="{sy + 156}" font-family="{SANS}" font-size="14.5" font-weight="700" fill="#f5f3ff">'
                 f'{esc(proj["move"])}</text>')
        # stat bars
        bars = []
        if st:
            b, c = st.get("bytes", 0), st.get("commits", 0)
            bars.append(("CODE", fmt_bytes(b), max(0.06, (math.log10(max(b, 10)) - 3) / max(0.1, math.log10(max_bytes) - 3))))
            bars.append(("COMMITS", str(c), max(0.06, math.sqrt(c / max_commits))))
        track_x, track_w = bx + 78, 250
        for m, (lab, val, frac) in enumerate(bars):
            y = sy + 180 + m * 22
            fw = track_w * min(1.0, frac)
            g.append(f'<text x="{bx}" y="{y + 7}" font-family="{MONO}" font-size="9" letter-spacing="1.4" fill="#8b7fb8">{lab}</text>')
            g.append(f'<rect x="{track_x}" y="{y}" width="{track_w}" height="8" rx="4" fill="#1a1230"/>')
            g.append(f'<rect x="{track_x}" y="{y}" width="{fw:.1f}" height="8" rx="4" fill="{col}">'
                     + turn(k, n, [0.0, 0.22], ["0", f"{fw:.1f}"], f"{fw:.1f}", T, attr="width") + '</rect>')
            g.append(f'<rect x="{track_x}" y="{y}" width="{fw:.1f}" height="8" rx="4" fill="url(#selShine)" opacity="0.8">'
                     + turn(k, n, [0.0, 0.22], ["0", f"{fw:.1f}"], f"{fw:.1f}", T, attr="width") + '</rect>')
            g.append(f'<text x="{track_x + track_w + 10}" y="{y + 8}" font-family="{MONO}" font-size="10" font-weight="700" '
                     f'fill="#f5f3ff">{esc(val)}</text>')
        # language mix as a segmented bar
        langs = st.get("langs") if st else None
        if langs:
            y = sy + 180 + len(bars) * 22
            total = sum(s for _, s, _ in langs) or 1
            g.append(f'<text x="{bx}" y="{y + 7}" font-family="{MONO}" font-size="9" letter-spacing="1.4" fill="#8b7fb8">LANGS</text>')
            cx_ = track_x
            legend = []
            for name, size, lc in langs:
                seg = track_w * size / total
                g.append(f'<rect x="{cx_:.1f}" y="{y}" width="{max(seg - 1.5, 1.5):.1f}" height="8" rx="2" fill="{lc}"/>')
                cx_ += seg
                legend.append(f"{name} {size * 100 / total:.0f}%")
            g.append(f'<text x="{track_x + track_w + 10}" y="{y + 8}" font-family="{MONO}" font-size="9" fill="#c4b5fd">'
                     f'{esc(" · ".join(legend[:2]))}</text>')
        # stack chips
        cx_ = bx
        cy_ = sy + sh - 30
        for chip in proj["stack"]:
            cw = len(chip) * 6.4 + 18
            g.append(f'<rect x="{cx_:.1f}" y="{cy_}" width="{cw:.1f}" height="19" rx="9.5" fill="{col}" fill-opacity="0.1" '
                     f'stroke="{col}" stroke-opacity="0.5"/>')
            g.append(f'<text x="{cx_ + cw / 2:.1f}" y="{cy_ + 13}" text-anchor="middle" font-family="{MONO}" font-size="9.5" '
                     f'fill="#f5f3ff">{esc(chip)}</text>')
            cx_ += cw + 6
        g.append('</g>')
        p.append("".join(g))

    # ---- the roster strip
    for k, proj in enumerate(ROSTER):
        col = proj["color"]
        tx = rx0 + k * (tile_w + gap)
        r = res.get(proj["fleet"]) if proj["fleet"] else None
        p.append(f'<rect x="{tx:.1f}" y="{ry0}" width="{tile_w}" height="{tile_h}" rx="11" fill="#0d0818" stroke="{col}" stroke-opacity="0.35"/>')
        s0, s1 = k / n, (k + 1) / n
        lit_vals = "1;0" if k == 0 else ("0;1" if k == n - 1 else "0;1;0")
        lit_kt = f"0;{s1:.4f}" if k == 0 else (f"0;{s0:.4f}" if k == n - 1 else f"0;{s0:.4f};{s1:.4f}")
        p.append(f'<rect x="{tx:.1f}" y="{ry0}" width="{tile_w}" height="{tile_h}" rx="11" fill="{col}" opacity="{0.2 if k == 0 else 0}">'
                 f'<animate attributeName="opacity" values="{lit_vals.replace("1", "0.2")}" keyTimes="{lit_kt}" calcMode="discrete" '
                 f'dur="{T}s" repeatCount="indefinite"/></rect>')
        p.append(emblem(proj["icon"], col, tx + tile_w / 2, ry0 + 30, 30, 1.7))
        fs, ls = (8.5, 0.6) if len(proj["short"]) <= 9 else (7.6, 0.1)
        p.append(f'<text x="{tx + tile_w / 2:.1f}" y="{ry0 + 62}" text-anchor="middle" font-family="{MONO}" font-size="{fs}" '
                 f'letter-spacing="{ls}" fill="#d4d4d8">{esc(proj["short"])}</text>')
        if r:
            dot = STATUS[r["s"]][1]
            p.append(f'<circle cx="{tx + tile_w - 10:.1f}" cy="{ry0 + 10}" r="3" fill="{dot}" filter="url(#selGlow)">'
                     f'{breathe("opacity", "1;0.3;1", f"{1.2 + k * 0.1:.1f}s")}</circle>')
    # the P1 cursor jumping along the roster
    xs = ";".join(f"{rx0 + k * (tile_w + gap) - 4:.1f}" for k in range(n))
    kts = ";".join(f"{k / n:.4f}" for k in range(n))
    p.append(f'<g><animateTransform attributeName="transform" type="translate" values="{";".join(f"{float(x) - (rx0 - 4):.1f},0" for x in xs.split(";"))}" '
             f'keyTimes="{kts}" calcMode="discrete" dur="{T}s" repeatCount="indefinite"/>'
             f'<rect x="{rx0 - 4:.1f}" y="{ry0 - 4}" width="{tile_w + 8}" height="{tile_h + 8}" rx="14" fill="none" '
             f'stroke="#fde047" stroke-width="2.4" filter="url(#selGlow)">{breathe("stroke-opacity", "1;0.45;1", "0.8s")}</rect>'
             f'<rect x="{rx0 + tile_w / 2 - 15:.1f}" y="{ry0 - 18}" width="30" height="15" rx="4" fill="#ef4444"/>'
             f'<text x="{rx0 + tile_w / 2:.1f}" y="{ry0 - 7}" text-anchor="middle" font-family="{SANS}" font-size="10" '
             f'font-weight="900" fill="#ffffff">P1</text></g>')

    # ---- footer
    fy = H - 22
    p.append(f'<text x="28" y="{fy}" font-family="{MONO}" font-size="9" letter-spacing="1.2" fill="#8b7fb8">'
             f'◀ ▶ AUTO-SELECT · STATS FROM THE GITHUB API · '
             f'<tspan fill="#4ade80">●</tspan> ONLINE = PASSED ITS LAST HEALTH CHECK (EVERY {CADENCE_H} H)</text>')
    p.append(f'<text x="{W - 28}" y="{fy}" text-anchor="end" font-family="{SANS}" font-size="11" font-weight="900" '
             f'letter-spacing="2" fill="#fde047">PRESS START'
             f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.5;1" dur="1s" repeatCount="indefinite"/></text>')
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
