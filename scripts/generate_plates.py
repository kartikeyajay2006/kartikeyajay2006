#!/usr/bin/env python3
"""Generate two plates in the profile's one theme:

  assets/kovidam.svg      — section 03 "Building Kovidam": the company as one
                            pipeline. A stack of resumes goes into Skill Graph,
                            which ranks candidates on engineering evidence, and
                            the shortlist goes into AI Interview, which runs the
                            first round and hands the recruiter a review packet.
                            A candidate travels the whole path. The live status
                            of kovidam.co.in comes from the health check
                            generate_select.py records every 3 hours.
  assets/credentials.svg  — section 10 "Credentials & Honors": education,
                            leadership, every honour with its date, and the
                            certifications, on one panel.

The copy is curated and taken from each product's own README; the only live
value is the health check. Credentials are self-reported career markers.

SVG notes (see generate_signal.py): all motion is SMIL, nothing uses
<use>/<mpath>, and everything readable is visible without SMIL.

Never-fail contract: this script always exits 0, and writes a file only after
it has rendered.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from theme import (BG, CYAN, INDIGO, INK, INK_2, INK_3, INK_4, LINE, LINE_2, LIVE, MONO, PANEL,  # noqa: E402
                   PINK, SANS, VIOLET, WAKE, DOWN, blueprint, breathe, esc, fit, glow, kicker, stamp, text_w)

HISTORY_PATH = os.environ.get("HISTORY_PATH", "data/fleet-history.json")
KOVIDAM_PATH = os.environ.get("KOVIDAM_PATH", "assets/kovidam.svg")
CRED_PATH = os.environ.get("CRED_PATH", "assets/credentials.svg")
TZ = timezone(timedelta(hours=5, minutes=30))

# ------------------------------------------------------------------ Kovidam
STAGES = [
    # (title, sub, product)  product: None = input/output, "sg" Skill Graph, "ai" AI Interview
    ("Resumes", "a stack, any format", None),
    ("Real work", "GitHub + 5 platforms", "sg"),
    ("Explained score", "gates · signals · confidence", "sg"),
    ("AI interview", "grounded in the resume", "ai"),
    ("Review packet", "Q&A map · playback · trace", "ai"),
    ("Decision", "in minutes, defensible", None),
]
PRODUCTS = {
    "sg": ("SKILL GRAPH", "Who to interview", "Hire on engineering evidence, not keywords.",
           "FastAPI · PostgreSQL · Qdrant · React", VIOLET),
    "ai": ("AI INTERVIEW", "How they think", "First-round interviews that run themselves.",
           "FastAPI · Next.js · PostgreSQL · Redis", CYAN),
}


def latest_status():
    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            runs = json.load(f).get("runs", [])
        for run in reversed(runs):
            r = run.get("results", {}).get("kovidam")
            if r:
                at = datetime.fromisoformat(run["at"].replace("Z", "+00:00")).astimezone(TZ)
                ok = sum(1 for x in runs if x.get("results", {}).get("kovidam", {}).get("s") in ("up", "slow"))
                total = sum(1 for x in runs if x.get("results", {}).get("kovidam"))
                return r, at, (100 * ok / total if total else None)
    except Exception:  # noqa: BLE001
        pass
    return None, None, None


def kovidam():
    W, H = 1280, 470
    r, at, avail = latest_status()
    up = bool(r and r.get("s") in ("up", "slow"))
    scol = LIVE if up else (DOWN if r else INK_3)
    status = (f"ONLINE · {r['ms']} ms" if up else ("OFFLINE" if r else "SITE"))
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" aria-labelledby="kt kd">',
         '<title id="kt">Building Kovidam</title>',
         '<desc id="kd">Kovidam, the AI talent-intelligence company I co-founded and build as AI engineer, drawn as one '
         'pipeline: a stack of resumes goes into Skill Graph, which pulls each candidate\'s real work from GitHub and five '
         'coding platforms and returns a ranked shortlist where every score explains itself; the shortlist goes into AI '
         'Interview, which runs a first-round interview grounded in each resume and hands the recruiter a review packet, '
         f'so the decision takes minutes. kovidam.co.in {"is online" if up else "status unknown"} at the last health check.'
         '</desc>',
         f'<defs>{glow("kg", 2.4)}<clipPath id="kfr"><rect width="{W}" height="{H}" rx="14"/></clipPath>'
         f'<radialGradient id="klit" cx="0.08" cy="0.1" r="0.7"><stop offset="0" stop-color="{VIOLET}" stop-opacity="0.18"/>'
         f'<stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/></radialGradient>'
         f'<linearGradient id="kink" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff"/>'
         f'<stop offset="0.5" stop-color="#c4b5fd"/><stop offset="1" stop-color="#67e8f9"/></linearGradient></defs>',
         '<g clip-path="url(#kfr)">', f'<rect width="{W}" height="{H}" fill="{BG}"/>',
         f'<rect width="{W}" height="{H}" fill="url(#klit)"/>', blueprint(W, H, VIOLET, a_fine=0.018, a_strong=0.045)]
    o.append(kicker(40, 44, "BUILDING  //  KOVIDAM  ·  CO-FOUNDER & AI ENGINEER"))
    checked = f"CHECKED {at.strftime('%H:%M')} IST" if at else ""
    o.append(stamp(W - 40, 44, f"KOVIDAM.CO.IN  ·  {status}" + (f"  ·  {checked}" if checked else ""), dot=up))

    # left: the company
    o.append(f'<text x="40" y="112" font-family="{SANS}" font-size="46" font-weight="800" letter-spacing="3" '
             f'fill="url(#kink)">KOVIDAM</text>')
    o.append(f'<text x="42" y="142" font-family="{SANS}" font-size="17" font-weight="600" fill="{INK}">AI talent intelligence</text>')
    o.append(f'<text x="42" y="170" font-family="{SANS}" font-size="14" fill="{INK_3}">Hiring decided by what a candidate has</text>')
    o.append(f'<text x="42" y="190" font-family="{SANS}" font-size="14" fill="{INK_3}">built, not what a resume says.</text>')
    if avail is not None:
        o.append(kicker(42, 236, "UPTIME, SINCE CHECKS BEGAN", size=9))
        o.append(f'<text x="41" y="270" font-family="{SANS}" font-size="30" font-weight="800" fill="{INK}">{avail:.1f}%</text>')
    o.append(kicker(42, 312, "ROLE", size=9))
    o.append(f'<text x="42" y="334" font-family="{SANS}" font-size="15" font-weight="700" fill="{INK}">Co-founder &amp; AI engineer</text>')
    o.append(f'<text x="42" y="354" font-family="{SANS}" font-size="13" fill="{INK_3}">Skill Graph and AI Interview, both open source.</text>')

    # right: the pipeline
    x0, x1 = 360, W - 40
    n = len(STAGES)
    gap = 14
    sw = (x1 - x0 - gap * (n - 1)) / n
    sy, sh = 236, 64
    # product brackets
    for key, (name, q, pitch, stack, col) in PRODUCTS.items():
        idx = [i for i, st in enumerate(STAGES) if st[2] == key]
        bx0 = x0 + idx[0] * (sw + gap) - 8
        bx1 = x0 + idx[-1] * (sw + gap) + sw + 8
        o.append(f'<rect x="{bx0:.1f}" y="92" width="{bx1 - bx0:.1f}" height="{sy + sh + 16 - 92}" rx="12" fill="{col}" '
                 f'fill-opacity="0.05" stroke="{col}" stroke-opacity="0.45" stroke-dasharray="5 5"/>')
        o.append(f'<text x="{bx0 + 16:.1f}" y="118" font-family="{MONO}" font-size="10.5" font-weight="700" letter-spacing="1.6" '
                 f'fill="{col}">{name}</text>')
        o.append(f'<text x="{bx0 + 16:.1f}" y="146" font-family="{SANS}" font-size="20" font-weight="800" fill="{INK}">{q}</text>')
        o.append(f'<text x="{bx0 + 16:.1f}" y="168" font-family="{SANS}" font-size="12.5" '
                 f'fill="{INK_2}">{esc(pitch)}</text>')
        o.append(f'<text x="{bx0 + 16:.1f}" y="192" font-family="{MONO}" '
                 f'font-size="{fit(stack, 9.5, bx1 - bx0 - 32, mono=True)}" fill="{INK_4}">{esc(stack)}</text>')
    # wire and stages
    cy = sy + sh / 2
    o.append(f'<path d="M{x0} {cy}H{x1}" stroke="{LINE_2}" stroke-width="1.4"/>')
    cyc = 6.0
    for i, (title, sub, key) in enumerate(STAGES):
        x = x0 + i * (sw + gap)
        col = PRODUCTS[key][4] if key else INK_3
        t = i / n * 0.9
        o.append(f'<rect x="{x:.1f}" y="{sy}" width="{sw:.1f}" height="{sh}" rx="10" fill="{PANEL}" stroke="{col}" '
                 f'stroke-opacity="{0.75 if key else 0.35}"/>')
        o.append(f'<rect x="{x - 3:.1f}" y="{sy - 3}" width="{sw + 6:.1f}" height="{sh + 6}" rx="12" fill="{col}" fill-opacity="0.12" '
                 f'stroke="{col}" stroke-width="1.8" opacity="0" filter="url(#kg)"><animate attributeName="opacity" '
                 f'values="0;0;1;0;0" keyTimes="0;{max(t, 0.001):.3f};{t + 0.04:.3f};{t + 0.22:.3f};1" dur="{cyc}s" '
                 f'repeatCount="indefinite"/></rect>')
        o.append(f'<text x="{x + sw / 2:.1f}" y="{sy + 28}" text-anchor="middle" font-family="{SANS}" '
                 f'font-size="{fit(title, 14, sw - 14, bold=True)}" font-weight="700" fill="{INK}">{esc(title)}</text>')
        o.append(f'<text x="{x + sw / 2:.1f}" y="{sy + 46}" text-anchor="middle" font-family="{MONO}" '
                 f'font-size="{fit(sub, 9, sw - 12, mono=True, floor=7.5)}" fill="{INK_3}">{esc(sub)}</text>')
        if i < n - 1:
            ax = x + sw + gap / 2
            o.append(f'<path d="M{ax - 3:.1f} {cy - 4}l5 4l-5 4" fill="none" stroke="{INK_3}" stroke-width="1.3"/>')
    # one candidate, travelling the whole way
    o.append(f'<circle r="5" fill="#ffffff" filter="url(#kg)"><animateMotion path="M{x0} {cy}H{x1}" keyPoints="0;1;1" '
             f'keyTimes="0;0.9;1" calcMode="linear" dur="{cyc}s" repeatCount="indefinite"/>'
             f'<animate attributeName="opacity" values="0;1;1;0;0" keyTimes="0;0.03;0.87;0.9;1" dur="{cyc}s" '
             f'repeatCount="indefinite"/></circle>')
    # footer facts, from the READMEs
    fy = 360
    facts = [("EVIDENCE OVER CLAIMS", "A skill counts for more when a repo, a contest rating or a project backs it."),
             ("EXPLAINABLE BY DEFAULT", "Every candidate comes back with the gates passed and the signals behind the score."),
             ("A REAL CONVERSATION", "The interviewer adapts to each resume; the recruiter reviews it in minutes.")]
    fw = (x1 - x0 - 2 * 16) / 3
    for i, (k, v) in enumerate(facts):
        fx = x0 + i * (fw + 16)
        o.append(f'<rect x="{fx:.1f}" y="{fy}" width="{fw:.1f}" height="70" rx="10" fill="{PANEL}" stroke="{LINE}"/>')
        o.append(f'<rect x="{fx + 1:.1f}" y="{fy + 12}" width="2.5" height="46" rx="1.2" fill="{[VIOLET, INDIGO, CYAN][i]}"/>')
        o.append(kicker(fx + 16, fy + 24, k, fill=INK_2, size=9))
        words, lines, cur = v.split(), [], ""
        for w_ in words:
            if text_w(cur + " " + w_, 11.5) > fw - 30 and cur:
                lines.append(cur)
                cur = w_
            else:
                cur = (cur + " " + w_).strip()
        lines.append(cur)
        for m, line in enumerate(lines[:2]):
            o.append(f'<text x="{fx + 16:.1f}" y="{fy + 44 + m * 16}" font-family="{SANS}" font-size="11.5" '
                     f'fill="{INK_3}">{esc(line)}</text>')
    o.append('</g>')
    o.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="{LINE}"/>')
    o.append('</svg>')
    return "\n".join(o)


# ------------------------------------------------------------------ credentials
EDUCATION = ("B.Tech, Computer Science & Engineering", "BITS Pilani")
LEADERSHIP = [("Co-founder & AI engineer", "Kovidam"), ("Product & Applied AI Lead", "AI-ML Club")]
HONORS = [("SEP 2026", "Gradient Rush Hackathon", "WINNER", VIOLET),
          ("2026", "Mela VC Ventures", "2ND PLACE", PINK),
          ("2025", "Auraverse Hackathon", "WINNER", VIOLET),
          ("2025", "Cardano Hackathon, Asia", "FINALIST", INDIGO),
          ("2024", "Young AI", "WINNER", VIOLET)]
CERTS = [("AWS Certified Cloud Practitioner", "2025"), ("Google AI Essentials", "2025")]


def credentials():
    W, H = 1280, 360
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" aria-labelledby="ct cd">',
         '<title id="ct">Credentials and honors</title>',
         f'<desc id="cd">Education: {esc(EDUCATION[0])}, {esc(EDUCATION[1])}. Leadership: '
         f'{esc("; ".join(f"{a}, {b}" for a, b in LEADERSHIP))}. Honors: '
         f'{esc("; ".join(f"{h[1]}, {h[2].lower()}, {h[0].title()}" for h in HONORS))}. Certifications: '
         f'{esc("; ".join(f"{a} ({b})" for a, b in CERTS))}.</desc>',
         f'<defs>{glow("cg", 2.2)}<clipPath id="cfr"><rect width="{W}" height="{H}" rx="14"/></clipPath></defs>',
         '<g clip-path="url(#cfr)">', f'<rect width="{W}" height="{H}" fill="{BG}"/>',
         blueprint(W, H, INDIGO, a_fine=0.016, a_strong=0.04)]
    wins = sum(1 for h in HONORS if h[2] == "WINNER")
    o.append(kicker(40, 44, "CREDENTIALS  //  EDUCATION · LEADERSHIP · HONORS · CERTIFICATIONS"))
    o.append(stamp(W - 40, 44, f"{wins} WINS · {len(HONORS)} PODIUMS & FINALS", dot=False))

    # left column: education, leadership, certifications
    lx = 40
    o.append(kicker(lx, 92, "EDUCATION", fill=VIOLET, size=9.5))
    o.append(f'<text x="{lx}" y="122" font-family="{SANS}" font-size="20" font-weight="800" fill="{INK}">{esc(EDUCATION[1])}</text>')
    o.append(f'<text x="{lx}" y="144" font-family="{SANS}" font-size="13.5" fill="{INK_3}">{esc(EDUCATION[0])}</text>')
    o.append(kicker(lx, 190, "LEADERSHIP", fill=CYAN, size=9.5))
    for i, (role, org) in enumerate(LEADERSHIP):
        y = 216 + i * 24
        o.append(f'<circle cx="{lx + 4}" cy="{y - 4.5}" r="3" fill="{LIVE}">{breathe("opacity", "1;0.35;1", "2s", f"{i * 0.4}s")}</circle>')
        o.append(f'<text x="{lx + 16}" y="{y}" font-family="{SANS}" font-size="14" font-weight="700" fill="{INK}">{esc(role)}'
                 f'<tspan font-weight="400" fill="{INK_3}">  ·  {esc(org)}</tspan></text>')
    o.append(kicker(lx, 288, "CERTIFICATIONS", fill=INDIGO, size=9.5))
    for i, (name, yr) in enumerate(CERTS):
        y = 314 + i * 22
        o.append(f'<text x="{lx}" y="{y}" font-family="{SANS}" font-size="13.5" fill="{INK_2}">{esc(name)}'
                 f'<tspan font-family="{MONO}" font-size="10.5" fill="{INK_4}">  {yr}</tspan></text>')

    # right: the honours board
    bx0, bx1 = 560, W - 40
    o.append(f'<rect x="{bx0}" y="72" width="{bx1 - bx0}" height="{H - 104}" rx="12" fill="{PANEL}" stroke="{LINE}"/>')
    o.append(kicker(bx0 + 22, 100, "HONORS", fill=INK_2, size=9.5))
    o.append(kicker(bx1 - 22, 100, "RESULT", anchor="end", size=9))
    rh = (H - 104 - 46) / len(HONORS)
    ys = ";".join(f"{116 + i * rh:.1f}" for i in range(len(HONORS)))
    kt = ";".join(f"{i / len(HONORS):.4f}" for i in range(len(HONORS)))
    o.append(f'<rect x="{bx0 + 10}" y="116" width="{bx1 - bx0 - 20}" height="{rh - 4:.1f}" rx="8" fill="{VIOLET}" '
             f'fill-opacity="0.07" stroke="{VIOLET}" stroke-opacity="0.3"><animate attributeName="y" values="{ys}" '
             f'keyTimes="{kt}" calcMode="discrete" dur="{len(HONORS) * 1.6}s" repeatCount="indefinite"/></rect>')
    for i, (when, name, result, col) in enumerate(HONORS):
        y = 116 + i * rh + rh / 2 + 2
        o.append(f'<text x="{bx0 + 24}" y="{y + 2}" font-family="{MONO}" font-size="10.5" letter-spacing="1" fill="{INK_4}">{when}</text>')
        o.append(f'<text x="{bx0 + 120}" y="{y + 3}" font-family="{SANS}" font-size="15.5" font-weight="700" fill="{INK}">{esc(name)}</text>')
        cw = len(result) * 7.4 + 30
        cx = bx1 - 22 - cw
        o.append(f'<rect x="{cx:.1f}" y="{y - 11}" width="{cw:.1f}" height="22" rx="11" fill="{col}" fill-opacity="0.1" '
                 f'stroke="{col}" stroke-opacity="0.6"/>')
        o.append(f'<circle cx="{cx + 12:.1f}" cy="{y}" r="3" fill="{col}"/>')
        o.append(f'<text x="{cx + 21:.1f}" y="{y + 4}" font-family="{MONO}" font-size="10.5" font-weight="700" '
                 f'letter-spacing="1" fill="{INK}">{result}</text>')
        if i:
            o.append(f'<path d="M{bx0 + 22} {116 + i * rh:.1f}H{bx1 - 22}" stroke="{LINE}"/>')
    o.append('</g>')
    o.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="{LINE}"/>')
    o.append('</svg>')
    return "\n".join(o)


def write(path, svg):
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(svg)
    os.replace(tmp, path)
    print(f"Wrote {path}")


def main():
    for path, fn in ((KOVIDAM_PATH, kovidam), (CRED_PATH, credentials)):
        try:
            svg = fn()
            if "<svg" in svg and "</svg>" in svg:
                write(path, svg)
        except Exception as e:  # noqa: BLE001
            print(f"WARNING: {path} not regenerated: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
