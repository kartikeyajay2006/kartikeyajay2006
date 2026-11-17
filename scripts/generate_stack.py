#!/usr/bin/env python3
"""Generate section 08 "Stack DNA": assets/stack-dna.svg and STACK.md.

The stack, traced. Nothing here is self-declared: every tool on the drawing was
found in the manifests of my public repositories -- package.json,
requirements*.txt, pyproject.toml, Pipfile, Cargo.toml, pom.xml, build.gradle,
docker-compose files, Dockerfiles, GitHub Actions workflows, and the service
settings in each repository's committed .env.example. A tool that no
public repository uses does not appear.

The drawing is a cross-section of a system, six layers from the interface down to
delivery, with the most used tools of each layer. Each tool is a block whose width
is the number of repositories that use it, and its tier is computed from that
count: core (5+ repos), working (2-4) and explored (1). A scanner passes over the
whole stack; then each flagship in turn is spotlit -- the stack dims and only the
tools that repository really uses light up. Below the layers, the language
foundation is drawn to scale by bytes of code.

STACK.md lists every tool with the repositories it was found in, so any block can
be checked.

Environment: GH_TOKEN (the GH_CONTRIB_PAT the other workflows use). Without it, or
if GitHub is unreachable, the last scan saved in data/stack.json is drawn again.
STACK_FIXTURE=1 draws from data/stack.json without scanning.

Never-fail contract: this script always exits 0, and writes files only after a
successful render.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from theme import (BG, CYAN, INDIGO, INK, INK_2, INK_3, INK_4, LINE, LINE_2, LIVE, MONO,  # noqa: E402
                   PANEL, PANEL_2, PINK, SANS, VIOLET, blueprint, breathe, esc, fit, glow, kicker,
                   stamp, text_w)

LOGIN = os.environ.get("GH_LOGIN", "kartikeyajay2006")
TOKEN = os.environ.get("GH_TOKEN", "")
FIXTURE = os.environ.get("STACK_FIXTURE", "") == "1"
DATA_PATH = os.environ.get("STACK_DATA", "data/stack.json")
SVG_PATH = os.environ.get("STACK_SVG", "assets/stack-dna.svg")
MD_PATH = os.environ.get("STACK_MD", "STACK.md")
TZ = timezone(timedelta(hours=5, minutes=30))
UA = f"{LOGIN}-stack-dna"

SKIP_DIRS = ("node_modules/", "vendor/", "venv/", ".venv/", "dist/", "build/", "site-packages/", ".next/",
             "target/", "__pycache__/", "third_party/", "examples/node_modules")
MANIFEST = re.compile(r"(^|/)(package\.json|requirements[^/]*\.txt|pyproject\.toml|Pipfile|setup\.py|Cargo\.toml|"
                      r"pom\.xml|build\.gradle(\.kts)?|(docker-)?compose[^/]*\.ya?ml|Dockerfile[^/]*|go\.mod|"
                      r"render\.yaml|vercel\.json|\.env(\.[\w-]+)?\.(example|sample|template)|env\.example)$")
MAX_FILES = 30

# ------------------------------------------------------------------ the catalogue
# layer -> [(tool, [dependency names]...)]. Names are matched exactly against the
# dependencies a manifest declares (lower-cased, extras and versions stripped), or
# with a trailing * as a prefix. "img:" matches a compose/Docker image, "file:" a
# file anywhere in the tree.
LAYERS = [
    ("INTERFACE", "What people touch", [
        ("React", ["react"]), ("Next.js", ["next"]), ("Vite", ["vite"]),
        ("Tailwind CSS", ["tailwindcss", "@tailwindcss/*"]), ("Three.js", ["three", "@react-three/fiber"]),
        ("Framer Motion", ["framer-motion", "motion"]), ("Tauri", ["@tauri-apps/api", "tauri"]),
        ("xterm.js", ["@xterm/xterm", "xterm"]), ("Streamlit", ["streamlit"]),
        ("TanStack Query", ["@tanstack/react-query"]), ("Recharts", ["recharts"]), ("D3", ["d3"]),
        ("Radix UI", ["@radix-ui/*"]), ("CodeMirror", ["@codemirror/*", "codemirror"]),
    ]),
    ("BACKEND", "APIs and services", [
        ("FastAPI", ["fastapi"]), ("Express", ["express"]), ("Fastify", ["fastify"]), ("Flask", ["flask"]),
        ("SQLAlchemy", ["sqlalchemy"]), ("Pydantic", ["pydantic"]), ("Prisma", ["prisma", "@prisma/client"]),
        ("GraphQL", ["graphql", "strawberry-graphql", "@apollo/server"]), ("Zod", ["zod"]),
        ("WebSockets", ["ws", "websockets", "socket.io", "@fastify/websocket"]), ("Tokio", ["tokio"]),
        ("Celery", ["celery"]),
    ]),
    ("AGENTS", "LLMs, tools, agent loops", [
        ("OpenAI", ["openai"]), ("Anthropic", ["anthropic", "@anthropic-ai/sdk", "env:anthropic*"]),
        ("LangGraph", ["langgraph", "@langchain/langgraph"]),
        ("LangChain", ["langchain", "langchain-*", "@langchain/core", "@langchain/openai", "@langchain/community"]),
        ("MCP", ["mcp", "fastmcp", "@modelcontextprotocol/sdk"]), ("Ollama", ["ollama", "env:ollama*", "img:ollama/*"]),
        ("Groq", ["groq", "groq-sdk", "env:groq*"]), ("Gemini", ["google-generativeai", "google-genai", "@google/generative-ai"]),
        ("LiteLLM", ["litellm"]),
    ]),
    ("MODELS", "Learning, vision, speech", [
        ("PyTorch", ["torch"]), ("TensorFlow", ["tensorflow", "tensorflow-cpu"]),
        ("scikit-learn", ["scikit-learn", "sklearn"]), ("Transformers", ["transformers"]), ("TRL", ["trl"]),
        ("NumPy", ["numpy"]), ("pandas", ["pandas"]), ("OpenCV", ["opencv-python", "opencv-python-headless"]),
        ("Whisper", ["openai-whisper", "faster-whisper"]), ("Tesseract", ["pytesseract", "tesseract.js"]),
        ("Sentence Transformers", ["sentence-transformers"]), ("spaCy", ["spacy"]), ("XGBoost", ["xgboost"]),
        ("Matplotlib", ["matplotlib"]),
    ]),
    ("DATA", "Where state lives", [
        ("PostgreSQL", ["psycopg", "psycopg2", "psycopg2-binary", "asyncpg", "pg", "postgres", "pgvector", "env-val:postgres",
                        "img:postgres", "img:pgvector/*", "img:ankane/pgvector"]),
        ("SQLite", ["better-sqlite3", "sqlite3", "aiosqlite", "rusqlite", "sql.js", "sqlx", "env-val:sqlite"]),
        ("MongoDB", ["mongoose", "mongodb", "pymongo", "motor", "env-val:mongodb"]),
        ("Redis", ["redis", "ioredis", "img:redis", "env:redis*", "env-val:redis"]),
        ("Qdrant", ["qdrant-client", "@qdrant/js-client-rest", "img:qdrant/*", "env:qdrant*"]),
        ("Neo4j", ["neo4j", "neo4j-driver", "img:neo4j", "env:neo4j*"]),
        ("MinIO", ["minio", "img:minio/*", "img:bitnami/minio", "env:minio*"]),
        ("Firebase", ["firebase", "firebase-admin"]), ("Supabase", ["@supabase/supabase-js", "supabase"]),
        ("Kafka", ["kafkajs", "confluent-kafka", "aiokafka", "img:bitnami/kafka", "img:confluentinc/*"]),
    ]),
    ("DELIVERY", "Ship, test and watch", [
        ("Docker", ["file:Dockerfile", "file:compose"]), ("GitHub Actions", ["file:.github/workflows/"]),
        ("Playwright", ["playwright", "@playwright/test", "pytest-playwright"]), ("Vitest", ["vitest"]),
        ("Jest", ["jest"]), ("pytest", ["pytest"]), ("Prometheus", ["prometheus-client", "prom-client",
                                                                     "img:prom/prometheus"]),
        ("Vercel", ["file:vercel.json"]), ("Render", ["file:render.yaml"]), ("ESLint", ["eslint"]),
    ]),
]

# The flagships the trace walks through, in the order of section 04.
TRACE = [("AEGIS", "Sovereign-On_Premise-Agentic-AI-Workbench"), ("JKY Terminal", "jky-terminal"),
         ("JKY-Radar", "JKY-Radar"), ("ForgeSRE", "Agent_that_act-Hackathon"), ("EraseOps", "Wispr_goa_task"),
         ("Evidence Console", "Multimodal-Data-Management-Pipeline-for-RAG-Ready-Systems"),
         ("Chakraview", "multi-layer_orchestation")]

LANG_SKIP = {"Jupyter Notebook", "Dockerfile", "Makefile", "Procfile", "Batchfile", "PowerShell"}


# ------------------------------------------------------------------ scanning
def api(path):
    req = urllib.request.Request(f"https://api.github.com{path}", headers={
        "Authorization": f"bearer {TOKEN}", "Accept": "application/vnd.github+json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def raw(repo, branch, path):
    url = (f"https://raw.githubusercontent.com/{LOGIN}/{urllib.parse.quote(repo)}/{urllib.parse.quote(branch)}/"
           f"{urllib.parse.quote(path)}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read(400_000).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def norm(name):
    name = name.strip().strip("\"'").lower()
    name = re.split(r"[\s\[<>=!~;@(,]", name, maxsplit=1)[0] if not name.startswith("@") else \
        re.split(r"[\s\[<>=!~;(,]", name, maxsplit=1)[0]
    return name.replace("_", "-")


def deps_of(path, text):
    """Dependency names a manifest declares, plus images for compose/Docker files."""
    base = path.rsplit("/", 1)[-1]
    out, images = set(), set()
    try:
        if base == "package.json":
            data = json.loads(text)
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                out.update(k.lower() for k in (data.get(key) or {}))
        elif base.startswith("requirements") or base == "Pipfile":
            for line in text.splitlines():
                line = line.split("#", 1)[0].strip()
                if line and not line.startswith(("-", "[", "http")):
                    out.add(norm(line))
        elif base == "pyproject.toml" or base == "setup.py":
            for m in re.finditer(r"""["']([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*([<>=!~;].*?)?["']""", text):
                out.add(norm(m.group(1)))
            for m in re.finditer(r"^\s*([A-Za-z0-9_.\-]+)\s*=", text, re.M):
                out.add(norm(m.group(1)))
        elif base == "Cargo.toml":
            for m in re.finditer(r"^\s*([A-Za-z0-9_\-]+)\s*=", text, re.M):
                out.add(norm(m.group(1)))
        elif base == "pom.xml":
            out.update(m.group(1).lower() for m in re.finditer(r"<artifactId>([^<]+)</artifactId>", text))
        elif base.startswith("build.gradle"):
            out.update(m.group(1).lower() for m in re.finditer(r"['\"][\w.\-]+:([\w.\-]+):", text))
        elif "env" in base and base.endswith(("example", "sample", "template")):
            # the services a project is wired to, from its committed example config
            for line in text.splitlines():
                m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
                if not m:
                    continue
                out.add("env:" + m.group(1).lower().replace("_", "-"))
                val = m.group(2).lower()
                for scheme in ("sqlite", "postgres", "mongodb", "redis", "neo4j", "bolt"):
                    if scheme + ":" in val or scheme + "+" in val:
                        out.add("env-val:" + scheme)
        elif base.startswith(("docker-compose", "compose")) or base.startswith("Dockerfile"):
            for m in re.finditer(r"(?:image:|FROM)\s+[\"']?([\w./\-]+)", text):
                images.add(m.group(1).lower().split(":")[0].replace("docker.io/", "").replace("library/", ""))
    except Exception:  # noqa: BLE001  (a malformed manifest just contributes nothing)
        pass
    return out, images


def matches(rule, deps, images, paths):
    if rule.startswith("file:"):
        frag = rule[5:]
        if frag == "Dockerfile":
            return any(p.rsplit("/", 1)[-1].startswith("Dockerfile") for p in paths)
        if frag == "compose":
            return any(re.search(r"(^|/)(docker-)?compose[^/]*\.ya?ml$", p) for p in paths)
        if frag.endswith("/"):
            return any(p.startswith(frag) for p in paths)
        return any(p == frag or p.endswith("/" + frag) for p in paths)
    if rule.startswith("img:"):
        pat = rule[4:]
        return any(i == pat or (pat.endswith("*") and i.startswith(pat[:-1])) or i.endswith("/" + pat)
                   for i in images)
    if rule.endswith("*"):
        return any(d.startswith(rule[:-1]) for d in deps)
    return rule in deps


def scan_repo(repo):
    name, branch = repo["name"], repo.get("default_branch") or "main"
    tree = api(f"/repos/{LOGIN}/{urllib.parse.quote(name)}/git/trees/{urllib.parse.quote(branch)}?recursive=1")
    paths = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]
    paths = [p for p in paths if not any(s in p + "/" for s in SKIP_DIRS)]
    mans = [p for p in paths if MANIFEST.search(p)]
    mans.sort(key=lambda p: (p.count("/"), p))
    deps, images = set(), set()
    for p in mans[:MAX_FILES]:
        if p.endswith(("render.yaml", "vercel.json")) or "/fixtures/" in p or "/test" in p:
            continue
        d, i = deps_of(p, raw(name, branch, p))
        deps |= d
        images |= i
    tools = []
    for layer, _, catalogue in LAYERS:
        for tool, rules in catalogue:
            if any(matches(r, deps, images, paths) for r in rules):
                tools.append(tool)
    langs = api(f"/repos/{LOGIN}/{urllib.parse.quote(name)}/languages")
    return name, {"tools": tools, "manifests": len(mans[:MAX_FILES]), "langs": langs}


def scan():
    repos = []
    page = 1
    while True:
        batch = api(f"/users/{LOGIN}/repos?type=owner&per_page=100&page={page}")
        repos += [r for r in batch if not r.get("fork") and not r.get("private") and not r.get("archived")]
        if len(batch) < 100:
            break
        page += 1
    results = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for name, res in pool.map(lambda r: _safe(scan_repo, r), repos):
            if name:
                results[name] = res
    return {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "repos": results}


def _safe(fn, repo):
    for attempt in range(2):
        try:
            return fn(repo)
        except Exception as e:  # noqa: BLE001
            if attempt:
                print(f"WARNING: could not scan {repo.get('name')}: {e}", file=sys.stderr)
            time.sleep(2)
    return None, None


# ------------------------------------------------------------------ model
def model(data):
    repos = data["repos"]
    used = {}
    for name, r in repos.items():
        for t in r["tools"]:
            used.setdefault(t, []).append(name)
    layers = []
    for layer, sub, catalogue in LAYERS:
        tools = [(t, sorted(used[t], key=str.lower)) for t, _ in catalogue if t in used]
        tools.sort(key=lambda x: (-len(x[1]), x[0].lower()))
        layers.append((layer, sub, tools))
    langs = {}
    for r in repos.values():
        for lang, b in (r.get("langs") or {}).items():
            if lang not in LANG_SKIP:
                langs[lang] = langs.get(lang, 0) + b
    return layers, sorted(langs.items(), key=lambda x: -x[1]), used


def tier(n):
    return "core" if n >= 5 else ("working" if n >= 2 else "explored")


# ------------------------------------------------------------------ drawing
# Drawn close to the width GitHub shows it at (about 1000 px), so 14 px type reads as 14 px.
W = 1000
LX0, LX1 = 32, 968           # band area
LABEL_W = 156                # layer label column
BAND_H, BAND_GAP = 58, 10
TOP = 156                    # first band
BLOCK_H = 40
MAX_PER_LAYER = 6
ALL_SLOT = 4.0               # seconds the whole stack is shown, with the scanner pass
SPOT_SLOT = 3.4              # seconds per flagship spotlight


def mix(a, b, t):
    a = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def layer_col(i, n):
    stops = [VIOLET, INDIGO, CYAN]
    t = i / (n - 1)
    return mix(stops[0], stops[1], t * 2) if t <= 0.5 else mix(stops[1], stops[2], (t - 0.5) * 2)


LANG_COL = {"TypeScript": "#3178c6", "Python": "#3572A5", "JavaScript": "#f1e05a", "Rust": "#dea584",
            "CSS": "#663399", "HTML": "#e34c26", "Java": "#b07219", "Shell": "#89e051", "C": "#555555",
            "Go": "#00ADD8"}


def visible(layers):
    return [(layer, sub, tools[:MAX_PER_LAYER], len(tools)) for layer, sub, tools in layers]


def draw(data):
    layers, langs, used = model(data)
    shown = visible(layers)
    n_repos = len(data["repos"])
    n_tools = sum(len(t) for _, _, t in layers)
    manifests = sum(r.get("manifests", 0) for r in data["repos"].values())
    at = datetime.fromisoformat(data["at"].replace("Z", "+00:00")).astimezone(TZ)
    nl = len(shown)
    bands_end = TOP + nl * (BAND_H + BAND_GAP) - BAND_GAP
    cap_y = bands_end + 34
    found_y = cap_y + 26
    H = found_y + 84

    # ---- block geometry: width grows with the number of repos, every label still fits
    geo = {}                 # tool -> (x, y, w, colour, tier, count, font size)
    area0, area1 = LX0 + LABEL_W + 12, LX1 - 10
    for li, (layer, _, tools, _) in enumerate(shown):
        y = TOP + li * (BAND_H + BAND_GAP) + (BAND_H - BLOCK_H) / 2
        col = layer_col(li, nl)
        gap = 8
        mins = [text_w(t, 14, bold=True) + 50 for t, _ in tools]
        weights = [len(r) for _, r in tools]
        avail = area1 - area0 - gap * max(len(tools) - 1, 0)
        extra = max(avail - sum(mins), 0)
        tw = sum(weights) or 1
        widths = [m + extra * w / tw for m, w in zip(mins, weights)]
        scale = min(1.0, avail / sum(widths)) if widths else 1
        x = area0
        for (t, repos), w in zip(tools, widths):
            w *= scale
            fs = fit(t, 14, w - 46, bold=True, floor=11)
            geo[t] = (x, y, w, col, tier(len(repos)), len(repos), fs)
            x += w + gap

    # ---- the spotlight sequence: the whole stack first, then each flagship's own tools
    spots = []
    for name, repo in TRACE:
        r = data["repos"].get(repo)
        if not r:
            continue
        mine = [t for _, _, tools, _ in shown for t, _ in tools if t in r["tools"]]
        if len(mine) >= 3:
            spots.append((name, mine))
    cycle = ALL_SLOT + SPOT_SLOT * len(spots)

    def window(t0, t1):
        """Discrete opacity animation that shows an element only between t0 and t1 seconds."""
        k0, k1 = t0 / cycle, t1 / cycle
        if k0 <= 0:
            return f'values="1;0" keyTimes="0;{k1:.4f}"'
        if k1 >= 1:
            return f'values="0;1" keyTimes="0;{k0:.4f}"'
        return f'values="0;1;0" keyTimes="0;{k0:.4f};{k1:.4f}"'

    def anim(t0, t1):
        return (f'<animate attributeName="opacity" {window(t0, t1)} calcMode="discrete" dur="{cycle:.1f}s" '
                f'repeatCount="indefinite"/>')

    desc_layers = "; ".join(f"{layer.title()}: " + ", ".join(f"{t} ({len(r)})" for t, r in tools)
                            for layer, _, tools, _ in shown if tools)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" aria-labelledby="st sd">',
         '<title id="st">Stack DNA: the stack, traced</title>',
         f'<desc id="sd">The tools found in the manifests of {n_repos} public repositories, drawn as a cross-section '
         f'of a system in six layers, the most used tools of each layer shown. Each block is one tool, its width the '
         f'number of repositories that use it, shown in brackets: {esc(desc_layers)}. Core means five or more '
         f'repositories, working two to four, explored one. A scanner passes over the whole stack, then each flagship '
         f'in turn is spotlit with only the tools it uses: '
         f'{esc("; ".join(f"{n}: {chr(44).join(m)}" for n, m in spots))}. Below, the languages by bytes of code: '
         f'{esc(", ".join(f"{k} {100 * v / max(sum(b for _, b in langs), 1):.0f}%" for k, v in langs[:6]))}.</desc>',
         f'<defs>{glow("sg", 3)}<clipPath id="sfr"><rect width="{W}" height="{H}" rx="14"/></clipPath>'
         f'<clipPath id="sband"><rect x="{area0 - 6}" y="{TOP}" width="{area1 - area0 + 12}" height="{bands_end - TOP}"/></clipPath>'
         f'<radialGradient id="slit" cx="0.85" cy="0" r="0.9"><stop offset="0" stop-color="{CYAN}" stop-opacity="0.09"/>'
         f'<stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></radialGradient>'
         f'<linearGradient id="sink" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#c4b5fd"/>'
         f'<stop offset="0.55" stop-color="{INDIGO}"/><stop offset="1" stop-color="#67e8f9"/></linearGradient>'
         f'<linearGradient id="sbeam" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff" stop-opacity="0"/>'
         f'<stop offset="0.5" stop-color="#ffffff" stop-opacity="0.16"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/>'
         f'</linearGradient></defs>',
         '<g clip-path="url(#sfr)">', f'<rect width="{W}" height="{H}" fill="{BG}"/>',
         f'<rect width="{W}" height="{H}" fill="url(#slit)"/>', blueprint(W, H, INDIGO, a_fine=0.016, a_strong=0.04)]

    # ---- header
    o.append(kicker(LX0, 40, f"STACK DNA  //  TRACED FROM {n_repos} PUBLIC REPOS", size=11))
    o.append(stamp(LX1, 40, f"{manifests} MANIFESTS READ  ·  SCANNED {at.strftime('%-d %b').upper()}"))
    o.append(f'<text x="{LX0}" y="92" font-family="{SANS}" font-size="36" font-weight="800" letter-spacing="-1" '
             f'fill="{INK}">The stack, <tspan fill="url(#sink)">traced.</tspan></text>')
    o.append(f'<text x="{LX0 + 1}" y="122" font-family="{SANS}" font-size="14.5" fill="{INK_3}">Every block is a tool my '
             f'repositories actually use. The wider it is, the more repos use it.</text>')
    # tiers legend, top right
    for j, (name, sub) in enumerate((("CORE", "5+ repos"), ("WORKING", "2–4"), ("EXPLORED", "1"))):
        x = 640 + j * 112
        o.append(_swatch(x, 80, 20, 15, CYAN, name.lower()))
        o.append(f'<text x="{x + 28}" y="92" font-family="{MONO}" font-size="11" letter-spacing="1" fill="{INK_2}">{name}</text>'
                 f'<text x="{x + 28}" y="108" font-family="{MONO}" font-size="10" fill="{INK_4}">{sub}</text>')

    # ---- bands and blocks
    for li, (layer, sub, tools, total) in enumerate(shown):
        y = TOP + li * (BAND_H + BAND_GAP)
        col = layer_col(li, nl)
        o.append(f'<rect x="{LX0}" y="{y}" width="{LX1 - LX0}" height="{BAND_H}" rx="10" fill="{PANEL}" stroke="{LINE}"/>')
        o.append(f'<rect x="{LX0 + 1}" y="{y + 11}" width="3" height="{BAND_H - 22}" rx="1.5" fill="{col}"/>')
        hidden = total - len(tools)
        more = f'<tspan fill="{INK_4}" font-weight="400" font-size="10.5" letter-spacing="0.6">  +{hidden}</tspan>' if hidden > 0 else ""
        o.append(f'<text x="{LX0 + 18}" y="{y + 25}" font-family="{MONO}" font-size="12" font-weight="700" '
                 f'letter-spacing="1.6" fill="{col}">{esc(layer)}{more}</text>')
        o.append(f'<text x="{LX0 + 18}" y="{y + 43}" font-family="{SANS}" font-size="11.5" fill="{INK_4}">{esc(sub)}</text>')
        for t, repos in tools:
            o.append(_block(*geo[t], name_override=t))

    # scanner pass over the whole stack while nothing is spotlit
    o.append(f'<g clip-path="url(#sband)"><rect x="{area0 - 140}" y="{TOP}" width="120" height="{bands_end - TOP}" '
             f'fill="url(#sbeam)" opacity="0"><animate attributeName="x" values="{area0 - 140};{area1 + 20};{area1 + 20}" '
             f'keyTimes="0;{ALL_SLOT * 0.8 / cycle:.4f};1" dur="{cycle:.1f}s" repeatCount="indefinite"/>{anim(0, ALL_SLOT)}'
             f'</rect></g>')

    # spotlights: dim the stack, relight only what this flagship uses
    for i, (name, mine) in enumerate(spots):
        t0 = ALL_SLOT + i * SPOT_SLOT
        g = [f'<g opacity="0">{anim(t0, t0 + SPOT_SLOT)}',
             f'<rect x="{area0 - 6}" y="{TOP}" width="{area1 - area0 + 12}" height="{bands_end - TOP}" fill="{BG}" '
             f'opacity="0.72"/>']
        for t in mine:
            x, y, w, col, tr, cnt, fs = geo[t]
            g.append(_block(x, y, w, col, "core", cnt, fs, name_override=t))
            g.append(f'<rect x="{x - 2:.1f}" y="{y - 2:.1f}" width="{w + 4:.1f}" height="{BLOCK_H + 4}" rx="8" fill="none" '
                     f'stroke="#ffffff" stroke-width="1.6" stroke-opacity="0.9" filter="url(#sg)"/>')
        # caption for this flagship
        g.append(f'<text x="{LX0}" y="{cap_y}" font-family="{MONO}" font-size="11" letter-spacing="1.6" fill="{INK_4}">'
                 f'SPOTLIGHT</text>')
        g.append(f'<text x="{LX0 + 92}" y="{cap_y + 1}" font-family="{SANS}" font-size="16" font-weight="800" '
                 f'fill="{INK}">{esc(name)}</text>')
        g.append(f'<text x="{LX0 + 104 + text_w(name, 16, bold=True):.1f}" y="{cap_y}" font-family="{SANS}" font-size="13.5" '
                 f'fill="{INK_3}">lights the {len(mine)} tools on this map it really uses</text>')
        g.append('</g>')
        o.append("".join(g))
    # the caption while the whole stack is showing (also the still frame)
    o.append(f'<g>{anim(0, ALL_SLOT)}'
             f'<text x="{LX0}" y="{cap_y}" font-family="{MONO}" font-size="11" letter-spacing="1.6" fill="{INK_4}">ALL</text>'
             f'<text x="{LX0 + 92}" y="{cap_y + 1}" font-family="{SANS}" font-size="16" font-weight="800" fill="{INK}">'
             f'{n_tools} tools across {n_repos} repos</text>'
             f'<text x="{LX0 + 104 + text_w(f"{n_tools} tools across {n_repos} repos", 16, bold=True):.1f}" y="{cap_y}" '
             f'font-family="{SANS}" font-size="13.5" fill="{INK_3}">then each flagship lights up the tools it uses</text></g>')
    # progress ticks for the sequence
    for i in range(len(spots) + 1):
        t0 = 0 if i == 0 else ALL_SLOT + (i - 1) * SPOT_SLOT
        t1 = ALL_SLOT if i == 0 else t0 + SPOT_SLOT
        x = LX1 - (len(spots) + 1 - i) * 16
        o.append(f'<rect x="{x}" y="{cap_y - 6}" width="11" height="4" rx="2" fill="{LINE_2}"/>'
                 f'<rect x="{x}" y="{cap_y - 6}" width="11" height="4" rx="2" fill="{CYAN}" opacity="{1 if i == 0 else 0}">'
                 f'{anim(t0, t1)}</rect>')

    # ---- the foundation: languages to scale
    total = sum(b for _, b in langs) or 1
    top = langs[:6]
    other = total - sum(b for _, b in top)
    segs = top + ([("Other", other)] if other > 0 else [])
    o.append(f'<rect x="{LX0}" y="{found_y}" width="{LX1 - LX0}" height="64" rx="10" fill="{PANEL}" stroke="{LINE}"/>')
    o.append(f'<text x="{LX0 + 18}" y="{found_y + 26}" font-family="{MONO}" font-size="12" font-weight="700" '
             f'letter-spacing="1.6" fill="{INK_2}">FOUNDATION</text>')
    o.append(f'<text x="{LX0 + 18}" y="{found_y + 44}" font-family="{SANS}" font-size="11.5" fill="{INK_4}">Languages, by bytes</text>')
    bx0, bx1 = area0, area1
    x = bx0
    for lang, b in segs:
        w = (bx1 - bx0) * b / total
        c = LANG_COL.get(lang, "#6e7681")
        o.append(f'<rect x="{x:.1f}" y="{found_y + 16}" width="{max(w - 2, 1):.1f}" height="10" rx="3" fill="{c}" opacity="0.9"/>')
        label = f"{lang} {100 * b / total:.0f}%"
        if w > text_w(label, 11, mono=True) + 6:
            o.append(f'<text x="{x:.1f}" y="{found_y + 46}" font-family="{MONO}" font-size="11" fill="{INK_3}">{esc(lang)} '
                     f'<tspan fill="{INK_4}">{100 * b / total:.0f}%</tspan></text>')
        x += w
    o.append('</g>')
    o.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="{LINE}"/>')
    o.append('</svg>')
    return "\n".join(o), (n_repos, n_tools, manifests)


def _swatch(x, y, w, h, col, tr):
    if tr == "core":
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{col}" fill-opacity="0.22" stroke="{col}"/>'
    if tr == "working":
        return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{col}" fill-opacity="0.08" stroke="{col}" '
                f'stroke-opacity="0.6"/>')
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="none" stroke="{INK_4}" '
            f'stroke-dasharray="3 3"/>')


def _block(x, y, w, col, tr, count, fs, name_override=None):
    name = name_override
    if name is None:
        raise ValueError("block needs a name")
    o = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{BLOCK_H}" rx="6" fill="{PANEL}"/>',
         _swatch(f"{x:.1f}", f"{y:.1f}", f"{w:.1f}", BLOCK_H, col, tr)]
    ink = INK if tr == "core" else (INK_2 if tr == "working" else INK_3)
    o.append(f'<text x="{x + 13:.1f}" y="{y + BLOCK_H / 2 + 5:.1f}" font-family="{SANS}" font-size="{fs}" '
             f'font-weight="{700 if tr != "explored" else 500}" fill="{ink}">{esc(name)}</text>')
    o.append(f'<text x="{x + w - 11:.1f}" y="{y + BLOCK_H / 2 + 4.5:.1f}" text-anchor="end" font-family="{MONO}" '
             f'font-size="12" font-weight="700" fill="{col if tr != "explored" else INK_4}">{count}</text>')
    return "".join(o)


def markdown(data):
    layers, langs, _ = model(data)
    at = datetime.fromisoformat(data["at"].replace("Z", "+00:00")).astimezone(TZ)
    lines = ["# Stack DNA: where each tool is used", "",
             f"Generated by `scripts/generate_stack.py` from the manifests of {len(data['repos'])} public repositories "
             f"(scanned {at.strftime('%-d %b %Y, %H:%M')} IST). A tool is listed only if a repository's own "
             "package.json, requirements, pyproject, Cargo, Maven/Gradle, compose file, Dockerfile, workflow or "
             "committed .env.example uses it.",
             "", "**Tiers:** core = 5 or more repositories · working = 2 to 4 · explored = 1.", ""]
    for layer, sub, tools in layers:
        if not tools:
            continue
        lines += [f"## {layer.title()} — {sub}", "", "| Tool | Repos | Tier | Used in |", "|:--|--:|:--|:--|"]
        for t, repos in tools:
            links = ", ".join(f"[{r}](https://github.com/{LOGIN}/{r})" for r in repos)
            lines.append(f"| {t} | {len(repos)} | {tier(len(repos))} | {links} |")
        lines.append("")
    total = sum(b for _, b in langs) or 1
    lines += ["## Foundation — languages by bytes of code", "", "| Language | Share |", "|:--|--:|"]
    lines += [f"| {k} | {100 * v / total:.1f}% |" for k, v in langs[:10]]
    return "\n".join(lines) + "\n"


def main():
    data = None
    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            cached = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        cached = None
    fresh = False
    if TOKEN and not FIXTURE:
        try:
            data = scan()
            if len(data["repos"]) < 5:
                raise RuntimeError(f"only {len(data['repos'])} repositories scanned")
            fresh = True
        except Exception as e:  # noqa: BLE001
            print(f"WARNING: scan failed, drawing the last saved scan: {e}", file=sys.stderr)
            data = None
    data = data or cached
    if not data:
        print("WARNING: no scan and no saved scan; nothing drawn.", file=sys.stderr)
        return 0
    try:
        svg, (nr, nt, nm) = draw(data)
        md = markdown(data)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: stack drawing failed, leaving files untouched: {e}", file=sys.stderr)
        return 0
    try:
        os.makedirs(os.path.dirname(SVG_PATH) or ".", exist_ok=True)
        with open(SVG_PATH, "w", encoding="utf-8") as f:
            f.write(svg)
        with open(MD_PATH, "w", encoding="utf-8") as f:
            f.write(md)
        if fresh:
            os.makedirs(os.path.dirname(DATA_PATH) or ".", exist_ok=True)
            with open(DATA_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1, sort_keys=True)
                f.write("\n")
        print(f"Stack DNA: {nt} tools across {nr} repos from {nm} manifests -> {SVG_PATH}, {MD_PATH}")
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: failed to write output files: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
