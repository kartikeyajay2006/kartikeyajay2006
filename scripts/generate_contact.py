#!/usr/bin/env python3
"""Generate assets/contact-terminal.svg — the section 13 "Contact" closing banner.

Purely decorative/framing (no GitHub API needed — just the run timestamp).
IMPORTANT: this SVG contains no clickable links. GitHub renders it as a flat
<img>, and any <a>/hyperlink baked into an SVG is inert in that context — so
the actual GitHub / Portfolio / LinkedIn / Kovidam / Email buttons live as
real markdown links directly below this image in the README, not inside it.

Deliberately calmer than the other three dashboards (Identity, Engineering
Impact, the contribution runner) — this is the closing section, and piling
on more animated complexity here would fight the pacing of a strong ending.

Never-fail contract: this script always exits 0. Any problem is logged to
stderr and the script leaves the existing output file untouched.
"""
import os
import sys
from datetime import datetime, timezone

OUT_PATH = os.environ.get("OUT_PATH", "assets/contact-terminal.svg")


def build_svg():
    synced = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    W, H = 900, 210

    tags = ["COLLABORATIONS", "OPPORTUNITIES", "AMBITIOUS BUILDS"]
    tag_colors = ["#a855f7", "#22d3ee", "#22c55e"]

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" '
                  f'role="img" aria-labelledby="cTitle cDesc">')
    parts.append('<title id="cTitle">Contact — system close</title>')
    parts.append('<desc id="cDesc">Closing signal: open to collaborations, opportunities, and ambitious builds. '
                 'Clickable GitHub, Portfolio, LinkedIn, Kovidam, and Email links appear directly below this image.</desc>')

    parts.append('''<defs>
    <filter id="glow" x="-250%" y="-250%" width="600%" height="600%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <radialGradient id="haloGrad" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#7c3aed" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#7c3aed" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#a855f7" stop-opacity="0"/>
      <stop offset="50%" stop-color="#22d3ee"/>
      <stop offset="100%" stop-color="#a855f7" stop-opacity="0"/>
    </linearGradient>
  </defs>''')

    parts.append(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="14" fill="#0a0a0a" stroke="#1f1f1f"/>')

    parts.append(f'<text x="20" y="24" font-family="Consolas, \'SF Mono\', monospace" font-size="10" '
                 f'letter-spacing="1" fill="#666">// SYSTEM.13 &gt; CLOSE.EXE</text>')
    parts.append(f'<circle cx="880" cy="20" r="3" fill="#22c55e"><animate attributeName="opacity" '
                 f'values="1;0.3;1" dur="2s" repeatCount="indefinite"/></circle>')

    cx = W / 2
    parts.append(f'<circle cx="{cx}" cy="86" r="70" fill="url(#haloGrad)">'
                 f'<animate attributeName="r" values="60;76;60" dur="4.5s" repeatCount="indefinite"/></circle>')

    parts.append(f'<text x="{cx}" y="76" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" '
                 f'font-size="30" font-weight="800" letter-spacing="1" fill="#f2f2f2">LET&#8217;S BUILD</text>')
    parts.append(f'<text x="{cx}" y="102" text-anchor="middle" font-family="Consolas, monospace" font-size="11" '
                 f'fill="#999">AI systems &#183; Agentic architectures &#183; Backend systems &#183; Ambitious products</text>')

    tag_gap = 14
    tag_widths = [128, 118, 138]
    total_w = sum(tag_widths) + tag_gap * (len(tags) - 1)
    tx = cx - total_w / 2
    for i, (tag, color, tw) in enumerate(zip(tags, tag_colors, tag_widths)):
        parts.append(f'<rect x="{tx:.1f}" y="122" width="{tw}" height="22" rx="11" fill="#101014" stroke="{color}" opacity="0.9"/>')
        parts.append(f'<circle cx="{tx+16:.1f}" cy="133" r="2.4" fill="{color}">'
                     f'<animate attributeName="opacity" values="1;0.35;1" dur="1.8s" begin="{i*0.3}s" repeatCount="indefinite"/></circle>')
        parts.append(f'<text x="{tx+26:.1f}" y="137" font-family="Consolas, monospace" font-size="9" '
                     f'letter-spacing="0.6" fill="{color}">{tag}</text>')
        tx += tw + tag_gap

    parts.append(f'<line x1="30" y1="168" x2="870" y2="168" stroke="#1f1f24" stroke-width="1"/>')
    parts.append(f'<rect x="30" y="167" width="60" height="2" fill="url(#lineGrad)" filter="url(#glow)">'
                 f'<animate attributeName="x" values="30;810" dur="6s" repeatCount="indefinite" calcMode="linear"/></rect>')

    parts.append(f'<text x="30" y="190" font-family="Consolas, monospace" font-size="10" letter-spacing="1.5" '
                 f'fill="#555">&#9679; SYSTEM // END</text>')
    parts.append(f'<text x="870" y="190" text-anchor="end" font-family="Consolas, monospace" font-size="9" '
                 f'fill="#555">SYNCED {synced}</text>')

    parts.append('</svg>')
    return "\n".join(parts)


def main():
    try:
        svg = build_svg()
    except Exception as e:  # noqa: BLE001 - deliberate: never let this step fail the job
        print(f"WARNING: could not regenerate {OUT_PATH}: {e}. Leaving existing file untouched.", file=sys.stderr)
        return

    if "<svg" not in svg or "</svg>" not in svg:
        print("WARNING: generated SVG failed a basic sanity check. Leaving existing file untouched.", file=sys.stderr)
        return

    tmp_path = OUT_PATH + ".tmp"
    try:
        os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(svg)
        os.replace(tmp_path, OUT_PATH)
        print(f"Wrote {OUT_PATH} ({len(svg):,} bytes)")
    except OSError as e:
        print(f"WARNING: could not write {OUT_PATH}: {e}", file=sys.stderr)
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


if __name__ == "__main__":
    main()
    sys.exit(0)
