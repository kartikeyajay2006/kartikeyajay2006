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
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
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
COLORS = {"up": "#22c55e", "slow": "#f59e0b", "partial": "#f97316", "down": "#ef4444", None: "#1c1c22"}
LABELS = {"up": "UP", "slow": "COLD", "partial": "PARTIAL", "down": "DOWN"}

TOP, ROW_H = 160, 38


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


# ------------------------------------------------------------------ render
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
    H = TOP + n * ROW_H + 58
    p = []

    if ok_now == n:
        headline, head_col = "All systems operational", "#22c55e"
    elif ok_now >= n - 1:
        headline, head_col = f"{ok_now} of {n} operational", "#f59e0b"
    else:
        headline, head_col = f"{n - ok_now} deployments need attention", "#ef4444"

    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" '
             f'aria-labelledby="fleetTitle fleetDesc">')
    p.append('<title id="fleetTitle">Fleet status — every deployed project, health-checked</title>')
    rows_txt = "; ".join(
        f'{d["name"]}: {LABELS[res[d["id"]]["s"]]}, {fmt_ms(res[d["id"]]["ms"])}' for d in deps)
    p.append(f'<desc id="fleetDesc">{esc(headline)}. {n} deployments checked from GitHub Actions every '
             f'{CADENCE_H} hours; last run {last_at.strftime("%d %b %Y %H:%M")} {TZ_NAME}. Uptime '
             f'{uptime * 100:.1f}% across {len(runs)} runs since {first_at.strftime("%d %b %Y")}. '
             f'Median response {fmt_ms(median)}. {esc(rows_txt)}.</desc>')
    p.append(f'''<defs>
    <pattern id="fltDots" width="26" height="26" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="0.9" fill="#151518"/></pattern>
    <filter id="fltGlow" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <linearGradient id="fltBand" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{head_col}" stop-opacity="0.14"/><stop offset="0.6" stop-color="{head_col}" stop-opacity="0.03"/><stop offset="1" stop-color="{head_col}" stop-opacity="0"/></linearGradient>
  </defs>''')
    p.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="#0a0a0a" stroke="#1f1f1f"/>')
    p.append(f'<rect x="14" y="14" width="{W - 28}" height="{H - 28}" fill="url(#fltDots)"/>')

    # header
    p.append(micro(22, 30, "FLEET // LIVE", "#5a5a63", size=10))
    p.append(f'<circle cx="{W - 26}" cy="26.5" r="3" fill="#22c55e" filter="url(#fltGlow)">{anim("opacity", "1;0.3;1", "1.8s")}</circle>')
    p.append(micro(W - 36, 30, f"{n} DEPLOYMENTS · CHECKED EVERY {CADENCE_H} H BY GITHUB ACTIONS · LAST RUN "
                               f"{last_at.strftime('%d %b %H:%M').upper()} {TZ_NAME}", "#5a5a63", "end", 10))

    # summary band with a heartbeat trace
    by0, bh = 46, 70
    p.append(f'<rect x="20" y="{by0}" width="{W - 40}" height="{bh}" rx="12" fill="#0f0f13" stroke="#1f1f25"/>')
    p.append(f'<rect x="20" y="{by0}" width="{W - 40}" height="{bh}" rx="12" fill="url(#fltBand)"/>')
    cx0, cy0 = 54, by0 + bh / 2
    p.append(f'<circle cx="{cx0}" cy="{cy0}" r="15" fill="{head_col}" opacity="0.16"/>')
    p.append(f'<circle cx="{cx0}" cy="{cy0}" r="15" fill="none" stroke="{head_col}" stroke-width="1.2" opacity="0.6">'
             f'{anim("r", "15;22;15", "2.4s")}{anim("opacity", "0.6;0;0.6", "2.4s")}</circle>')
    if ok_now == n:
        p.append(f'<polyline points="{cx0 - 6},{cy0} {cx0 - 1.5},{cy0 + 4.5} {cx0 + 7},{cy0 - 5}" fill="none" '
                 f'stroke="{head_col}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>')
    else:
        p.append(f'<line x1="{cx0}" y1="{cy0 - 7}" x2="{cx0}" y2="{cy0 + 2}" stroke="{head_col}" stroke-width="2.4" stroke-linecap="round"/>'
                 f'<circle cx="{cx0}" cy="{cy0 + 6.5}" r="1.6" fill="{head_col}"/>')
    p.append(text(82, by0 + 31, esc(headline), size=21, fill=INK, family=SANS, weight=700, spacing=-0.3))
    p.append(text(83, by0 + 51, esc(f"{ok_now} of {n} up on the last run · since {first_at.strftime('%d %b %Y')}"),
                  size=10.5, fill=INK3))
    # heartbeat: an ECG trace that keeps drawing itself
    hx0, hx1, hy = 398, 528, by0 + bh / 2
    seg = (hx1 - hx0) / 3
    pts = []
    for k in range(3):
        a = hx0 + k * seg
        pts += [(a, hy), (a + seg * 0.38, hy), (a + seg * 0.46, hy - 4), (a + seg * 0.52, hy + 3),
                (a + seg * 0.58, hy - 15), (a + seg * 0.65, hy + 9), (a + seg * 0.72, hy), (a + seg, hy)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    plen = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    p.append(f'<polyline points="{poly}" fill="none" stroke="{head_col}" stroke-width="1" opacity="0.18"/>')
    p.append(f'<polyline points="{poly}" fill="none" stroke="{head_col}" stroke-width="1.6" stroke-linejoin="round" '
             f'stroke-linecap="round" stroke-dasharray="{plen * 0.22:.0f} {plen:.0f}" filter="url(#fltGlow)">'
             f'<animate attributeName="stroke-dashoffset" values="{plen * 0.22:.0f};{-plen:.0f}" dur="3.2s" '
             f'repeatCount="indefinite"/></polyline>')
    # three numbers on the right of the band
    stats = [("MEDIAN RESPONSE", fmt_ms(median)), ("UPTIME", fmt_pct(uptime)), ("RUNS", f"{len(runs)}")]
    sx = W - 40
    for lab, val in reversed(stats):
        p.append(micro(sx, by0 + 27, lab, INK4, "end", 8.5))
        p.append(text(sx, by0 + 50, esc(val), size=19, fill=INK, anchor="end", family=SANS, weight=700))
        sx -= 112

    # column heads
    sx0 = 300
    bar_w, bar_gap = 4.6, 1.9
    p.append(micro(40, TOP - 14, "DEPLOYMENT", INK4, size=8.5))
    p.append(micro(sx0, TOP - 14, f"LAST {STRIP} CHECKS  →  NEWEST", INK4, size=8.5))
    p.append(micro(578, TOP - 14, "VERIFIED", INK4, size=8.5))
    p.append(micro(742, TOP - 14, "UPTIME", INK4, "end", 8.5))
    p.append(micro(810, TOP - 14, "RESPONSE", INK4, "end", 8.5))
    p.append(micro(878, TOP - 14, "STATUS", INK4, "end", 8.5))
    p.append(f'<line x1="22" y1="{TOP - 6}" x2="{W - 22}" y2="{TOP - 6}" stroke="#1f1f25"/>')

    window = runs[-STRIP:]
    for i, d in enumerate(deps):
        y = TOP + i * ROW_H
        r = res[d["id"]]
        st = r["s"]
        col = COLORS[st]
        if i % 2 == 0:
            p.append(f'<rect x="20" y="{y}" width="{W - 40}" height="{ROW_H}" rx="6" fill="#ffffff" opacity="0.012"/>')
        # status dot
        p.append(f'<circle cx="28" cy="{y + 19}" r="3.6" fill="{col}"/>')
        if st in ("up", "slow"):
            p.append(f'<circle cx="28" cy="{y + 19}" r="3.6" fill="none" stroke="{col}" stroke-width="1.2">'
                     f'{anim("r", "3.6;9;9", "2.6s", f"{i * 0.21:.2f}s")}{anim("opacity", "0.8;0;0", "2.6s", f"{i * 0.21:.2f}s")}</circle>')
        p.append(text(40, y + 17, esc(d["name"]), size=12.5, fill=INK, family=SANS, weight=600))
        sub = host_of(d["url"]) + (f" · engine v{r['ver'].lstrip('v')}" if r.get("ver") else "")
        p.append(text(40, y + 30.5, esc(sub), size=9, fill=INK4))

        # uptime strip, newest on the right
        pad = STRIP - len(window)
        for k in range(STRIP):
            bx = sx0 + k * (bar_w + bar_gap)
            v = window[k - pad]["results"].get(d["id"]) if k >= pad else None
            bar = f'<rect x="{bx:.1f}" y="{y + 10}" width="{bar_w}" height="18" rx="1.4"'
            if v:
                p.append(f'{bar} fill="{COLORS[v["s"]]}">{reveal(0.25 + k * 0.012 + i * 0.02)}</rect>')
            else:
                p.append(f'{bar} fill="{COLORS[None]}"/>')
        seen = [rr["results"][d["id"]] for rr in runs if d["id"] in rr["results"]]
        up_pct = sum(v["s"] in ("up", "slow") for v in seen) / max(1, len(seen))
        # newest bar breathes
        nx = sx0 + (STRIP - 1) * (bar_w + bar_gap)
        p.append(f'<rect x="{nx - 1:.1f}" y="{y + 8}" width="{bar_w + 2}" height="22" rx="2" fill="none" stroke="{col}" '
                 f'stroke-width="1" opacity="0.5">{anim("opacity", "0.65;0.1;0.65", "2.2s", f"{i * 0.13:.2f}s")}</rect>')

        # verified layers
        chips = [("PAGE", True)]
        if "api" in r:
            chips.append(("API", r["api"]))
        if r.get("db") is not None:
            chips.append(("DB", r["db"]))
        cx = 578
        for lab, ok in chips:
            cw = len(lab) * 5.6 + 18
            ccol = "#22c55e" if (ok and st != "down") else "#ef4444"
            p.append(f'<rect x="{cx:.1f}" y="{y + 11}" width="{cw:.1f}" height="16" rx="4" fill="#0d0d10" stroke="#26262e"/>')
            p.append(f'<circle cx="{cx + 7:.1f}" cy="{y + 19}" r="2.1" fill="{ccol}"/>')
            p.append(text(cx + 12.5, y + 22.4, lab, size=8.5, fill=INK2))
            cx += cw + 5

        p.append(text(742, y + 23, fmt_pct(up_pct), size=11.5,
                      fill=INK if up_pct >= 0.99 else INK2, anchor="end"))
        p.append(text(810, y + 23, esc(fmt_ms(r["ms"]) if st != "down" else "—"), size=11.5,
                      fill=COLORS["slow"] if st == "slow" else INK2, anchor="end"))
        lab = LABELS[st]
        pw = len(lab) * 6.4 + 18
        p.append(f'<rect x="{878 - pw:.1f}" y="{y + 10}" width="{pw:.1f}" height="18" rx="9" fill="{col}" '
                 f'fill-opacity="0.12" stroke="{col}" stroke-opacity="0.55"/>')
        p.append(text(878 - pw / 2, y + 22.6, lab, size=9, fill=col, anchor="middle", weight=700, spacing=0.8))

    # legend
    fy = H - 24
    lx = 24
    for key, lab in (("up", "answered in under 3 s"), ("slow", "answered after waking (over 3 s, or on retry)"),
                     ("partial", "page up, health check failed"), ("down", "no answer, error or login wall"),
                     (None, "not checked yet")):
        p.append(f'<rect x="{lx}" y="{fy - 8.5}" width="4.6" height="11" rx="1.2" fill="{COLORS[key]}"/>')
        p.append(text(lx + 9, fy, esc(lab), size=8.8, fill=INK3))
        lx += 9 + len(lab) * 5.3 + 18
    p.append("</svg>")
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
