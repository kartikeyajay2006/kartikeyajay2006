#!/usr/bin/env python3
"""Generate assets/fleet-status.svg — a status page for every deployed project.

Each run (GitHub Actions: every 3 hours and on every push) requests each
deployment's public URL from the runner and, where the app exposes one, its
own health endpoint. The result is appended to data/fleet-history.json and
the board is redrawn from that history:

  - status per deployment: UP (answered in under 3 s), COLD (answered, but
    only after 3 s or on a retry; free tiers and serverless APIs sleep when
    idle and wake on the first request), PARTIAL (the page answered but the app's health endpoint
    reported a problem) or DOWN (an error, a timeout, or a redirect to a
    login wall instead of the app)
  - the last STRIP checks as an uptime strip, and uptime over the stored
    history (UP and COLD count as up)
  - the latest response time
  - for apps with a health endpoint, which layers the app itself vouched for:
    the page, the API and the database (plus the engine version it reports)

Nothing here is self-reported: every number comes from a request made by the
runner. Stdlib-only, no token needed.

SVG notes (see generate_signal.py): GitHub strips <script> and inline <style>,
so all motion is SMIL and every animated element carries its own values.
Everything readable starts visible.

Local preview: FLEET_FIXTURE=<history.json> renders that history without
making any request; FLEET_NO_SAVE=1 checks live but leaves the history file
alone.

Never-fail contract: this script always exits 0. Any problem is logged to
stderr, and the SVG and history files are only written after a successful
render.
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
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

OUT_PATH = os.environ.get("OUT_PATH", "assets/fleet-status.svg")
HISTORY_PATH = os.environ.get("HISTORY_PATH", "data/fleet-history.json")
FIXTURE = os.environ.get("FLEET_FIXTURE", "")
NO_SAVE = os.environ.get("FLEET_NO_SAVE", "") == "1"

TZ = timezone(timedelta(hours=5, minutes=30))
TZ_NAME = "IST"
CADENCE_H = 3
KEEP_RUNS = 240          # 30 days at one run every 3 hours
STRIP = 40               # checks drawn per row
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
    code, final, ms, _, err = fetch(dep["url"], timeout)
    if err or not (200 <= code < 400) or login_wall(dep["url"], final):
        time.sleep(5)  # one retry, so a single dropped packet does not paint a red bar
        code, final, ms, _, err = fetch(dep["url"], timeout)
    out = {"code": code, "ms": ms}
    page_ok = not err and 200 <= code < 400 and not login_wall(dep["url"], final)
    if not page_ok:
        out["s"] = "down"
        out["why"] = "login wall" if (not err and login_wall(dep["url"], final)) else (err or f"HTTP {code}")
        return dep["id"], out
    out["s"] = "up" if ms < SLOW_MS else "slow"
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


# ------------------------------------------------------------------ helpers
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def text(x, y, s, size=10, fill=INK3, anchor="start", family=MONO, weight=400, spacing=None, extra=""):
    ls = f' letter-spacing="{spacing}"' if spacing is not None else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}"{ls}{extra}>{s}</text>')


def micro(x, y, s, fill=INK3, anchor="start", size=9):
    return text(x, y, esc(s), size=size, fill=fill, anchor=anchor, spacing=1.3)


def anim(attr, values, dur, begin="0s"):
    n = len(values.split(";"))
    kt = ";".join(f"{i / (n - 1):.3f}" for i in range(n))
    return (f'<animate attributeName="{attr}" values="{values}" keyTimes="{kt}" calcMode="spline" '
            f'keySplines="{";".join([EASE] * (n - 1))}" dur="{dur}" begin="{begin}" repeatCount="indefinite"/>')


def reveal(delay, dur=0.35):
    k = delay / (delay + dur)
    return (f'<animate attributeName="opacity" values="0;0;1" keyTimes="0;{k:.3f};1" dur="{delay + dur:.2f}s" '
            f'fill="freeze"/>')


def fmt_ms(ms):
    return f"{ms / 1000:.1f} s" if ms >= 1000 else f"{ms} ms"


def fmt_pct(x):
    return "100%" if x >= 1 else f"{x * 100:.1f}%"


def host_of(url):
    h = urllib.parse.urlparse(url)
    return (h.hostname or "") + (h.path.rstrip("/") if h.path not in ("", "/") else "")


# ------------------------------------------------------------------ render: the vitals monitor
# Health checks drawn as what they are named after: vital signs. Every
# deployment is one ECG channel on a patient monitor. Its rhythm comes from
# its latest check (normal, slow, irregular or a flatline), its numerics are
# the measured response time and uptime, and one sweep redraws every channel
# the way a bedside monitor does: a write-head with a glowing trail and an
# erase gap running ahead of it.
SCREEN = "#020a06"
PHOS = {"up": "#3dff9a", "slow": "#ffc53d", "partial": "#ff8a3d", "down": "#ff4d5e", None: "#3f6b55"}
WORD = {"up": "NORMAL", "slow": "SLOW", "partial": "IRREGULAR", "down": "NO SIGNAL"}
DIM, DIM2, PALE = "#3f6b55", "#2a4a3a", "#c8f5dc"
TX0, TX1 = 222, 688            # trace window
VTOP, VROW = 150, 34           # first channel, channel pitch
SWEEP = 5.2                    # seconds per sweep
SHORT = {"evidence": "Evidence Console", "club-ideas": "AI-ML Club ideas", "jky-terminal": "JKY Terminal site"}

# one heartbeat, as (fraction of the beat, height as a share of the R wave; negative is up)
PQRST = [(0.0, 0), (0.07, 0), (0.095, -0.12), (0.12, -0.17), (0.145, -0.12), (0.17, 0), (0.215, 0),
         (0.235, 0.13), (0.262, -1.0), (0.29, 0.32), (0.315, 0), (0.40, 0), (0.44, -0.18), (0.48, -0.27),
         (0.52, -0.19), (0.56, 0), (1.0, 0)]


def _beats(status, phase, seed):
    """Beat start positions and (interval, amplitude) for a channel's rhythm."""
    rnd = random.Random(seed)
    if status == "slow":
        base, amp = 104.0, 11.0
    elif status == "partial":
        base, amp = 66.0, 12.5
    else:
        base, amp = 68.0, 15.0
    out, x, n = [], TX0 - phase, 0
    while x < TX1 + base:
        interval = base
        dropped = False
        if status == "partial":
            interval = base * rnd.choice((0.72, 0.85, 1.2, 1.35))
            dropped = n % 5 == 3
        elif status == "up":
            interval = base * rnd.uniform(0.96, 1.04)
        out.append((x, interval, 0.0 if dropped else amp * rnd.uniform(0.9, 1.05)))
        x += interval
        n += 1
    return out


def trace_points(status, baseline, phase, seed):
    pts = []
    if status in ("down", None):
        rnd = random.Random(seed)
        x = TX0
        while x <= TX1:
            pts.append((x, baseline + (rnd.uniform(-0.7, 0.7) if status == "down" else 0)))
            x += 6
        if pts[-1][0] < TX1:
            pts.append((TX1, baseline))
        return pts
    for start, interval, amp in _beats(status, phase, seed):
        for u, k in PQRST:
            pts.append((start + u * interval, baseline + k * amp))
    # clip to the trace window, interpolating at both edges
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x1 < TX0 or x0 > TX1:
            continue
        if x0 < TX0 <= x1 and x1 > x0:
            out.append((TX0, y0 + (y1 - y0) * (TX0 - x0) / (x1 - x0)))
        elif TX0 <= x0 <= TX1:
            if not out or out[-1][0] < x0:
                out.append((x0, y0))
        if x0 <= TX1 < x1:
            out.append((TX1, y0 + (y1 - y0) * (TX1 - x0) / (x1 - x0)))
    if out and out[-1][0] < TX1:
        out.append((TX1, out[-1][1]))
    return out


def motion_keys(pts, samples=48):
    """keyTimes / keyPoints so a dot moving along the polyline keeps a constant x speed."""
    cum = [0.0]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.hypot(x1 - x0, y1 - y0))
    total = cum[-1] or 1.0
    times, points, j = [], [], 0
    for s in range(samples + 1):
        x = TX0 + (TX1 - TX0) * s / samples
        while j < len(pts) - 2 and pts[j + 1][0] < x:
            j += 1
        (x0, y0), (x1, y1) = pts[j], pts[j + 1]
        f = 0.0 if x1 == x0 else max(0.0, min(1.0, (x - x0) / (x1 - x0)))
        length = cum[j] + f * (cum[j + 1] - cum[j])
        times.append(f"{s / samples:.4f}")
        points.append(f"{min(1.0, max(0.0, length / total)):.4f}")
    for i in range(1, len(points)):  # keep keyPoints monotonic after rounding
        if float(points[i]) < float(points[i - 1]):
            points[i] = points[i - 1]
    return ";".join(times), ";".join(points)


def mini_wave(x, y, status, w=26):
    if status == "down":
        return f'<line x1="{x}" y1="{y}" x2="{x + w}" y2="{y}" stroke="{PHOS[status]}" stroke-width="1.3"/>'
    amp = {"up": 7, "slow": 5, "partial": 6}[status]
    if status == "partial":
        pts = [(0, 0), (4, 0), (5.5, 1), (7, -amp), (8.5, 2), (10, 0), (17, 0), (18.5, 1), (20, -amp * 0.6), (21.5, 1.5), (23, 0), (w, 0)]
    elif status == "slow":
        pts = [(0, 0), (9, 0), (10.5, 1), (12, -amp), (13.5, 2), (15, 0), (w, 0)]
    else:
        pts = [(0, 0), (3, 0), (4.5, 1), (6, -amp), (7.5, 2), (9, 0), (15, 0), (16.5, 1), (18, -amp), (19.5, 2), (21, 0), (w, 0)]
    poly = " ".join(f"{x + a:.1f},{y + b:.1f}" for a, b in pts)
    return f'<polyline points="{poly}" fill="none" stroke="{PHOS[status]}" stroke-width="1.3" stroke-linejoin="round"/>'


def build(runs):
    if not runs:
        raise ValueError("no checks recorded yet")
    latest = runs[-1]
    last_at = datetime.fromisoformat(latest["at"].replace("Z", "+00:00")).astimezone(TZ)
    first_at = datetime.fromisoformat(runs[0]["at"].replace("Z", "+00:00")).astimezone(TZ)
    deps = [d for d in DEPLOYMENTS if d["id"] in latest["results"]]
    n = len(deps)
    res = latest["results"]
    ok_now = sum(1 for d in deps if res[d["id"]]["s"] in ("up", "slow"))
    up_ms = sorted(res[d["id"]]["ms"] for d in deps if res[d["id"]]["s"] in ("up", "slow", "partial"))
    median = up_ms[len(up_ms) // 2] if up_ms else 0
    total = good = 0
    for r in runs:
        for d in deps:
            v = r["results"].get(d["id"])
            if v:
                total += 1
                good += v["s"] in ("up", "slow")
    uptime = good / total if total else 0
    alarms = [d for d in deps if res[d["id"]]["s"] in ("down", "partial")]
    H = VTOP + n * VROW + 66
    trace_top, trace_bot = VTOP - 4, VTOP + n * VROW
    p = []

    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-labelledby="fleetTitle fleetDesc">')
    p.append('<title id="fleetTitle">Vitals — every deployed project on a patient monitor</title>')
    rows_txt = "; ".join(
        f'{d["name"]}: {WORD[res[d["id"]]["s"]].lower()}, {fmt_ms(res[d["id"]]["ms"]) if res[d["id"]]["s"] != "down" else "no response"}'
        for d in deps)
    head_txt = "all rhythms normal" if not alarms else f"{len(alarms)} alarm{'s' if len(alarms) > 1 else ''}"
    p.append(f'<desc id="fleetDesc">A bedside-monitor view of {n} deployments, each an ECG channel whose rhythm '
             f'comes from its latest health check: {head_txt}. Checked from GitHub Actions every {CADENCE_H} hours; '
             f'last run {last_at.strftime("%d %b %Y %H:%M")} {TZ_NAME}. Median response {fmt_ms(median)}; uptime '
             f'{uptime * 100:.1f}% across {len(runs)} runs since {first_at.strftime("%d %b %Y")}. {esc(rows_txt)}.</desc>')

    p.append(f'''<defs>
    <linearGradient id="vBezel" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#26272d"/><stop offset="0.5" stop-color="#15161a"/><stop offset="1" stop-color="#0c0d10"/></linearGradient>
    <pattern id="vGrid" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M10,0 L0,0 0,10" fill="none" stroke="#0a2215" stroke-width="0.6"/></pattern>
    <pattern id="vGridMajor" width="50" height="50" patternUnits="userSpaceOnUse"><path d="M50,0 L0,0 0,50" fill="none" stroke="#0d2e1c" stroke-width="0.8"/></pattern>
    <pattern id="vScan" width="4" height="3" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#000" opacity="0.38"/></pattern>
    <radialGradient id="vVignette" cx="0.5" cy="0.5" r="0.8"><stop offset="0.62" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.5"/></radialGradient>
    <linearGradient id="vGlare" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff" stop-opacity="0.06"/><stop offset="0.35" stop-color="#ffffff" stop-opacity="0"/></linearGradient>
    <linearGradient id="vRoll" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3dff9a" stop-opacity="0"/><stop offset="0.5" stop-color="#3dff9a" stop-opacity="0.05"/><stop offset="1" stop-color="#3dff9a" stop-opacity="0"/></linearGradient>
    <linearGradient id="vHeadGrad" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#000"/><stop offset="1" stop-color="#fff"/></linearGradient>
    <filter id="vGlow" x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="1.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <filter id="vGlowBig" x="-300%" y="-300%" width="700%" height="700%"><feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <clipPath id="vScreen"><rect x="12" y="12" width="{W - 24}" height="{H - 24}" rx="11"/></clipPath>
    <clipPath id="vTraces"><rect x="{TX0 - 2}" y="{trace_top}" width="{TX1 - TX0 + 3}" height="{trace_bot - trace_top}"/></clipPath>
    <mask id="vHeadMask" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">
      <rect x="{TX0 - 90}" y="{trace_top}" width="90" height="{trace_bot - trace_top}" fill="url(#vHeadGrad)">
        <animate attributeName="x" values="{TX0 - 90};{TX1 - 90}" dur="{SWEEP}s" repeatCount="indefinite"/></rect>
    </mask>
  </defs>''')

    # bezel and screen
    p.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="18" fill="url(#vBezel)" stroke="#2c2d33"/>')
    p.append(f'<rect x="12" y="12" width="{W - 24}" height="{H - 24}" rx="11" fill="{SCREEN}" stroke="#000" stroke-width="2"/>')
    p.append('<g clip-path="url(#vScreen)">')
    p.append(f'<rect x="12" y="12" width="{W - 24}" height="{H - 24}" fill="url(#vGrid)"/>')
    p.append(f'<rect x="12" y="12" width="{W - 24}" height="{H - 24}" fill="url(#vGridMajor)"/>')

    # ---- header strip
    p.append(f'<text x="30" y="38" font-family="{MONO}" font-size="11" font-weight="700" letter-spacing="2.2" fill="{PHOS["up"]}">'
             f'VITALS</text>')
    p.append(f'<text x="92" y="38" font-family="{MONO}" font-size="10" letter-spacing="1.5" fill="{DIM}">'
             f'// {n} CHANNELS · CHECKED EVERY {CADENCE_H} H BY GITHUB ACTIONS</text>')
    # alarm banner
    if alarms:
        alarms.sort(key=lambda d: res[d["id"]]["s"] != "down")  # flatlines first
        col = PHOS[res[alarms[0]["id"]]["s"]]
        names = ", ".join(SHORT.get(d["id"], d["name"]) for d in alarms[:2]) + (f" +{len(alarms) - 2}" if len(alarms) > 2 else "")
        msg = f"▲ ALARM · {names}"
    else:
        col, msg = PHOS["up"], "■ ALL RHYTHMS NORMAL"
    bw = len(msg) * 7.75 + 24
    p.append(f'<rect x="{W - 28 - bw:.1f}" y="24" width="{bw:.1f}" height="20" rx="3" fill="{col}" fill-opacity="0.12" '
             f'stroke="{col}" stroke-opacity="0.6"/>')
    blink = (f'<animate attributeName="opacity" values="1;1;0.25;0.25" keyTimes="0;0.5;0.55;1" dur="1.1s" repeatCount="indefinite"/>'
             if alarms else "")
    p.append(f'<text x="{W - 28 - bw / 2:.1f}" y="38" text-anchor="middle" font-family="{MONO}" font-size="10.5" font-weight="700" '
             f'letter-spacing="1.4" fill="{col}">{blink}{esc(msg)}</text>')

    # ---- big numerics
    ny0 = 56
    p.append(f'<line x1="24" y1="{ny0}" x2="{W - 24}" y2="{ny0}" stroke="#0f3322"/>')
    boxes = [("RESPONSE · MEDIAN", fmt_ms(median).split(" ")[0], fmt_ms(median).split(" ")[1], PHOS["up"]),
             ("UPTIME", f"{uptime * 100:.1f}" if uptime < 1 else "100", "%", "#22e5ff"),
             ("CHANNELS UP", f"{ok_now}/{n}", "", "#ffe14d"),
             ("LAST CHECK", last_at.strftime("%H:%M"), f"{TZ_NAME} · {last_at.strftime('%d %b').upper()}", "#c084fc")]
    bwid = (W - 48) / 4
    for i, (lab, val, unit, c) in enumerate(boxes):
        bx = 24 + i * bwid
        if i:
            p.append(f'<line x1="{bx:.1f}" y1="{ny0 + 10}" x2="{bx:.1f}" y2="{ny0 + 70}" stroke="#0f3322"/>')
        p.append(f'<text x="{bx + 14:.1f}" y="{ny0 + 22}" font-family="{MONO}" font-size="9" letter-spacing="1.4" fill="{c}" opacity="0.8">{esc(lab)}</text>')
        p.append(f'<text x="{bx + 12:.1f}" y="{ny0 + 60}" font-family="{SANS}" font-size="36" font-weight="700" fill="{c}" '
                 f'filter="url(#vGlow)">{esc(val)}<tspan font-family="{MONO}" font-size="11" font-weight="400" dx="6" '
                 f'fill="{c}" opacity="0.75">{esc(unit)}</tspan></text>')
    p.append(f'<line x1="24" y1="{ny0 + 80}" x2="{W - 24}" y2="{ny0 + 80}" stroke="#0f3322"/>')

    # ---- channels
    traces, heads, dots = [], [], []
    for i, d in enumerate(deps):
        y0 = VTOP + i * VROW
        r = res[d["id"]]
        st = r["s"]
        col = PHOS[st]
        base = y0 + 23
        if st in ("down", "partial"):
            p.append(f'<rect x="14" y="{y0 - 3}" width="{W - 28}" height="{VROW}" fill="{col}" opacity="0.06"/>')
        if i:
            p.append(f'<line x1="24" y1="{y0 - 3}" x2="{W - 24}" y2="{y0 - 3}" stroke="#0b2618"/>')
        # label
        label = SHORT.get(d["id"], d["name"])
        p.append(f'<text x="30" y="{y0 + 13}" font-family="{SANS}" font-size="12" font-weight="700" fill="{col}">'
                 f'{esc(label)}</text>')
        if "api" in r:
            lx_ = 30 + len(label) * 7.1 + 10
            for lab, ok in (("API", r["api"]), ("DB", r.get("db"))):
                if ok is None:
                    continue
                lc = PHOS["up"] if ok and st != "down" else PHOS["down"]
                p.append(f'<circle cx="{lx_:.1f}" cy="{y0 + 9.5}" r="2.2" fill="{lc}" filter="url(#vGlowBig)"/>')
                p.append(f'<text x="{lx_ + 5:.1f}" y="{y0 + 12.5}" font-family="{MONO}" font-size="8" fill="{DIM}">{lab}</text>')
                lx_ += 12 + len(lab) * 5.2
        host = host_of(d["url"])
        if len(host) > 30:
            host = host[:29] + "…"
        p.append(f'<text x="30" y="{y0 + 26}" font-family="{MONO}" font-size="8" fill="{DIM}">{esc(host)}</text>')
        # trace
        pts = trace_points(st, base, (i * 37) % 68, seed=zlib.crc32(d["id"].encode()))
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        traces.append(f'<polyline points="{poly}" fill="none" stroke="{col}" stroke-width="1.5" stroke-linejoin="round" '
                      f'stroke-linecap="round" opacity="0.85"/>')
        heads.append(f'<polyline points="{poly}" fill="none" stroke="#eafff4" stroke-width="2.2" stroke-linejoin="round" '
                     f'stroke-linecap="round"/>')
        kt, kp = motion_keys(pts)
        path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        dots.append(f'<circle r="2.6" fill="#ffffff" opacity="0" filter="url(#vGlowBig)">'
                    f'<set attributeName="opacity" to="1" begin="0s"/>'
                    f'<animateMotion path="{path}" dur="{SWEEP}s" repeatCount="indefinite" calcMode="linear" '
                    f'keyTimes="{kt}" keyPoints="{kp}"/></circle>')
        if st == "down":
            p.append(f'<text x="{(TX0 + TX1) / 2:.1f}" y="{base - 6}" text-anchor="middle" font-family="{MONO}" font-size="10" '
                     f'font-weight="700" letter-spacing="3" fill="{col}">NO SIGNAL{blink if alarms else ""}</text>')
        # numerics
        if st == "down":
            val, unit = "---", ""
        else:
            val, unit = fmt_ms(r["ms"]).split(" ")
        p.append(f'<text x="782" y="{y0 + 24}" text-anchor="end" font-family="{SANS}" font-size="21" font-weight="700" '
                 f'fill="{col}" filter="url(#vGlow)">{esc(val)}</text>')
        p.append(f'<text x="786" y="{y0 + 24}" font-family="{MONO}" font-size="9" fill="{col}" opacity="0.7">{esc(unit)}</text>')
        seen = [rr["results"][d["id"]] for rr in runs if d["id"] in rr["results"]]
        up_pct = sum(v["s"] in ("up", "slow") for v in seen) / max(1, len(seen))
        p.append(f'<text x="{W - 30}" y="{y0 + 13}" text-anchor="end" font-family="{MONO}" font-size="9" font-weight="700" '
                 f'letter-spacing="1" fill="{col}">{WORD[st]}</text>')
        p.append(f'<text x="{W - 30}" y="{y0 + 26}" text-anchor="end" font-family="{MONO}" font-size="8" fill="{DIM}">'
                 f'UPTIME {fmt_pct(up_pct)}</text>')

    p.append(f'<g clip-path="url(#vTraces)">')
    p.append(f'<g filter="url(#vGlow)">{"".join(traces)}</g>')
    # erase gap running just ahead of the write-head
    p.append(f'<rect x="{TX0}" y="{trace_top}" width="16" height="{trace_bot - trace_top}" fill="{SCREEN}">'
             f'<animate attributeName="x" values="{TX0 + 2};{TX1 + 2}" dur="{SWEEP}s" repeatCount="indefinite"/></rect>')
    p.append(f'<g mask="url(#vHeadMask)" filter="url(#vGlow)">{"".join(heads)}</g>')
    p.append("".join(dots))
    p.append('</g>')

    # ---- footer legend: what each rhythm means
    fy = H - 30
    p.append(f'<line x1="24" y1="{fy - 18}" x2="{W - 24}" y2="{fy - 18}" stroke="#0f3322"/>')
    lx = 30
    for st, lab in (("up", "normal · under 3 s"), ("slow", "slow · woke up"),
                    ("partial", "irregular · API/DB failing"), ("down", "flatline · no answer")):
        p.append(mini_wave(lx, fy, st))
        p.append(f'<text x="{lx + 32}" y="{fy + 3}" font-family="{MONO}" font-size="8.5" fill="{DIM}">{esc(lab)}</text>')
        lx += 32 + len(lab) * 5.1 + 24
    p.append(f'<text x="{W - 30}" y="{fy + 3}" text-anchor="end" font-family="{MONO}" font-size="8.5" fill="{DIM2}">'
             f'{len(runs)} RUNS · UPTIME SINCE {first_at.strftime("%d %b %Y").upper()}</text>')

    # ---- CRT: scanlines, slow roll band, vignette, glare
    p.append(f'<rect x="12" y="12" width="{W - 24}" height="{H - 24}" fill="url(#vScan)"/>')
    p.append(f'<rect x="12" y="-120" width="{W - 24}" height="120" fill="url(#vRoll)">'
             f'<animate attributeName="y" values="-120;{H}" dur="7s" repeatCount="indefinite"/></rect>')
    p.append(f'<rect x="12" y="12" width="{W - 24}" height="{H - 24}" fill="url(#vVignette)"/>')
    p.append(f'<rect x="12" y="12" width="{W - 24}" height="{H - 24}" fill="url(#vGlare)"/>')
    p.append('</g>')
    # bezel details: power LED and model plate
    p.append(f'<circle cx="{W - 26}" cy="{H - 6}" r="2" fill="#22c55e" filter="url(#vGlowBig)">{anim("opacity", "1;0.35;1", "2.4s")}</circle>')
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
        svg = build(runs)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: fleet status failed, leaving existing files untouched: {e}", file=sys.stderr)
        return 0
    try:
        os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            f.write(svg)
        if not FIXTURE and not NO_SAVE:
            save_history(HISTORY_PATH, runs)
        print(f"Wrote {OUT_PATH}")
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: failed to write fleet files: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
