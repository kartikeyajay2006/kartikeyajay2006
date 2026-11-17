#!/usr/bin/env python3
"""Generate section 07 "Selected Projects": a drawing set in assets/selected/.

  - cover.svg: the cover sheet. "Ten systems, drawn as they run", a sheet
    index of every project with its class, and the live demos' latest health
    check (online count, time checked, share of checks passed since the
    history began);
  - NN-<project>.svg: one engineering sheet per project. Each redraws the
    "how it works" diagram from that repository's own README, with data
    packets flowing through it; a dimension line gives the code size to
    scale by language and the commit count (GitHub API); a title block gives
    the stack and, for projects with a live demo, ONLINE / WAKING /
    DEGRADED / OFFLINE and the response time from the health checks this
    script runs every 3 hours (appended to data/fleet-history.json).

Nothing on a sheet is self-reported: every number is either from the GitHub
API or from a request the runner made, and pitch, diagram and stack are
taken from each repository's README.

SVG notes (see generate_signal.py): GitHub strips <script> and inline
<style>, so all motion is SMIL and nothing uses <use>/<mpath>; every packet
carries its own inline path. Everything readable starts visible, so a
renderer without SMIL shows the finished drawing.

Environment: GH_TOKEN (the same GH_CONTRIB_PAT the other workflows use) for
the repository stats; if the API is unavailable the last stats saved in
data/project-stats.json are used. FLEET_FIXTURE=<history.json> renders a saved
history without making requests; FLEET_NO_SAVE=1 checks live but leaves the
data files alone. OUT_DIR changes where the sheets are written.

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

MONO = "ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
EASE = "0.42 0 0.58 1"

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


# ------------------------------------------------------------------ the drawing set
# Ten projects, AI products first. Each sheet redraws the "how it works" diagram from
# that repository's own README (mermaid flowcharts, distilled to their main path), so
# nothing on a sheet is invented: pitch, nodes and stack come from the README, sizes,
# commits and languages from the GitHub API, status from the health checks above.
OUT_DIR = os.environ.get("OUT_DIR", "assets/selected")

# node: (id, column, row, title, subtitle). Rows: 0 top, 1 bottom, 0.5 between.
ROSTER = [
    {"repo": "AI-Businesses", "slug": "01-merchant-copilot", "name": "AI Merchant Copilot", "color": "#f472b6",
     "cls": "AI PRODUCT · RETAIL", "fleet": None, "live": None,
     "pitch": "A shop assistant for India's small merchants: stock, sales, khata, forecasts.",
     "stack": ["React", "FastAPI", "GPT-4o-mini", "scikit-learn"],
     "nodes": [("cam", 0, 0, "Product photo", "camera stock-in"), ("vis", 1, 0, "GPT-4o-mini", "vision · brand"),
               ("inv", 2, 0, "Inventory", "no duplicate SKU"), ("chat", 0, 1, "Ask the shop", "Hindi · English"),
               ("ctx", 1, 1, "Grounded", "stock · khata · sales"), ("ans", 2, 1, "Answer", "from own data"),
               ("fc", 3, 0.5, "Forecast", "linear regression")],
     "edges": [("cam", "vis"), ("vis", "inv"), ("chat", "ctx"), ("ctx", "ans"), ("inv", "fc")]},
    {"repo": "Financial-Health-Score", "slug": "02-financial-health", "name": "Financial Health Card", "color": "#22d3ee",
     "cls": "FINTECH · EXPLAINABLE ML", "fleet": None, "live": None,
     "pitch": "Credit scoring for new-to-credit small businesses, explained factor by factor.",
     "stack": ["React", "FastAPI", "scikit-learn", "Firebase"],
     "nodes": [("in", 0, 0.5, "Alternate data", "simulated fetch"), ("f", 1, 0.5, "5 features", "cash flow · GST"),
               ("rf", 2, 0, "Random Forest", "200 trees"), ("gb", 2, 1, "Grad. Boosting", "150 trees"),
               ("e", 3, 0.5, "Ensemble", "blended 60 / 40"), ("card", 4, 0.5, "Health card", "score · limit · PDF")],
     "edges": [("in", "f"), ("f", "rf"), ("f", "gb"), ("rf", "e"), ("gb", "e"), ("e", "card")]},
    {"repo": "AI-Video-Editor", "slug": "03-video-studio", "name": "AI Video Studio", "color": "#f87171",
     "cls": "AI PRODUCT · MEDIA", "fleet": None, "live": None,
     "pitch": "Upload a raw clip, get it back with styled captions timed to the speech.",
     "stack": ["Next.js", "FastAPI", "Whisper", "FFmpeg"],
     "nodes": [("up", 0, 0, "Upload MP4", "+ theme"), ("wh", 1, 0, "Whisper", "local · timed"),
               ("plan", 2, 0, "Edit plan", "plan.json"), ("ass", 3, 0, "ASS captions", "styled"),
               ("ff", 4, 0, "FFmpeg", "burn · keep audio"), ("chat", 2, 1, "Chat restyle", "bold · colour")],
     "edges": [("up", "wh"), ("wh", "plan"), ("plan", "ass"), ("ass", "ff"), ("chat", "plan")]},
    {"repo": "Cardano-BlockPhantom", "slug": "04-blockphantom", "name": "BlockPhantom", "color": "#a78bfa",
     "cls": "WEB3 · HACKATHON FINALIST", "fleet": None, "live": None,
     "pitch": "Check a wallet before you send it money: risk score, history and a PDF.",
     "stack": ["FastAPI", "React", "Blockfrost", "Alchemy"],
     "nodes": [("addr", 0, 0.5, "Address", "+ chain"), ("api", 1, 0.5, "FastAPI", "/wallet/…/risk"),
               ("bf", 2, 0, "Blockfrost", "Cardano"), ("al", 2, 1, "Alchemy", "Ethereum"),
               ("risk", 3, 0.5, "Risk engine", "tx stats → score"), ("pdf", 4, 0, "Report", "dashboard · PDF"),
               ("pay", 4, 1, "Masumi", "pay per check")],
     "edges": [("addr", "api"), ("api", "bf"), ("api", "al"), ("bf", "risk"), ("al", "risk"), ("risk", "pdf"),
               ("risk", "pay")]},
    {"repo": "2nd-Year-MERN-P_S", "slug": "05-shopkart", "name": "ShopKart", "color": "#4ade80",
     "cls": "E-COMMERCE · MERN", "fleet": "shopkart", "live": "https://shopkart-black-one.vercel.app",
     "pitch": "A full-stack store with real orders and stock in MongoDB Atlas.",
     "stack": ["React", "Express", "MongoDB", "Playwright"],
     "nodes": [("ui", 0, 0.5, "React app", "cookie session"), ("api", 1, 0.5, "Express API", "Vercel function"),
               ("cod", 2, 0, "Cash on delivery", "full journey"), ("rp", 2, 1, "Razorpay", "test mode"),
               ("tx", 3, 0.5, "Transaction", "order · stock · cart"), ("db", 4, 0.5, "MongoDB", "Atlas · bom1")],
     "edges": [("ui", "api"), ("api", "cod"), ("api", "rp"), ("cod", "tx"), ("rp", "tx"), ("tx", "db")]},
    {"repo": "codecrafters-shell-java", "slug": "06-jsh", "name": "jsh", "color": "#fbbf24",
     "cls": "SYSTEMS · JAVA", "fleet": None, "live": None,
     "pitch": "A POSIX-style Unix shell, written from scratch in about 600 lines of Java.",
     "stack": ["Java", "JLine", "Maven"],
     "nodes": [("line", 0, 0.5, "Input line", "JLine REPL"), ("tok", 1, 0.5, "Tokenizer", "quotes · escapes"),
               ("redir", 2, 0.5, "Redirect · pipe", "> 2>> a | b | c"), ("bi", 3, 0, "Builtin", "in-process"),
               ("ext", 3, 1, "PATH lookup", "ProcessBuilder"), ("job", 4, 1, "Jobs table", "& · + / -")],
     "edges": [("line", "tok"), ("tok", "redir"), ("redir", "bi"), ("redir", "ext"), ("ext", "job")]},
    {"repo": "ai-image-classifier", "slug": "07-image-classifier", "name": "AI Image Classifier", "color": "#38bdf8",
     "cls": "COMPUTER VISION", "fleet": None, "live": None,
     "pitch": "Upload a photo, get the top-3 ImageNet guesses with confidence in about a second.",
     "stack": ["Python", "TensorFlow", "OpenCV", "Streamlit"],
     "nodes": [("up", 0, 0.5, "JPG / PNG", "upload"), ("np", 1, 0.5, "Pillow", "→ NumPy"),
               ("rs", 2, 0.5, "Resize", "224 × 224"), ("m", 3, 0.5, "MobileNetV2", "ImageNet"),
               ("top", 4, 0.5, "Top 3", "+ confidence")],
     "edges": [("up", "np"), ("np", "rs"), ("rs", "m"), ("m", "top")]},
    {"repo": "Agentra-Website", "slug": "08-agentra", "name": "Agentra", "color": "#e879f9",
     "cls": "WEB · TEAM BUILD", "fleet": "agentra", "live": "https://agentra-website-chi.vercel.app",
     "pitch": "A cinematic agency site: motion-driven pages, a 3D showcase, a real lead form.",
     "stack": ["Next.js", "TypeScript", "Framer Motion", "Prisma"],
     "nodes": [("app", 0, 0.5, "Next.js app", "design tokens"), ("mo", 1, 0, "Motion", "scroll reveals"),
               ("sc", 2, 0, "3D showcase", "60 FPS · tilt"), ("form", 1, 1, "Lead form", "Zod validation"),
               ("db", 2, 1, "Prisma", "stored leads")],
     "edges": [("app", "mo"), ("mo", "sc"), ("app", "form"), ("form", "db")]},
    {"repo": "blood-group-donor", "slug": "09-bloodconnect", "name": "BloodConnect", "color": "#fb7185",
     "cls": "SOCIAL IMPACT · WEB", "fleet": "bloodconnect", "live": "https://blood-group-donor-two.vercel.app",
     "pitch": "Find donors by blood group and city, with live stats and one-tap requests.",
     "stack": ["React", "Vite"],
     "nodes": [("api", 0, 0.5, "Sample API", "jsonplaceholder"), ("map", 1, 0.5, "Donor model", "blood groups"),
               ("flt", 2, 0.5, "Filters", "group · city"), ("grid", 3, 0.5, "Donor grid", "live stats"),
               ("req", 4, 0.5, "Request", "one tap")],
     "edges": [("api", "map"), ("map", "flt"), ("flt", "grid"), ("grid", "req")]},
    {"repo": "project_ideas--AI-ML-CLUB", "slug": "10-club-ideas", "name": "AI-ML Club Ideas", "color": "#facc15",
     "cls": "COMMUNITY · AI-ML CLUB", "fleet": "club-ideas", "live": "https://projectideas-ai-ml.vercel.app",
     "pitch": "Six applied-AI project briefs for the club's Applied AI & Product Track.",
     "stack": ["HTML", "CSS", "Vercel"],
     "nodes": [("p", 0, 0.5, "The problem", "a real example"), ("who", 1, 0.5, "Who it helps", "the users"),
               ("build", 2, 0.5, "What to build", "four-step flow"), ("v1", 3, 0.5, "First version", "smallest whole"),
               ("demo", 4, 0.5, "The demo", "× 6 projects")],
     "edges": [("p", "who"), ("who", "build"), ("build", "v1"), ("v1", "demo")]},
]

STATUS = {"up": ("ONLINE", "#4ade80"), "slow": ("WAKING", "#fbbf24"), "partial": ("DEGRADED", "#fb923c"),
          "down": ("OFFLINE", "#f87171"), None: ("SOURCE", "#a1a1aa")}

SW, SH = 640, 400            # one sheet
DX0, DX1 = 34, 606           # diagram area, x
ROW_Y = (186, 258)           # diagram rows, y (row 0.5 sits between)
NODE_H = 46
SEG = 0.5                    # seconds a packet takes along one wire



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
                                          "User-Agent": f"{LOGIN}-selected-works"})
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


def text_w(s, size, mono=False, bold=False):
    return len(s) * size * (0.61 if mono else (0.58 if bold else 0.53))


def fit(s, size, width, mono=False, bold=False, floor=9.0):
    while size > floor and text_w(s, size, mono, bold) > width:
        size -= 0.5
    return size


def sheet(k, proj, st, r, n):
    col = proj["color"]
    nodes = {nid: (c, row, t, sub) for nid, c, row, t, sub in proj["nodes"]}
    ncols = max(c for c, _, _, _ in nodes.values()) + 1
    span = DX1 - DX0
    nw = min(124.0, (span - (ncols - 1) * 22) / ncols)
    gap = (span - ncols * nw) / (ncols - 1) if ncols > 1 else 0

    def box(nid):
        c, row, _, _ = nodes[nid]
        x = DX0 + c * (nw + gap)
        y = ROW_Y[0] + row * (ROW_Y[1] - ROW_Y[0])
        return x, y                                       # left edge, vertical centre

    # depth of each node from the sources, for packet timing
    incoming = {nid: [a for a, b in proj["edges"] if b == nid] for nid in nodes}
    depth = {}

    def d(nid):
        if nid not in depth:
            depth[nid] = 0 if not incoming[nid] else 1 + max(d(a) for a in incoming[nid])
        return depth[nid]

    for nid in nodes:
        d(nid)
    period = (max(depth.values()) + 1) * SEG + 1.4

    label, scol = STATUS[r["s"] if r else None]
    ms = f' · {fmt_ms(r["ms"])}' if r and r["s"] in ("up", "slow") else ""
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SW} {SH}" width="100%" role="img" '
           f'aria-labelledby="t{k} d{k}">',
           f'<title id="t{k}">Sheet {k + 1:02d} — {esc(proj["name"])}</title>',
           f'<desc id="d{k}">{esc(proj["name"])}, {esc(proj["cls"].title())}. {esc(proj["pitch"])} How it works: '
           f'{esc("; ".join(f"{nodes[a][2]} to {nodes[b][2]}" for a, b in proj["edges"]))}. Built with '
           f'{esc(", ".join(proj["stack"]))}.'
           + (f' {fmt_bytes(st.get("bytes", 0))} of code, {st.get("commits", 0)} commits.' if st else "")
           + (f' Live demo {label.lower()}{esc(ms.replace(" · ", " in "))}.' if r else "") + '</desc>',
           f'''<defs>
  <linearGradient id="bg{k}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0d0a1c"/><stop offset="1" stop-color="#07050f"/></linearGradient>
  <radialGradient id="lit{k}" cx="0.18" cy="0" r="0.9"><stop offset="0" stop-color="{col}" stop-opacity="0.16"/><stop offset="1" stop-color="{col}" stop-opacity="0"/></radialGradient>
  <filter id="gl{k}" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <clipPath id="cl{k}"><rect width="{SW}" height="{SH}" rx="16"/></clipPath>
</defs>''',
           f'<g clip-path="url(#cl{k})">',
           f'<rect width="{SW}" height="{SH}" fill="url(#bg{k})"/>',
           f'<rect width="{SW}" height="{SH}" fill="url(#lit{k})"/>']
    # blueprint grid: fine every 20, strong every 100
    g = []
    for x in range(20, SW, 20):
        g.append(f'<path d="M{x} 0V{SH}" stroke="{col}" stroke-opacity="{0.075 if x % 100 == 0 else 0.03}"/>')
    for y in range(20, SH, 20):
        g.append(f'<path d="M0 {y}H{SW}" stroke="{col}" stroke-opacity="{0.075 if y % 100 == 0 else 0.03}"/>')
    out.append("".join(g))
    # drawing frame and registration marks
    out.append(f'<rect x="16" y="16" width="{SW - 32}" height="{SH - 32}" rx="8" fill="none" stroke="{col}" '
               f'stroke-opacity="0.28"/>')
    for cx, cy in ((16, 16), (SW - 16, 16), (16, SH - 16), (SW - 16, SH - 16)):
        out.append(f'<path d="M{cx - 7} {cy}H{cx + 7}M{cx} {cy - 7}V{cy + 7}" stroke="{col}" stroke-opacity="0.8"/>')

    # heading
    out.append(f'<text x="{DX0}" y="46" font-family="{MONO}" font-size="11" letter-spacing="1.6" fill="{col}">'
               f'SHEET {k + 1:02d} / {n:02d}<tspan fill="#8b86a3">  ·  {esc(proj["cls"])}</tspan></text>')
    out.append(f'<text x="{DX0}" y="84" font-family="{SANS}" font-size="{fit(proj["name"], 30, span, bold=True)}" '
               f'font-weight="800" letter-spacing="-0.4" fill="#ffffff">{esc(proj["name"])}</text>')
    out.append(f'<text x="{DX0}" y="110" font-family="{SANS}" font-size="{fit(proj["pitch"], 14.5, span)}" '
               f'fill="#cfcbe0">{esc(proj["pitch"])}</text>')
    out.append(f'<text x="{DX1}" y="46" text-anchor="end" font-family="{MONO}" font-size="10" letter-spacing="1.4" '
               f'fill="#6f6a86">HOW IT WORKS ↘</text>')

    # wires
    wires, packets = [], []
    for a, b in proj["edges"]:
        ax, ay = box(a)
        bx, by = box(b)
        ca, cb = nodes[a][0], nodes[b][0]
        if cb > ca:
            x1, y1, x2, y2 = ax + nw, ay, bx, by
            if abs(y1 - y2) < 0.5:
                path = f"M{x1:.1f} {y1:.1f}H{x2 - 1:.1f}"
            else:
                mx = (x1 + x2) / 2
                path = f"M{x1:.1f} {y1:.1f}H{mx:.1f}V{y2:.1f}H{x2 - 1:.1f}"
            head = f"M{x2 - 1:.1f} {y2:.1f}l-7 -4v8Z"
        else:                                          # same column: vertical wire
            x = ax + nw / 2
            up = by < ay
            y1 = ay - NODE_H / 2 if up else ay + NODE_H / 2
            y2 = by + NODE_H / 2 if up else by - NODE_H / 2
            path = f"M{x:.1f} {y1:.1f}V{y2 + (1 if up else -1):.1f}"
            head = (f"M{x:.1f} {y2 + 1:.1f}l-4 7h8Z" if up else f"M{x:.1f} {y2 - 1:.1f}l-4 -7h8Z")
        wires.append(f'<path d="{path}" fill="none" stroke="{col}" stroke-opacity="0.5" stroke-width="1.4" '
                     f'stroke-dasharray="4 4"><animate attributeName="stroke-dashoffset" values="16;0" dur="1.2s" '
                     f'repeatCount="indefinite"/></path><path d="{head}" fill="{col}" fill-opacity="0.85"/>')
        t0 = depth[a] * SEG / period
        t1 = (depth[a] + 1) * SEG / period
        packets.append(
            f'<circle r="3.6" fill="#ffffff" filter="url(#gl{k})" opacity="0">'
            f'<animateMotion path="{path}" keyPoints="0;0;1;1" keyTimes="0;{t0:.4f};{t1:.4f};1" calcMode="linear" '
            f'dur="{period:.2f}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes="0;{t0:.4f};{t0 + 0.004:.4f};'
            f'{t1 - 0.004:.4f};{t1:.4f};1" dur="{period:.2f}s" repeatCount="indefinite"/></circle>')
    out.append("".join(wires))

    # nodes: always drawn (an image that has not started its clock still shows the whole diagram);
    # each lights up whenever a packet arrives
    for nid, (c, row, title, sub) in nodes.items():
        x, y = box(nid)
        top = y - NODE_H / 2
        arrive = depth[nid] * SEG / period
        hit = (f'<animate attributeName="opacity" values="0;0;1;0;0" keyTimes="0;{max(arrive, 0.001):.4f};'
               f'{arrive + 0.04:.4f};{arrive + 0.3:.4f};1" dur="{period:.2f}s" repeatCount="indefinite"/>')
        out.append(
            f'<g>'
            f'<rect x="{x:.1f}" y="{top:.1f}" width="{nw:.1f}" height="{NODE_H}" rx="10" fill="#120d22" '
            f'stroke="{col}" stroke-opacity="0.75" stroke-width="1.2"/>'
            f'<rect x="{x - 3:.1f}" y="{top - 3:.1f}" width="{nw + 6:.1f}" height="{NODE_H + 6}" rx="12" fill="{col}" '
            f'fill-opacity="0.16" stroke="{col}" stroke-width="2" opacity="0" filter="url(#gl{k})">{hit}</rect>'
            f'<text x="{x + nw / 2:.1f}" y="{y - 2:.1f}" text-anchor="middle" font-family="{SANS}" '
            f'font-size="{fit(title, 13.5, nw - 10, bold=True)}" font-weight="700" fill="#ffffff">{esc(title)}</text>'
            f'<text x="{x + nw / 2:.1f}" y="{y + 14:.1f}" text-anchor="middle" font-family="{MONO}" '
            f'font-size="{fit(sub, 10, nw - 10, mono=True, floor=8)}" fill="#9d97b8">{esc(sub)}</text></g>')
    out.append("".join(packets))

    # dimension line: the code base, to scale by language
    yd = 316
    out.append(f'<path d="M{DX0} {yd - 7}V{yd + 7}M{DX1} {yd - 7}V{yd + 7}" stroke="#8b86a3"/>')
    langs = (st or {}).get("langs") or []
    tot = sum(s for _, s, _ in langs) or 1
    lx = DX0 + 8
    if langs:
        for name, size, lc in langs:
            seg = (span - 16) * size / tot
            out.append(f'<rect x="{lx:.1f}" y="{yd - 1.5}" width="{max(seg - 1.5, 1.5):.1f}" height="3" rx="1.5" fill="{lc}"/>')
            lx += seg
    else:
        out.append(f'<path d="M{DX0 + 8} {yd}H{DX1 - 8}" stroke="#8b86a3"/>')
    out.append(f'<path d="M{DX0 + 1} {yd}l7 -3.5v7Z M{DX1 - 1} {yd}l-7 -3.5v7Z" fill="#8b86a3"/>')
    if st:
        dim = f'{fmt_bytes(st.get("bytes", 0))} OF CODE  ·  {st.get("commits", 0)} COMMITS'
        mix = "   ".join(f"{name} {100 * size / tot:.0f}%" for name, size, _ in langs)
        out.append(f'<text x="{SW / 2}" y="{yd - 9}" text-anchor="middle" font-family="{MONO}" font-size="10.5" '
                   f'letter-spacing="1.1" fill="#d6d2e6">{dim}</text>')
        out.append(f'<text x="{SW / 2}" y="{yd + 18}" text-anchor="middle" font-family="{MONO}" font-size="9.5" '
                   f'fill="#7d7896">{esc(mix)}</text>')

    # title block
    tb_y, tb_h, split = 342, 40, 432
    stack = "  ·  ".join(proj["stack"])
    out.append(f'<rect x="{DX0}" y="{tb_y}" width="{span}" height="{tb_h}" rx="6" fill="#0b0818" stroke="{col}" '
               f'stroke-opacity="0.35"/><path d="M{split} {tb_y}V{tb_y + tb_h}" stroke="{col}" stroke-opacity="0.35"/>')
    out.append(f'<text x="{DX0 + 12}" y="{tb_y + 15}" font-family="{MONO}" font-size="8.5" letter-spacing="1.4" '
               f'fill="#6f6a86">BUILT WITH</text>')
    out.append(f'<text x="{DX0 + 12}" y="{tb_y + 31}" font-family="{SANS}" font-size="{fit(stack, 12.5, split - DX0 - 24, bold=True)}" '
               f'font-weight="600" fill="#ece9f6">{esc(stack)}</text>')
    out.append(f'<text x="{split + 12}" y="{tb_y + 15}" font-family="{MONO}" font-size="8.5" letter-spacing="1.4" '
               f'fill="#6f6a86">{"LIVE DEMO" if proj["fleet"] else "REPOSITORY"}</text>')
    if r:
        out.append(f'<circle cx="{split + 18}" cy="{tb_y + 27}" r="4" fill="{scol}" filter="url(#gl{k})">'
                   f'{breathe("opacity", "1;0.3;1", "1.6s")}</circle>')
        out.append(f'<text x="{split + 28}" y="{tb_y + 31}" font-family="{MONO}" font-size="11.5" font-weight="700" '
                   f'letter-spacing="0.6" fill="{scol}">{label}{esc(ms)}</text>')
    else:
        out.append(f'<text x="{split + 12}" y="{tb_y + 31}" font-family="{MONO}" font-size="11.5" font-weight="700" '
                   f'letter-spacing="0.6" fill="#cfcbe0">OPEN SOURCE ↗</text>')
    out.append('</g>')
    out.append(f'<rect x="0.5" y="0.5" width="{SW - 1}" height="{SH - 1}" rx="16" fill="none" stroke="{col}" stroke-opacity="0.4"/>')
    out.append('</svg>')
    return "\n".join(out)


CW, CH = 1280, 420


def cover(runs, stats):
    latest = runs[-1] if runs else {"results": {}, "at": None}
    res = latest.get("results", {})
    last_at = (datetime.fromisoformat(latest["at"].replace("Z", "+00:00")).astimezone(TZ)
               if latest.get("at") else None)
    live = [p for p in ROSTER if p["fleet"]]
    online = sum(1 for p in live if res.get(p["fleet"], {}).get("s") in ("up", "slow"))
    ok = total = 0
    for run in runs:
        for p in live:
            rr = run.get("results", {}).get(p["fleet"])
            if rr:
                total += 1
                ok += rr.get("s") in ("up", "slow")
    avail = f"{100 * ok / total:.1f}%" if total else "—"
    since = (datetime.fromisoformat(runs[0]["at"].replace("Z", "+00:00")).astimezone(TZ).strftime("%-d %b")
             if runs else "")
    code = sum(stats.get(p["repo"], {}).get("bytes", 0) for p in ROSTER)
    commits = sum(stats.get(p["repo"], {}).get("commits", 0) for p in ROSTER)
    n = len(ROSTER)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CW} {CH}" width="100%" role="img" aria-labelledby="ct cd">',
         '<title id="ct">Selected works — the drawing set</title>',
         f'<desc id="cd">The cover sheet of a drawing set of {n} selected projects: ten systems, drawn as they run. '
         f'A sheet index lists every project with its class and, for the {len(live)} with a live demo, its latest '
         f'health check: {online} of {len(live)} online, checked at {last_at.strftime("%H:%M") if last_at else "--:--"} '
         f'{TZ_NAME}, {avail} of checks passed since {since}. Together the projects hold {fmt_bytes(code)} of code '
         f'in {commits} commits.</desc>',
         f'''<defs>
  <linearGradient id="cbg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#100b22"/><stop offset="1" stop-color="#06040c"/></linearGradient>
  <radialGradient id="clit" cx="0.22" cy="0.1" r="0.8"><stop offset="0" stop-color="#a78bfa" stop-opacity="0.22"/><stop offset="1" stop-color="#a78bfa" stop-opacity="0"/></radialGradient>
  <linearGradient id="cink" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#c4b5fd"/><stop offset="0.5" stop-color="#f0abfc"/><stop offset="1" stop-color="#67e8f9"/></linearGradient>
  <filter id="cgl" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <clipPath id="cfr"><rect width="{CW}" height="{CH}" rx="16"/></clipPath>
</defs>''',
         '<g clip-path="url(#cfr)">',
         f'<rect width="{CW}" height="{CH}" fill="url(#cbg)"/><rect width="{CW}" height="{CH}" fill="url(#clit)"/>']
    g = []
    for x in range(20, CW, 20):
        g.append(f'<path d="M{x} 0V{CH}" stroke="#a78bfa" stroke-opacity="{0.07 if x % 100 == 0 else 0.025}"/>')
    for y in range(20, CH, 20):
        g.append(f'<path d="M0 {y}H{CW}" stroke="#a78bfa" stroke-opacity="{0.07 if y % 100 == 0 else 0.025}"/>')
    o.append("".join(g))
    o.append(f'<rect x="18" y="18" width="{CW - 36}" height="{CH - 36}" rx="10" fill="none" stroke="#a78bfa" stroke-opacity="0.3"/>')
    for cx, cy in ((18, 18), (CW - 18, 18), (18, CH - 18), (CW - 18, CH - 18)):
        o.append(f'<path d="M{cx - 9} {cy}H{cx + 9}M{cx} {cy - 9}V{cy + 9}" stroke="#c4b5fd"/>')

    # left: the title
    o.append(f'<text x="58" y="72" font-family="{MONO}" font-size="12.5" letter-spacing="2.2" fill="#a78bfa">'
             f'SYSTEM // 07  ·  SELECTED WORKS  ·  DRAWING SET</text>')
    o.append(f'<text x="56" y="140" font-family="{SANS}" font-size="54" font-weight="800" letter-spacing="-1.4" '
             f'fill="#ffffff">Ten systems,</text>')
    o.append(f'<text x="56" y="200" font-family="{SANS}" font-size="54" font-weight="800" letter-spacing="-1.4" '
             f'fill="url(#cink)">drawn as they run.</text>')
    # the pen that inks the underline
    o.append(f'<path d="M58 222H560" stroke="url(#cink)" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="502" '
             f'stroke-dashoffset="0"><animate attributeName="stroke-dashoffset" values="502;0;0;-502" keyTimes="0;0.35;0.8;1" '
             f'dur="6s" repeatCount="indefinite"/></path>')
    o.append(f'<text x="58" y="258" font-family="{SANS}" font-size="16" fill="#b9b4cc">Each sheet redraws the how-it-works '
             f'diagram from that project\'s own README,</text>')
    o.append(f'<text x="58" y="282" font-family="{SANS}" font-size="16" fill="#b9b4cc">with its real code size, commits '
             f'and languages. Click a sheet to open the repo.</text>')

    # left: live readout
    o.append(f'<text x="58" y="334" font-family="{MONO}" font-size="10" letter-spacing="1.6" fill="#8b86a3">LIVE DEMOS</text>')
    o.append(f'<circle cx="139" cy="330" r="4" fill="#4ade80" filter="url(#cgl)">{breathe("opacity", "1;0.25;1", "1.4s")}</circle>')
    o.append(f'<text x="56" y="376" font-family="{SANS}" font-size="38" font-weight="800" fill="#4ade80">{online}'
             f'<tspan font-size="20" fill="#6b6785"> / {len(live)} online</tspan></text>')
    o.append(f'<text x="246" y="334" font-family="{MONO}" font-size="10" letter-spacing="1.6" fill="#8b86a3">CHECKED</text>')
    o.append(f'<text x="246" y="372" font-family="{SANS}" font-size="26" font-weight="800" fill="#e9e6f5">'
             f'{last_at.strftime("%H:%M") if last_at else "--:--"}<tspan font-family="{MONO}" font-size="11" '
             f'font-weight="400" fill="#8b86a3"> {TZ_NAME} · every {CADENCE_H} h</tspan></text>')
    o.append(f'<text x="452" y="334" font-family="{MONO}" font-size="10" letter-spacing="1.6" fill="#8b86a3">CHECKS PASSED</text>')
    o.append(f'<text x="452" y="372" font-family="{SANS}" font-size="26" font-weight="800" fill="#e9e6f5">{avail}'
             f'<tspan font-family="{MONO}" font-size="11" font-weight="400" fill="#8b86a3"> since {since}</tspan></text>')

    # right: the sheet index, with a reader bar that steps down it
    ix, iy, iw, rh = 680, 54, 562, 30
    o.append(f'<rect x="{ix}" y="{iy}" width="{iw}" height="{rh * n + 52}" rx="10" fill="#0a0716" fill-opacity="0.85" '
             f'stroke="#a78bfa" stroke-opacity="0.35"/>')
    o.append(f'<text x="{ix + 18}" y="{iy + 26}" font-family="{MONO}" font-size="10" letter-spacing="1.8" fill="#a78bfa">'
             f'SHEET INDEX</text>')
    o.append(f'<text x="{ix + iw - 18}" y="{iy + 26}" text-anchor="end" font-family="{MONO}" font-size="10" letter-spacing="1.4" '
             f'fill="#6f6a86">{fmt_bytes(code)} · {commits} COMMITS</text>')
    r0 = iy + 40
    step = 1.6
    ys = ";".join(f"{r0 + i * rh - 1}" for i in range(n))
    kt = ";".join(f"{i / n:.4f}" for i in range(n))
    o.append(f'<rect x="{ix + 8}" y="{r0 - 1}" width="{iw - 16}" height="{rh - 2}" rx="6" fill="#a78bfa" fill-opacity="0.13" '
             f'stroke="#a78bfa" stroke-opacity="0.45"><animate attributeName="y" values="{ys}" keyTimes="{kt}" '
             f'calcMode="discrete" dur="{n * step}s" repeatCount="indefinite"/></rect>')
    for i, p in enumerate(ROSTER):
        y = r0 + i * rh + 19
        rr = res.get(p["fleet"]) if p["fleet"] else None
        lab, sc = STATUS[rr["s"] if rr else None]
        o.append(f'<circle cx="{ix + 26}" cy="{y - 4}" r="4" fill="{p["color"]}"/>')
        o.append(f'<text x="{ix + 40}" y="{y}" font-family="{MONO}" font-size="11" fill="#8b86a3">{i + 1:02d}</text>')
        o.append(f'<text x="{ix + 68}" y="{y}" font-family="{SANS}" font-size="14" font-weight="700" fill="#f4f2fb">'
                 f'{esc(p["name"])}</text>')
        o.append(f'<text x="{ix + 270}" y="{y}" font-family="{MONO}" font-size="9.5" letter-spacing="0.8" fill="#8b86a3">'
                 f'{esc(p["cls"])}</text>')
        if rr:
            o.append(f'<circle cx="{ix + iw - 106}" cy="{y - 4}" r="3.5" fill="{sc}">{breathe("opacity", "1;0.3;1", "1.6s", f"{i * 0.2:.1f}s")}</circle>')
            o.append(f'<text x="{ix + iw - 18}" y="{y}" text-anchor="end" font-family="{MONO}" font-size="10.5" '
                     f'font-weight="700" fill="{sc}">{fmt_ms(rr["ms"]) if rr["s"] in ("up", "slow") else lab}</text>')
        else:
            o.append(f'<text x="{ix + iw - 18}" y="{y}" text-anchor="end" font-family="{MONO}" font-size="10" '
                     f'fill="#6f6a86">source</text>')
    o.append('</g>')
    o.append(f'<rect x="0.5" y="0.5" width="{CW - 1}" height="{CH - 1}" rx="16" fill="none" stroke="#2a1650"/>')
    o.append('</svg>')
    return "\n".join(o)


def build_all(runs, stats):
    latest = runs[-1] if runs else {"results": {}}
    res = latest.get("results", {})
    files = {"cover.svg": cover(runs, stats)}
    for k, proj in enumerate(ROSTER):
        r = res.get(proj["fleet"]) if proj["fleet"] else None
        files[f'{proj["slug"]}.svg'] = sheet(k, proj, stats.get(proj["repo"], {}), r, len(ROSTER))
    return files


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
        files = build_all(runs, stats)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: selected works failed, leaving existing files untouched: {e}", file=sys.stderr)
        return 0
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        for name, svg in files.items():
            with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
                f.write(svg)
        if not FIXTURE and not NO_SAVE:
            save_history(HISTORY_PATH, runs)
            if fresh:
                with open(STATS_PATH, "w", encoding="utf-8") as f:
                    json.dump(stats, f, indent=1, sort_keys=True)
                    f.write("\n")
        print(f"Wrote {len(files)} files to {OUT_DIR}")
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: failed to write output files: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
