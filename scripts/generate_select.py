#!/usr/bin/env python3
"""Generate section 04 "Selected Work" (assets/selected/) and section 05 "Systems"
(assets/systems/).

Selected Work is a drawing set of the flagship systems:
  - cover.svg: "Seven systems, drawn as they run": an index of every flagship with
    its class, the one proof figure from its README, and the live demos' latest
    health check (online count, time checked, share of checks passed);
  - NN-<project>.svg: one engineering sheet per flagship. Each redraws the "how it
    works" flow from that repository's own README with data packets flowing through
    it; a dimension line gives the code size to scale by language and the commit
    count (GitHub API); a title block gives the stack and, for live demos, ONLINE /
    WAKING / DEGRADED / OFFLINE and the response time;
  - 08-more.svg: the last sheet, pointing down to the rack.

Systems is a rack: rack.svg (the header) and one clickable 1U faceplate per
remaining project, with its domain, one line, stack, code size, commits, and a
status light from the same health checks.

Nothing is self-reported: every number is from the GitHub API, from a request the
runner made, or quoted from that project's own README.

SVG notes (see generate_signal.py): GitHub strips <script> and inline <style>, so
all motion is SMIL and nothing uses <use>/<mpath>. Everything readable starts
visible, so a renderer without SMIL shows the finished drawing.

Environment: GH_TOKEN (the same GH_CONTRIB_PAT the other workflows use) for the
repository stats; if the API is unavailable the last stats saved in
data/project-stats.json are used. FLEET_FIXTURE=<history.json> renders a saved
history without making requests; FLEET_NO_SAVE=1 checks live but leaves the data
files alone. OUT_DIR / RACK_DIR change where the files are written.

Never-fail contract: this script always exits 0. Any problem is logged to stderr
and files are only written after a successful render.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from theme import (BG, CYAN, DOMAIN, DOMAIN_NAME, DOWN, INDIGO, INK, INK_2, INK_3, INK_4, LINE, LINE_2,  # noqa: E402
                   LIVE, MONO, PANEL, PANEL_2, SANS, VIOLET, WAKE, blueprint, breathe, esc, fit, fmt_bytes,
                   fmt_ms, glow, kicker, stamp, text_w)

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
# Seven flagship systems. Each sheet redraws the "how it works" flow from that
# repository's own README (its mermaid diagrams and "in one minute" sections,
# distilled to the main path), so nothing on a sheet is invented: pitch, nodes, stack
# and the proof figure come from the README, sizes, commits and languages from the
# GitHub API, status from the health checks above.
OUT_DIR = os.environ.get("OUT_DIR", "assets/selected")
RACK_DIR = os.environ.get("RACK_DIR", "assets/systems")

# node: (id, column, row, title, subtitle). Rows: 0 top, 1 bottom, 0.5 between.
ROSTER = [
    {"repo": "Sovereign-On_Premise-Agentic-AI-Workbench", "slug": "01-aegis", "name": "AEGIS", "domain": "agentic",
     "cls": "AGENTIC · AIR-GAPPED", "fleet": None, "live": None,
     "proof": "31 / 31 ATTACKS HELD", "tests": 1211,
     "pitch": "Answers your plant can prove: an air-gapped AI workbench for regulated work.",
     "stack": ["FastAPI", "Next.js", "Ollama", "SQLite"],
     "nodes": [("in", 0, 0.5, "Scanned report", "question · PDF"), ("llm", 1, 0, "Ollama", "loopback only"),
               ("reg", 1, 1, "Formula registry", "21 clause-cited"), ("chk", 2, 0.5, "Claim check", "claims traced"),
               ("hum", 3, 0.5, "Human sign-off", "two signatures"), ("rec", 4, 0.5, "Signed record", "verify offline")],
     "edges": [("in", "llm"), ("in", "reg"), ("llm", "chk"), ("reg", "chk"), ("chk", "hum"), ("hum", "rec")]},
    {"repo": "jky-terminal", "slug": "02-jky-terminal", "name": "JKY Terminal", "domain": "tools",
     "cls": "DEVELOPER TOOL · DESKTOP", "fleet": "jky-terminal", "live": "https://kartikeyajay2006.github.io/jky-terminal/",
     "proof": "3,639 TESTS", "tests": 3639,
     "pitch": "The local-first terminal that keeps shells alive and asks before it acts.",
     "stack": ["Rust", "Tauri", "React", "xterm.js"],
     "nodes": [("win", 0, 0.5, "Window", "React · xterm.js"), ("ipc", 1, 0.5, "Pinned IPC", "123 commands"),
               ("core", 2, 0.5, "Rust core", "22 crates"), ("sup", 3, 0, "Supervisor", "outlives window"),
               ("par", 3, 1, "Parsers", "8 · no model"), ("sh", 4, 0, "Your shell", "real PTY"),
               ("pan", 4, 1, "Panels", "under the output")],
     "edges": [("win", "ipc"), ("ipc", "core"), ("core", "sup"), ("core", "par"), ("sup", "sh"), ("par", "pan")]},
    {"repo": "JKY-Radar", "slug": "03-jky-radar", "name": "JKY-Radar", "domain": "tools",
     "cls": "DEVELOPER TOOL · API CONTRACTS", "fleet": "jky-radar", "live": "https://jky-radar.onrender.com",
     "proof": "157 RULES · 558 TESTS", "tests": 558,
     "pitch": "Know what breaks before you ship: API contract diffs with a release gate.",
     "stack": ["Node.js", "Express", "MongoDB", "React"],
     "nodes": [("two", 0, 0.5, "Two versions", "7 formats"), ("parse", 1, 0.5, "Parse safely", "normalised"),
               ("match", 2, 0.5, "Match", "paths · fields"), ("cls", 3, 0.5, "Classify", "157 rules"),
               ("gate", 4, 0, "Gate", "pass · block"), ("imp", 4, 1, "Impact", "teams affected")],
     "edges": [("two", "parse"), ("parse", "match"), ("match", "cls"), ("cls", "gate"), ("gate", "imp")]},
    {"repo": "Agent_that_act-Hackathon", "slug": "04-forgesre", "name": "ForgeSRE", "domain": "agentic",
     "cls": "AGENTIC · SRE", "fleet": None, "live": None,
     "proof": "17 MCP TOOLS · 79 TESTS", "tests": 79,
     "pitch": "An SRE agent that proves its fix, and stops for a human before a rollback.",
     "stack": ["Python", "MCP", "Docker", "PostgreSQL"],
     "nodes": [("al", 0, 0.5, "Alerts", "firing"), ("inv", 1, 0.5, "Investigate", "metrics · logs"),
               ("prv", 2, 0.5, "Prove", "in the sandbox"), ("rs", 3, 0, "Restart", "autonomous"),
               ("hum", 3, 1, "Human gate", "rollback waits"), ("ver", 4, 0.5, "Verify", "p95 · error rate")],
     "edges": [("al", "inv"), ("inv", "prv"), ("prv", "rs"), ("prv", "hum"), ("rs", "ver"), ("hum", "ver")]},
    {"repo": "Wispr_goa_task", "slug": "05-eraseops", "name": "EraseOps", "domain": "agentic",
     "cls": "AGENTIC · PRIVACY", "fleet": None, "live": None,
     "proof": "ZERO-RESIDUAL RESCAN", "tests": None,
     "pitch": "Delete a customer from every system, and prove it, behind one approved plan.",
     "stack": ["TypeScript", "LangGraph", "PostgreSQL", "MinIO"],
     "nodes": [("g", 0, 0.5, "Goal", "typed or spoken"), ("d", 1, 0.5, "Discovery", "read-only MCP"),
               ("reh", 2, 0, "Rehearsal", "rolled-back txn"), ("bk", 2, 1, "Backup", "verified copy"),
               ("h", 3, 0.5, "Human", "signs plan hash"), ("x", 4, 0.5, "Erase", "+ rescan to zero")],
     "edges": [("g", "d"), ("d", "reh"), ("d", "bk"), ("reh", "h"), ("bk", "h"), ("h", "x")]},
    {"repo": "Multimodal-Data-Management-Pipeline-for-RAG-Ready-Systems", "slug": "06-evidence-console",
     "name": "Evidence Console", "domain": "intel",
     "cls": "INTELLIGENCE · MULTIMODAL RAG", "fleet": "evidence", "live": "https://frontend-sigma-murex-82.vercel.app/",
     "proof": "125+ TESTS", "tests": 125,
     "pitch": "Every answer links to the exact video second or PDF page it came from.",
     "stack": ["FastAPI", "React", "pgvector", "Neo4j"],
     "nodes": [("in", 0, 0.5, "Video · PDF", "+ audio · image"), ("ex", 1, 0.5, "Extract", "Whisper · OCR"),
               ("ln", 2, 0.5, "Cross-link", "resolve entities"), ("pg", 3, 0, "pgvector", "evidence units"),
               ("neo", 3, 1, "Neo4j", "typed relations"), ("ans", 4, 0.5, "Cited answer", "second · page")],
     "edges": [("in", "ex"), ("ex", "ln"), ("ln", "pg"), ("ln", "neo"), ("pg", "ans"), ("neo", "ans")]},
    {"repo": "multi-layer_orchestation", "slug": "07-chakraview", "name": "Chakraview", "domain": "agentic",
     "cls": "AGENT OPS · COMMAND CENTER", "fleet": "chakraview", "live": "https://multi-layer-orchestation.vercel.app/",
     "proof": "CONFIDENCE GATE 0.7", "tests": None,
     "pitch": "Launch many agents at once, watch every step, hold unsure results for a human.",
     "stack": ["Next.js", "Fastify", "SQLite", "WebSockets"],
     "nodes": [("op", 0, 0.5, "Operator", "launches tasks"), ("tg", 1, 0.5, "Task graph", "plan → review"),
               ("log", 2, 0, "Node logs", "per-node trace"), ("cf", 2, 1, "Confidence", "below 0.7 waits"),
               ("ws", 3, 0, "Live feed", "WebSockets"), ("q", 3, 1, "Oversight", "approve · reject"),
               ("done", 4, 1, "Completed", "counts only now")],
     "edges": [("op", "tg"), ("tg", "log"), ("tg", "cf"), ("log", "ws"), ("cf", "q"), ("q", "done")]},
]

# The rack: everything else worth opening, one line each.
RACK = [
    {"repo": "JKY-Folder", "name": "JKY-Folder", "domain": "product", "cls": "PRODUCT · APPLICATION DOCUMENTS",
     "pitch": "Students' application documents, with page-cited checklists from instruction PDFs.",
     "stack": ["React", "TypeScript", "Express", "Tesseract"], "fleet": None, "note": "528 TESTS"},
    {"repo": "my-localmcp", "name": "my-localmcp", "domain": "tools", "cls": "DEVELOPER TOOL · MCP SERVER",
     "pitch": "An offline MCP server that gives coding agents fast, deterministic repo context.",
     "stack": ["Python", "SQLite FTS5", "Ollama", "MCP"], "fleet": None, "note": "RUNS OFFLINE"},
    {"repo": "github-ranking", "name": "github-ranking", "domain": "tools", "cls": "DEVELOPER TOOL · SCORING",
     "pitch": "Scores developers and teams out of 100 on what they actually built themselves.",
     "stack": ["Next.js", "TypeScript", "SQLite"], "fleet": None, "note": "PRIVATE INSTANCE"},
    {"repo": "agent--flow", "name": "AgentFlow OS", "domain": "agentic", "cls": "GOVERNANCE · RISK TIERS",
     "pitch": "Risk-tiered human approval across support, HR, finance, sales and IT-ops agents.",
     "stack": ["Next.js", "FastAPI", "PostgreSQL", "Redis"], "fleet": None, "note": None},
    {"repo": "Multimodel-governance-B2A", "name": "B2A Governance", "domain": "agentic", "cls": "GOVERNANCE · AUDIT",
     "pitch": "Every agent action checked against policy, billed and hash-chained into an audit log.",
     "stack": ["FastAPI", "SQLAlchemy", "PostgreSQL", "Prometheus"], "fleet": None, "note": None},
    {"repo": "RL-model-Negotiation", "name": "DealForge", "domain": "intel", "cls": "ML · REINFORCEMENT LEARNING",
     "pitch": "An RL environment where a buyer agent learns to close good, fair, low-risk deals.",
     "stack": ["Python", "TRL PPO", "Qwen2.5", "OpenEnv"], "fleet": None, "note": None},
    {"repo": "GitVeda", "name": "GitVeda", "domain": "product", "cls": "PRODUCT · LEARN GIT",
     "pitch": "Learn Git by playing it: 30 levels in a simulated in-browser Git terminal.",
     "stack": ["React", "Vite", "Firebase", "OpenAI"], "fleet": "gitveda", "note": None},
    {"repo": "AI-Businesses", "name": "AI Merchant Copilot", "domain": "intel", "cls": "AI PRODUCT · RETAIL",
     "pitch": "A shop assistant for India's small merchants: stock, sales, khata, forecasts.",
     "stack": ["React", "FastAPI", "GPT-4o-mini", "scikit-learn"], "fleet": None, "note": None},
    {"repo": "AI-Video-Editor", "name": "AI Video Studio", "domain": "intel", "cls": "AI PRODUCT · MEDIA",
     "pitch": "Upload a raw clip, get it back with styled captions timed to the speech.",
     "stack": ["Next.js", "FastAPI", "Whisper", "FFmpeg"], "fleet": None, "note": None},
    {"repo": "Financial-Health-Score", "name": "Financial Health Card", "domain": "intel", "cls": "FINTECH · EXPLAINABLE ML",
     "pitch": "Explainable credit scoring for new-to-credit businesses, on synthetic data.",
     "stack": ["React", "FastAPI", "scikit-learn", "Firebase"], "fleet": None, "note": "PROTOTYPE"},
    {"repo": "Cardano-BlockPhantom", "name": "BlockPhantom", "domain": "product", "cls": "WEB3 · HACKATHON FINALIST",
     "pitch": "Check a wallet before you send it money: risk score, history and a PDF report.",
     "stack": ["FastAPI", "React", "Blockfrost", "Alchemy"], "fleet": None, "note": "FINALIST"},
    {"repo": "2nd-Year-MERN-P_S", "name": "ShopKart", "domain": "product", "cls": "E-COMMERCE · MERN",
     "pitch": "A full-stack store with real orders and stock in MongoDB Atlas.",
     "stack": ["React", "Express", "MongoDB", "Playwright"], "fleet": "shopkart", "note": None},
    {"repo": "codecrafters-shell-java", "name": "jsh", "domain": "tools", "cls": "SYSTEMS · JAVA",
     "pitch": "A POSIX-style Unix shell, written from scratch in about 600 lines of Java.",
     "stack": ["Java", "JLine", "Maven"], "fleet": None, "note": None},
    {"repo": "ai-image-classifier", "name": "AI Image Classifier", "domain": "intel", "cls": "COMPUTER VISION",
     "pitch": "Upload a photo, get the top-3 ImageNet guesses with confidence in about a second.",
     "stack": ["Python", "TensorFlow", "Streamlit"], "fleet": None, "note": None},
    {"repo": "Agentra-Website", "name": "Agentra", "domain": "product", "cls": "WEB · TEAM BUILD",
     "pitch": "A cinematic agency site: motion-driven pages, a 3D showcase, a real lead form.",
     "stack": ["Next.js", "TypeScript", "Framer Motion", "Prisma"], "fleet": "agentra", "note": None},
    {"repo": "blood-group-donor", "name": "BloodConnect", "domain": "product", "cls": "SOCIAL IMPACT · WEB",
     "pitch": "Find blood donors by group and city, with one-tap requests, on a sample API.",
     "stack": ["React", "Vite"], "fleet": "bloodconnect", "note": None},
    {"repo": "project_ideas--AI-ML-CLUB", "name": "AI-ML Club Ideas", "domain": "product", "cls": "COMMUNITY · AI-ML CLUB",
     "pitch": "Six applied-AI project briefs for the club's Applied AI & Product Track.",
     "stack": ["HTML", "CSS"], "fleet": "club-ideas", "note": None},
    {"repo": "kartikeya-portfolio", "name": "Portfolio", "domain": "product", "cls": "WEB · PERSONAL SITE",
     "pitch": "Immersive personal site: cinematic loader, particle network, a working terminal.",
     "stack": ["HTML", "CSS", "JavaScript"], "fleet": "portfolio", "note": None},
]

STATUS = {"up": ("ONLINE", LIVE), "slow": ("WAKING", WAKE), "partial": ("DEGRADED", "#fb923c"),
          "down": ("OFFLINE", DOWN), None: ("SOURCE", INK_3)}

SW, SH = 640, 400            # one sheet
DX0, DX1 = 34, 606           # diagram area, x
ROW_Y = (192, 262)           # diagram rows, y (row 0.5 sits between)
NODE_H = 46
SEG = 0.5                    # seconds a packet takes along one wire

WORDS = {n: w for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split())}


STATS_Q = """{ %s }
fragment F on Repository {
  languages(first: 3, orderBy: {field: SIZE, direction: DESC}) { totalSize edges { size node { name color } } }
  defaultBranchRef { target { ... on Commit { history { totalCount } } } }
}"""


def fetch_stats():
    """Code size, commits and top languages per repo; cached so a run without a token
    (or with the API down) still draws the last known numbers."""
    cached = {}
    try:
        with open(STATS_PATH, encoding="utf-8") as f:
            cached = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    if not TOKEN or FIXTURE:
        return cached, False
    repos = [p["repo"] for p in ROSTER + RACK]
    fields = " ".join(f'r{i}: repository(owner: "{LOGIN}", name: "{r}") {{ ...F }}' for i, r in enumerate(repos))
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
    for i, repo in enumerate(repos):
        node = data.get(f"r{i}")
        if not node:
            if repo in cached:
                out[repo] = cached[repo]
            continue
        langs = node.get("languages") or {}
        hist = (((node.get("defaultBranchRef") or {}).get("target") or {}).get("history") or {})
        out[repo] = {
            "bytes": langs.get("totalSize", 0),
            "commits": hist.get("totalCount", 0),
            "langs": [[e["node"]["name"], e["size"], e["node"]["color"] or "#8b949e"] for e in langs.get("edges") or []],
        }
    return out, True


def defs(k, col):
    return (f'<defs><radialGradient id="lit{k}" cx="0.16" cy="0" r="0.95"><stop offset="0" stop-color="{col}" '
            f'stop-opacity="0.13"/><stop offset="1" stop-color="{col}" stop-opacity="0"/></radialGradient>'
            f'{glow(f"gl{k}")}<clipPath id="cl{k}"><rect width="{SW}" height="{SH}" rx="14"/></clipPath></defs>')


def paper(k, col, w=SW, h=SH):
    """Ground, light, engineering grid, drawing frame and registration marks."""
    o = [f'<g clip-path="url(#cl{k})">', f'<rect width="{w}" height="{h}" fill="{BG}"/>',
         f'<rect width="{w}" height="{h}" fill="url(#lit{k})"/>', blueprint(w, h, col),
         f'<rect x="16" y="16" width="{w - 32}" height="{h - 32}" rx="8" fill="none" stroke="{col}" stroke-opacity="0.22"/>']
    for cx, cy in ((16, 16), (w - 16, 16), (16, h - 16), (w - 16, h - 16)):
        o.append(f'<path d="M{cx - 7} {cy}H{cx + 7}M{cx} {cy - 7}V{cy + 7}" stroke="{col}" stroke-opacity="0.75"/>')
    return o


def chip(x_right, y, label, col, size=10):
    """A right-aligned proof chip: the one number from the README that matters most."""
    w = len(label) * (size * 0.62 + 0.6) + 26
    x = x_right - w
    return (f'<rect x="{x:.1f}" y="{y - 13}" width="{w:.1f}" height="20" rx="10" fill="{col}" fill-opacity="0.1" '
            f'stroke="{col}" stroke-opacity="0.55"/>'
            f'<circle cx="{x + 11:.1f}" cy="{y - 3}" r="2.6" fill="{col}">{breathe("opacity", "1;0.35;1", "2.4s")}</circle>'
            f'<text x="{x + 18:.1f}" y="{y + 0.5}" font-family="{MONO}" font-size="{size}" font-weight="700" '
            f'letter-spacing="0.6" fill="{INK}">{esc(label)}</text>')


def sheet(k, proj, st, r, n):
    col = DOMAIN[proj["domain"]]
    nodes = {nid: (c, row, t, sub) for nid, c, row, t, sub in proj["nodes"]}
    ncols = max(c for c, _, _, _ in nodes.values()) + 1
    span = DX1 - DX0
    nw = min(124.0, (span - (ncols - 1) * 22) / ncols)
    gap = (span - ncols * nw) / (ncols - 1) if ncols > 1 else 0

    def box(nid):
        c, row, _, _ = nodes[nid]
        return DX0 + c * (nw + gap), ROW_Y[0] + row * (ROW_Y[1] - ROW_Y[0])

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
           f'<title id="t{k}">Selected work {k + 1:02d}: {esc(proj["name"])}</title>',
           f'<desc id="d{k}">{esc(proj["name"])}, {esc(proj["cls"].title())}. {esc(proj["pitch"])} '
           f'Proof from its repository: {esc(proj["proof"].lower())}. How it works: '
           f'{esc("; ".join(f"{nodes[a][2]} to {nodes[b][2]}" for a, b in proj["edges"]))}. Built with '
           f'{esc(", ".join(proj["stack"]))}.'
           + (f' {fmt_bytes(st.get("bytes", 0))} of code, {st.get("commits", 0)} commits.' if st else "")
           + (f' Live demo {label.lower()}{esc(ms.replace(" · ", " in "))}.' if r else "") + '</desc>',
           defs(k, col)]
    out += paper(k, col)

    # heading
    out.append(f'<text x="{DX0}" y="47" font-family="{MONO}" font-size="10.5" letter-spacing="1.5" fill="{col}">'
               f'{k + 1:02d} / {n:02d}<tspan fill="{INK_3}">  ·  {esc(proj["cls"])}</tspan></text>')
    out.append(chip(DX1, 48, proj["proof"], col))
    out.append(f'<text x="{DX0}" y="88" font-family="{SANS}" font-size="{fit(proj["name"], 31, span, bold=True)}" '
               f'font-weight="800" letter-spacing="-0.5" fill="{INK}">{esc(proj["name"])}</text>')
    out.append(f'<text x="{DX0}" y="114" font-family="{SANS}" font-size="{fit(proj["pitch"], 14, span)}" '
               f'fill="{INK_2}">{esc(proj["pitch"])}</text>')
    out.append(f'<path d="M{DX0} 136H{DX1}" stroke="{col}" stroke-opacity="0.18"/>')
    out.append(kicker(DX0, 152, "HOW IT WORKS  ·  FROM ITS README", fill=INK_4, size=9))

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

    # nodes: always drawn (an image that has not started its clock still shows the whole
    # diagram); each lights up whenever a packet arrives
    for nid, (c, row, title, sub) in nodes.items():
        x, y = box(nid)
        top = y - NODE_H / 2
        arrive = depth[nid] * SEG / period
        hit = (f'<animate attributeName="opacity" values="0;0;1;0;0" keyTimes="0;{max(arrive, 0.001):.4f};'
               f'{arrive + 0.04:.4f};{arrive + 0.3:.4f};1" dur="{period:.2f}s" repeatCount="indefinite"/>')
        out.append(
            f'<g><rect x="{x:.1f}" y="{top:.1f}" width="{nw:.1f}" height="{NODE_H}" rx="10" fill="{PANEL}" '
            f'stroke="{col}" stroke-opacity="0.7" stroke-width="1.2"/>'
            f'<rect x="{x - 3:.1f}" y="{top - 3:.1f}" width="{nw + 6:.1f}" height="{NODE_H + 6}" rx="12" fill="{col}" '
            f'fill-opacity="0.16" stroke="{col}" stroke-width="2" opacity="0" filter="url(#gl{k})">{hit}</rect>'
            f'<text x="{x + nw / 2:.1f}" y="{y - 2:.1f}" text-anchor="middle" font-family="{SANS}" '
            f'font-size="{fit(title, 13.5, nw - 10, bold=True)}" font-weight="700" fill="{INK}">{esc(title)}</text>'
            f'<text x="{x + nw / 2:.1f}" y="{y + 14:.1f}" text-anchor="middle" font-family="{MONO}" '
            f'font-size="{fit(sub, 9.5, nw - 10, mono=True, floor=8)}" fill="{INK_3}">{esc(sub)}</text></g>')
    out.append("".join(packets))

    # dimension line: the code base, to scale by language
    yd = 318
    out.append(f'<path d="M{DX0} {yd - 7}V{yd + 7}M{DX1} {yd - 7}V{yd + 7}" stroke="{INK_4}"/>')
    langs = (st or {}).get("langs") or []
    tot = sum(s for _, s, _ in langs) or 1
    lx = DX0 + 8
    if langs:
        for name, size, lc in langs:
            seg = (span - 16) * size / tot
            out.append(f'<rect x="{lx:.1f}" y="{yd - 1.5}" width="{max(seg - 1.5, 1.5):.1f}" height="3" rx="1.5" fill="{lc}"/>')
            lx += seg
    else:
        out.append(f'<path d="M{DX0 + 8} {yd}H{DX1 - 8}" stroke="{INK_4}"/>')
    out.append(f'<path d="M{DX0 + 1} {yd}l7 -3.5v7Z M{DX1 - 1} {yd}l-7 -3.5v7Z" fill="{INK_4}"/>')
    if st:
        dim = f'{fmt_bytes(st.get("bytes", 0))} OF CODE  ·  {st.get("commits", 0)} COMMITS'
        mix = "   ".join(f"{name} {100 * size / tot:.0f}%" for name, size, _ in langs)
        out.append(f'<text x="{SW / 2}" y="{yd - 9}" text-anchor="middle" font-family="{MONO}" font-size="10" '
                   f'letter-spacing="1.1" fill="{INK_2}">{dim}</text>')
        out.append(f'<text x="{SW / 2}" y="{yd + 17}" text-anchor="middle" font-family="{MONO}" font-size="9" '
                   f'fill="{INK_4}">{esc(mix)}</text>')

    # title block
    tb_y, tb_h, split = 344, 38, 420
    stack = "  ·  ".join(proj["stack"])
    out.append(f'<rect x="{DX0}" y="{tb_y}" width="{span}" height="{tb_h}" rx="6" fill="{PANEL}" stroke="{col}" '
               f'stroke-opacity="0.3"/><path d="M{split} {tb_y}V{tb_y + tb_h}" stroke="{col}" stroke-opacity="0.3"/>')
    out.append(f'<text x="{DX0 + 12}" y="{tb_y + 14}" font-family="{MONO}" font-size="8" letter-spacing="1.4" '
               f'fill="{INK_4}">BUILT WITH</text>')
    out.append(f'<text x="{DX0 + 12}" y="{tb_y + 30}" font-family="{SANS}" font-size="{fit(stack, 12.5, split - DX0 - 24, bold=True)}" '
               f'font-weight="600" fill="{INK}">{esc(stack)}</text>')
    out.append(f'<text x="{split + 12}" y="{tb_y + 14}" font-family="{MONO}" font-size="8" letter-spacing="1.4" '
               f'fill="{INK_4}">{"LIVE" if proj["fleet"] else "REPOSITORY"}</text>')
    if r:
        out.append(f'<circle cx="{split + 18}" cy="{tb_y + 26}" r="4" fill="{scol}" filter="url(#gl{k})">'
                   f'{breathe("opacity", "1;0.3;1", "1.6s")}</circle>')
        out.append(f'<text x="{split + 28}" y="{tb_y + 30}" font-family="{MONO}" font-size="11" font-weight="700" '
                   f'letter-spacing="0.6" fill="{scol}">{label}{esc(ms)}</text>')
    else:
        out.append(f'<text x="{split + 12}" y="{tb_y + 30}" font-family="{MONO}" font-size="11" font-weight="700" '
                   f'letter-spacing="0.6" fill="{INK_2}">OPEN SOURCE ↗</text>')
    out.append('</g>')
    out.append(f'<rect x="0.5" y="0.5" width="{SW - 1}" height="{SH - 1}" rx="14" fill="none" stroke="{LINE}"/>')
    out.append('</svg>')
    return "\n".join(out)


def more_sheet(k, n, res):
    """Sheet 08: the way down to the rack, so the 2-column set stays whole."""
    col = INDIGO
    live = [p for p in RACK if p["fleet"]]
    online = sum(1 for p in live if res.get(p["fleet"], {}).get("s") in ("up", "slow"))
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SW} {SH}" width="100%" role="img" aria-labelledby="t{k} d{k}">',
         f'<title id="t{k}">{len(RACK)} more systems in the rack below</title>',
         f'<desc id="d{k}">The last sheet points down to section 05, Systems: {len(RACK)} more projects racked one '
         f'line each, {online} of {len(live)} live demos online at the last check.</desc>', defs(k, col)]
    o += paper(k, col)
    o.append(f'<text x="{DX0}" y="47" font-family="{MONO}" font-size="10.5" letter-spacing="1.5" fill="{col}">'
             f'{n:02d} / {n:02d}<tspan fill="{INK_3}">  ·  INDEX</tspan></text>')
    o.append(f'<text x="{DX0}" y="88" font-family="{SANS}" font-size="31" font-weight="800" letter-spacing="-0.5" '
             f'fill="{INK}">+{len(RACK)} more systems</text>')
    o.append(f'<text x="{DX0}" y="114" font-family="{SANS}" font-size="14" fill="{INK_2}">'
             f'Racked one line each in 05 Systems, right below.</text>')
    o.append(f'<path d="M{DX0} 136H{DX1}" stroke="{col}" stroke-opacity="0.18"/>')
    # a miniature rack: the first units, a reader bar stepping down them, LEDs breathing
    ux, uh, gap, shown = DX0 + 40, 22, 6, 5
    span_w = DX1 - DX0 - 80
    o.append(f'<rect x="{ux - 18}" y="156" width="{span_w + 36}" height="{shown * (uh + gap) + 12}" rx="6" fill="{PANEL}" '
             f'stroke="{LINE_2}"/>')
    ys = ";".join(f"{162 + i * (uh + gap) - 2}" for i in range(shown))
    kt = ";".join(f"{i / shown:.4f}" for i in range(shown))
    o.append(f'<rect x="{ux - 6}" y="160" width="{span_w + 12}" height="{uh + 4}" rx="6" fill="{col}" fill-opacity="0.1" '
             f'stroke="{col}" stroke-opacity="0.45"><animate attributeName="y" values="{ys}" keyTimes="{kt}" '
             f'calcMode="discrete" dur="{shown * 1.4}s" repeatCount="indefinite"/></rect>')
    for i, p in enumerate(RACK[:shown]):
        y = 162 + i * (uh + gap)
        c = DOMAIN[p["domain"]]
        rr = res.get(p["fleet"]) if p["fleet"] else None
        led = STATUS[rr["s"] if rr else None][1] if rr else INK_4
        o.append(f'<rect x="{ux}" y="{y}" width="{span_w}" height="{uh}" rx="4" fill="{PANEL_2}" stroke="{LINE_2}"/>'
                 f'<rect x="{ux}" y="{y}" width="3" height="{uh}" rx="1.5" fill="{c}"/>'
                 f'<circle cx="{ux + 16}" cy="{y + uh / 2}" r="3" fill="{led}">'
                 f'{breathe("opacity", "1;0.3;1", f"{1.2 + (i % 3) * 0.4:.1f}s", f"{i * 0.2:.1f}s")}</circle>'
                 f'<text x="{ux + 30}" y="{y + 15}" font-family="{SANS}" font-size="12" font-weight="700" fill="{INK}">'
                 f'{esc(p["name"])}</text>'
                 f'<text x="{ux + span_w - 12}" y="{y + 15}" text-anchor="end" font-family="{MONO}" font-size="8.5" '
                 f'letter-spacing="0.8" fill="{INK_3}">{esc(p["cls"])}</text>')
    o.append(f'<text x="{SW / 2}" y="328" text-anchor="middle" font-family="{MONO}" font-size="10" '
             f'letter-spacing="1.2" fill="{INK_3}">+ {len(RACK) - shown} MORE  ·  {online} / {len(live)} LIVE DEMOS ONLINE</text>')
    tb_y = 344
    o.append(f'<rect x="{DX0}" y="{tb_y}" width="{DX1 - DX0}" height="38" rx="6" fill="{col}" fill-opacity="0.1" '
             f'stroke="{col}" stroke-opacity="0.5"/>')
    o.append(f'<text x="{SW / 2}" y="{tb_y + 24}" text-anchor="middle" font-family="{MONO}" font-size="11.5" '
             f'font-weight="700" letter-spacing="1.6" fill="{INK}">OPEN THE RACK ↓</text>')
    o.append('</g>')
    o.append(f'<rect x="0.5" y="0.5" width="{SW - 1}" height="{SH - 1}" rx="14" fill="none" stroke="{LINE}"/>')
    o.append('</svg>')
    return "\n".join(o)


CW, CH = 1280, 420


def availability(runs, ids):
    ok = total = 0
    for run in runs:
        for i in ids:
            rr = run.get("results", {}).get(i)
            if rr:
                total += 1
                ok += rr.get("s") in ("up", "slow")
    return f"{100 * ok / total:.1f}%" if total else "—"


def cover(runs, stats):
    latest = runs[-1] if runs else {"results": {}, "at": None}
    res = latest.get("results", {})
    last_at = (datetime.fromisoformat(latest["at"].replace("Z", "+00:00")).astimezone(TZ)
               if latest.get("at") else None)
    live = [p for p in ROSTER if p["fleet"]]
    online = sum(1 for p in live if res.get(p["fleet"], {}).get("s") in ("up", "slow"))
    avail = availability(runs, [p["fleet"] for p in live])
    since = (datetime.fromisoformat(runs[0]["at"].replace("Z", "+00:00")).astimezone(TZ).strftime("%-d %b")
             if runs else "")
    tests = sum(p["tests"] or 0 for p in ROSTER)
    code = sum(stats.get(p["repo"], {}).get("bytes", 0) for p in ROSTER)
    commits = sum(stats.get(p["repo"], {}).get("commits", 0) for p in ROSTER)
    n = len(ROSTER)
    word = WORDS.get(n, str(n)).capitalize()

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CW} {CH}" width="100%" role="img" aria-labelledby="ct cd">',
         '<title id="ct">Selected work: the flagship systems</title>',
         f'<desc id="cd">{word} flagship systems, drawn as they run. An index lists each with its class, the one proof '
         f'figure from its repository and, for the {len(live)} with a live demo, its latest health check: {online} of '
         f'{len(live)} online at {last_at.strftime("%H:%M") if last_at else "--:--"} {TZ_NAME}, {avail} of checks passed '
         f'since {since}. Together they report {tests:,}+ tests and hold {fmt_bytes(code)} of code in {commits:,} commits.'
         f'</desc>',
         f'''<defs>
  <radialGradient id="clit" cx="0.2" cy="0.05" r="0.85"><stop offset="0" stop-color="{VIOLET}" stop-opacity="0.16"/><stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>
  <linearGradient id="cink" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#c4b5fd"/><stop offset="0.55" stop-color="{INDIGO}"/><stop offset="1" stop-color="#67e8f9"/></linearGradient>
  {glow("cgl", 2.4)}
  <clipPath id="cfr"><rect width="{CW}" height="{CH}" rx="14"/></clipPath>
</defs>''',
         '<g clip-path="url(#cfr)">',
         f'<rect width="{CW}" height="{CH}" fill="{BG}"/><rect width="{CW}" height="{CH}" fill="url(#clit)"/>',
         blueprint(CW, CH, VIOLET, a_fine=0.022, a_strong=0.055)]
    o.append(kicker(40, 44, f"SELECTED WORK  //  {n} FLAGSHIP SYSTEMS"))
    o.append(stamp(CW - 40, 44, f"HEALTH-CHECKED EVERY {CADENCE_H} H  ·  LAST {last_at.strftime('%H:%M') if last_at else '--:--'} {TZ_NAME}"))

    # left: the title
    o.append(f'<text x="40" y="128" font-family="{SANS}" font-size="50" font-weight="800" letter-spacing="-1.4" '
             f'fill="{INK}">{word} systems,</text>')
    o.append(f'<text x="40" y="184" font-family="{SANS}" font-size="50" font-weight="800" letter-spacing="-1.4" '
             f'fill="url(#cink)">drawn as they run.</text>')
    o.append(f'<path d="M42 206H520" stroke="url(#cink)" stroke-width="2.5" stroke-linecap="round" stroke-dasharray="478" '
             f'stroke-dashoffset="0"><animate attributeName="stroke-dashoffset" values="478;0;0;-478" keyTimes="0;0.35;0.8;1" '
             f'dur="6s" repeatCount="indefinite"/></path>')
    o.append(f'<text x="42" y="242" font-family="{SANS}" font-size="15.5" fill="{INK_3}">Each sheet redraws the how-it-works '
             f'flow from that project\'s own README,</text>')
    o.append(f'<text x="42" y="265" font-family="{SANS}" font-size="15.5" fill="{INK_3}">with its proof, code size and '
             f'commits. Click a sheet to open the repository.</text>')

    # left: readout, three cells
    cells = [("TESTS REPORTED", f"{tests:,}+", "by their repositories", INK),
             ("LIVE DEMOS", f"{online} / {len(live)}", "online now", LIVE if online == len(live) else WAKE),
             ("CHECKS PASSED", avail, f"since {since}", INK)]
    for i, (lab, val, sub, c) in enumerate(cells):
        x = 42 + i * 190
        o.append(f'<rect x="{x}" y="296" width="174" height="86" rx="10" fill="{PANEL}" stroke="{LINE}"/>')
        o.append(f'<rect x="{x + 1}" y="308" width="2.5" height="62" rx="1.2" fill="{[VIOLET, LIVE, CYAN][i]}"/>')
        o.append(kicker(x + 16, 318, lab, size=9))
        o.append(f'<text x="{x + 15}" y="352" font-family="{SANS}" font-size="27" font-weight="800" fill="{c}">{val}</text>')
        o.append(f'<text x="{x + 16}" y="371" font-family="{MONO}" font-size="9.5" fill="{INK_4}">{sub}</text>')

    # right: the index, with a reader bar stepping down it
    ix, iy, iw, rh = 640, 68, 600, 38
    o.append(f'<rect x="{ix}" y="{iy}" width="{iw}" height="{rh * n + 46}" rx="10" fill="{PANEL}" stroke="{LINE}"/>')
    o.append(kicker(ix + 18, iy + 24, "INDEX", size=9))
    o.append(kicker(ix + 250, iy + 24, "PROOF, FROM ITS README", size=9))
    o.append(kicker(ix + iw - 18, iy + 24, "STATUS", anchor="end", size=9))
    r0 = iy + 36
    step = 1.8
    ys = ";".join(f"{r0 + i * rh + 3}" for i in range(n))
    kt = ";".join(f"{i / n:.4f}" for i in range(n))
    o.append(f'<rect x="{ix + 8}" y="{r0 + 3}" width="{iw - 16}" height="{rh - 1}" rx="7" fill="{VIOLET}" fill-opacity="0.09" '
             f'stroke="{VIOLET}" stroke-opacity="0.4"><animate attributeName="y" values="{ys}" keyTimes="{kt}" '
             f'calcMode="discrete" dur="{n * step}s" repeatCount="indefinite"/></rect>')
    for i, p in enumerate(ROSTER):
        y = r0 + i * rh + 22
        c = DOMAIN[p["domain"]]
        rr = res.get(p["fleet"]) if p["fleet"] else None
        lab, sc = STATUS[rr["s"] if rr else None]
        o.append(f'<rect x="{ix + 18}" y="{y - 13}" width="3" height="16" rx="1.5" fill="{c}"/>')
        o.append(f'<text x="{ix + 30}" y="{y}" font-family="{MONO}" font-size="10.5" fill="{INK_4}">{i + 1:02d}</text>')
        o.append(f'<text x="{ix + 56}" y="{y}" font-family="{SANS}" font-size="15" font-weight="700" fill="{INK}">'
                 f'{esc(p["name"])}</text>')
        o.append(f'<text x="{ix + 56}" y="{y + 13}" font-family="{MONO}" font-size="8.5" letter-spacing="0.8" fill="{INK_4}">'
                 f'{esc(p["cls"])}</text>')
        o.append(f'<text x="{ix + 250}" y="{y + 4}" font-family="{MONO}" font-size="11" font-weight="700" '
                 f'letter-spacing="0.4" fill="{c}">{esc(p["proof"])}</text>')
        if rr:
            o.append(f'<circle cx="{ix + iw - 98}" cy="{y}" r="3.5" fill="{sc}">{breathe("opacity", "1;0.3;1", "1.6s", f"{i * 0.2:.1f}s")}</circle>')
            o.append(f'<text x="{ix + iw - 18}" y="{y + 4}" text-anchor="end" font-family="{MONO}" font-size="10.5" '
                     f'font-weight="700" fill="{sc}">{fmt_ms(rr["ms"]) if rr["s"] in ("up", "slow") else lab}</text>')
        else:
            o.append(f'<text x="{ix + iw - 18}" y="{y + 4}" text-anchor="end" font-family="{MONO}" font-size="10" '
                     f'fill="{INK_4}">source</text>')
    o.append('</g>')
    o.append(f'<rect x="0.5" y="0.5" width="{CW - 1}" height="{CH - 1}" rx="14" fill="none" stroke="{LINE}"/>')
    o.append('</svg>')
    return "\n".join(o)


# ------------------------------------------------------------------ the rack
# A unit is shown at half the README width (about 520 px), so it is drawn at 600 x 150
# with large type: nothing on it renders smaller than about 9 px.
UW, UH = 600, 150            # one rack unit


def wrap(s, size, width, lines=2):
    words, out, cur = s.split(), [], ""
    for w_ in words:
        if cur and text_w(cur + " " + w_, size) > width:
            out.append(cur)
            cur = w_
        else:
            cur = (cur + " " + w_).strip()
    out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1].rstrip(".,;") + "…"
    return out


def rack_unit(i, p, st, rr):
    col = DOMAIN[p["domain"]]
    lab, sc = STATUS[rr["s"] if rr else None]
    led = sc if rr else INK_4
    commits = (st or {}).get("commits", 0)
    langs = (st or {}).get("langs") or []
    k = f"u{i}"
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {UW} {UH}" width="100%" role="img" aria-labelledby="t{k} d{k}">',
         f'<title id="t{k}">{esc(p["name"])}</title>',
         f'<desc id="d{k}">Rack unit {i + 1:02d}, {esc(p["name"])}, {esc(p["cls"].title())}: {esc(p["pitch"])} Built with '
         f'{esc(", ".join(p["stack"]))}.' + (f' {fmt_bytes(st.get("bytes", 0))} of code, {commits} commits.' if st else "")
         + (f' Live demo {lab.lower()}.' if rr else "") + ' Opens the repository.</desc>',
         f'<defs>{glow(f"g{k}", 1.8)}<clipPath id="c{k}"><rect width="{UW}" height="{UH}" rx="10"/></clipPath>'
         f'<linearGradient id="s{k}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{col}" stop-opacity="0.12"/>'
         f'<stop offset="0.55" stop-color="{col}" stop-opacity="0"/></linearGradient></defs>',
         f'<g clip-path="url(#c{k})">',
         f'<rect width="{UW}" height="{UH}" fill="{PANEL}"/>', f'<rect width="{UW}" height="{UH}" fill="url(#s{k})"/>']
    # rack ears with screws
    ear = 20
    for ex in (0, UW - ear):
        o.append(f'<rect x="{ex}" y="0" width="{ear}" height="{UH}" fill="{PANEL_2}"/>')
        for sy in (26, UH - 26):
            o.append(f'<circle cx="{ex + ear / 2}" cy="{sy}" r="4" fill="{BG}" stroke="{LINE_2}"/>'
                     f'<path d="M{ex + ear / 2 - 2.5} {sy}h5" stroke="{INK_4}" stroke-width="1.1"/>')
    o.append(f'<path d="M{ear} 0V{UH}M{UW - ear} 0V{UH}" stroke="{LINE}"/>')
    o.append(f'<rect x="{ear}" y="0" width="3.5" height="{UH}" fill="{col}"/>')
    # status column
    sx = 47
    o.append(f'<text x="{sx}" y="34" text-anchor="middle" font-family="{MONO}" font-size="10.5" letter-spacing="0.6" '
             f'fill="{INK_3}">U{i + 1:02d}</text>')
    o.append(f'<circle cx="{sx}" cy="66" r="6.5" fill="{led}"' + (
        f' filter="url(#g{k})">{breathe("opacity", "1;0.35;1", "1.8s", f"{(i % 5) * 0.3:.1f}s")}</circle>' if rr else '/>'))
    o.append(f'<text x="{sx}" y="92" text-anchor="middle" font-family="{MONO}" font-size="9.5" font-weight="700" '
             f'letter-spacing="0.6" fill="{sc if rr else INK_3}">'
             f'{"LIVE" if rr and rr["s"] in ("up", "slow") else ("DOWN" if rr else "SRC")}</text>')
    # activity lights: blink faster the more commits the repo has
    rate = max(0.5, 2.6 - math.log10(max(commits, 1)) * 0.9)
    for j in range(4):
        o.append(f'<rect x="{sx - 7 + j * 4.2:.1f}" y="110" width="2.6" height="11" rx="1.2" fill="{col}" opacity="0.25">'
                 f'<animate attributeName="opacity" values="0.2;0.95;0.2" dur="{rate + j * 0.17:.2f}s" '
                 f'begin="{(i * 0.37 + j * 0.23) % 1.5:.2f}s" repeatCount="indefinite"/></rect>')
    o.append(f'<path d="M72 18V{UH - 18}" stroke="{LINE}"/>')
    # faceplate text
    x0, x1 = 88, UW - ear - 16
    o.append(f'<text x="{x0}" y="34" font-family="{MONO}" font-size="{fit(p["cls"], 11, x1 - x0 - 150, mono=True)}" '
             f'font-weight="700" letter-spacing="1.1" fill="{col}">{esc(p["cls"])}</text>')
    if p.get("note"):
        o.append(chip(x1, 35, p["note"], col, size=10))
    o.append(f'<text x="{x0}" y="66" font-family="{SANS}" font-size="{fit(p["name"], 25, x1 - x0, bold=True)}" '
             f'font-weight="800" letter-spacing="-0.3" fill="{INK}">{esc(p["name"])}</text>')
    for m, line in enumerate(wrap(p["pitch"], 14.5, (x1 - x0) / 0.92)):
        o.append(f'<text x="{x0}" y="{90 + m * 19}" font-family="{SANS}" font-size="14.5" fill="{INK_2}">{esc(line)}</text>')
    # language strip and footer
    tot = sum(s for _, s, _ in langs) or 1
    lx, lw = x0, x1 - x0
    for name, size, lc in langs:
        seg = lw * size / tot
        o.append(f'<rect x="{lx:.1f}" y="120" width="{max(seg - 1.5, 1.5):.1f}" height="3" rx="1.5" fill="{lc}" opacity="0.9"/>')
        lx += seg
    if not langs:
        o.append(f'<path d="M{x0} 121H{x1}" stroke="{LINE_2}"/>')
    stack = "  ·  ".join(p["stack"])
    right = f'{fmt_bytes(st.get("bytes", 0))} · {commits} commits' if st else ""
    o.append(f'<text x="{x0}" y="140" font-family="{MONO}" '
             f'font-size="{fit(stack, 11.5, x1 - x0 - text_w(right, 11, mono=True) - 16, mono=True)}" '
             f'fill="{INK_2}">{esc(stack)}</text>')
    if right:
        o.append(f'<text x="{x1}" y="140" text-anchor="end" font-family="{MONO}" font-size="11" fill="{INK_3}">{right}</text>')
    o.append('</g>')
    o.append(f'<rect x="0.5" y="0.5" width="{UW - 1}" height="{UH - 1}" rx="10" fill="none" stroke="{LINE}"/>')
    o.append('</svg>')
    return "\n".join(o)


RW, RH = 1000, 160


def rack_head(runs, stats):
    latest = runs[-1] if runs else {"results": {}, "at": None}
    res = latest.get("results", {})
    last_at = (datetime.fromisoformat(latest["at"].replace("Z", "+00:00")).astimezone(TZ)
               if latest.get("at") else None)
    live = [p for p in RACK if p["fleet"]]
    online = sum(1 for p in live if res.get(p["fleet"], {}).get("s") in ("up", "slow"))
    code = sum(stats.get(p["repo"], {}).get("bytes", 0) for p in RACK)
    commits = sum(stats.get(p["repo"], {}).get("commits", 0) for p in RACK)
    n = len(RACK)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {RW} {RH}" width="100%" role="img" aria-labelledby="rt rd">',
         '<title id="rt">Systems: the rack</title>',
         f'<desc id="rd">{n} more systems, racked one line each below: {online} of {len(live)} live demos online at the '
         f'last health check, {fmt_bytes(code)} of code in {commits:,} commits. Colour marks the domain: agentic systems, '
         f'developer tools, intelligence and ML, products and web.</desc>',
         f'<defs><clipPath id="rfr"><rect width="{RW}" height="{RH}" rx="14"/></clipPath></defs>',
         '<g clip-path="url(#rfr)">', f'<rect width="{RW}" height="{RH}" fill="{BG}"/>',
         blueprint(RW, RH, INDIGO, a_fine=0.02, a_strong=0.05)]
    o.append(kicker(32, 40, f"SYSTEMS  //  THE RACK  ·  {n} UNITS", size=11))
    o.append(stamp(RW - 32, 40, f"{online} / {len(live)} LIVE ONLINE  ·  CHECKED "
                                f"{last_at.strftime('%H:%M') if last_at else '--:--'} {TZ_NAME}"))
    o.append(f'<text x="32" y="90" font-family="{SANS}" font-size="34" font-weight="800" letter-spacing="-0.8" fill="{INK}">'
             f'{WORDS.get(n, str(n)).capitalize()} more systems, racked.</text>')
    o.append(f'<text x="33" y="122" font-family="{SANS}" font-size="15" fill="{INK_3}">One unit per project. A green light '
             f'means its live demo answered the last check.</text>')
    o.append(f'<text x="33" y="146" font-family="{MONO}" font-size="11" letter-spacing="0.8" fill="{INK_4}">'
             f'{fmt_bytes(code)} OF CODE  ·  {commits:,} COMMITS</text>')
    # legend
    for j, key in enumerate(("agentic", "tools", "intel", "product")):
        x = 660 + (j % 2) * 170
        y = 78 + (j // 2) * 26
        o.append(f'<rect x="{x}" y="{y - 11}" width="3.5" height="15" rx="1.5" fill="{DOMAIN[key]}"/>')
        o.append(f'<text x="{x + 12}" y="{y}" font-family="{MONO}" font-size="11.5" letter-spacing="0.8" fill="{INK_2}">'
                 f'{esc(DOMAIN_NAME[key])}</text>')
    o.append('</g>')
    o.append(f'<rect x="0.5" y="0.5" width="{RW - 1}" height="{RH - 1}" rx="14" fill="none" stroke="{LINE}"/>')
    o.append('</svg>')
    return "\n".join(o)


def rack_slug(i, p):
    s = "".join(ch if ch.isalnum() else "-" for ch in p["name"].lower()).strip("-")
    while "--" in s:
        s = s.replace("--", "-")
    return f"{i + 1:02d}-{s}.svg"


def build_all(runs, stats):
    latest = runs[-1] if runs else {"results": {}}
    res = latest.get("results", {})
    n = len(ROSTER) + 1
    sel = {"cover.svg": cover(runs, stats)}
    for k, proj in enumerate(ROSTER):
        r = res.get(proj["fleet"]) if proj["fleet"] else None
        sel[f'{proj["slug"]}.svg'] = sheet(k, proj, stats.get(proj["repo"], {}), r, n)
    sel[f"{n:02d}-more.svg"] = more_sheet(len(ROSTER), n, res)
    rack = {"rack.svg": rack_head(runs, stats)}
    for i, p in enumerate(RACK):
        rr = res.get(p["fleet"]) if p["fleet"] else None
        rack[rack_slug(i, p)] = rack_unit(i, p, stats.get(p["repo"], {}), rr)
    return {OUT_DIR: sel, RACK_DIR: rack}


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
        out = build_all(runs, stats)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: selected works failed, leaving existing files untouched: {e}", file=sys.stderr)
        return 0
    try:
        count = 0
        for folder, files in out.items():
            os.makedirs(folder, exist_ok=True)
            for name, svg in files.items():
                with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                    f.write(svg)
                count += 1
        if not FIXTURE and not NO_SAVE:
            save_history(HISTORY_PATH, runs)
            if fresh:
                with open(STATS_PATH, "w", encoding="utf-8") as f:
                    json.dump(stats, f, indent=1, sort_keys=True)
                    f.write("\n")
        print(f"Wrote {count} files to {', '.join(out)}")
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: failed to write output files: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
