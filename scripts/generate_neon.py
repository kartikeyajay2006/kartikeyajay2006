#!/usr/bin/env python3
"""Generate assets/neon-contributions.svg from real GitHub contribution data.

Stdlib-only (no pip install needed in CI). Reads GH_TOKEN (a PAT with
read:user scope) and GH_LOGIN from the environment, queries the GraphQL
contributionsCollection for the trailing 6 months, and renders a dark,
neon "energy runner" traversal of the actual contribution grid as an
animated SVG (SMIL animateMotion — no embedded JS, since GitHub strips
inline scripts).

Every animated element carries its own inline path/values — no <use> or
<mpath> href indirection. GitHub's image-serving pipeline (camo) strips
internal href/xlink:href fragment references from served SVGs as an
XSS-safety measure, which silently collapses href-based motion paths to
a static point. Self-contained inline paths are the only form verified
to survive that pipeline.

Never-fail contract: this script always exits 0. Any problem (missing
token, rate limit, network error, malformed response, render bug) is
logged to stderr and the script leaves the existing output file exactly
as it was — it never writes partial output and never raises the process
exit code, so the calling workflow can never go red because of this step.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

LOGIN = os.environ.get("GH_LOGIN", "kartikeyajay2006")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT_PATH = os.environ.get("OUT_PATH", "assets/neon-contributions.svg")
MONTHS_BACK_DAYS = 183  # ~6 months


class FetchError(Exception):
    pass


QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            weekday
            contributionCount
            color
          }
        }
      }
    }
  }
}
"""

# GitHub's public API always returns one of these light-theme hex values
# regardless of the querying account's own theme. Map them to GitHub's
# own dark-mode green scale so the grid still reads as "the real graph".
LEVEL_BY_LIGHT_COLOR = {
    "#ebedf0": 0, "#9be9a8": 1, "#40c463": 2, "#30a14e": 3, "#216e39": 4,
    "#c6e48b": 1, "#7bc96f": 2, "#239a3b": 3, "#196127": 4,
}
DARK_BY_LEVEL = {0: "#161b22", 1: "#0e4429", 2: "#006d32", 3: "#26a641", 4: "#39d353"}


def _fetch_once():
    now = datetime.now(timezone.utc)
    frm = now - timedelta(days=MONTHS_BACK_DAYS)
    body = json.dumps({
        "query": QUERY,
        "variables": {
            "login": LOGIN,
            "from": frm.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": f"{LOGIN}-neon-contrib-generator",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise FetchError(f"HTTP {e.code} from GitHub GraphQL: {detail}") from e
    except urllib.error.URLError as e:
        raise FetchError(f"network failure reaching GitHub GraphQL: {e}") from e
    except (TimeoutError, json.JSONDecodeError) as e:
        raise FetchError(f"bad response from GitHub GraphQL: {e}") from e

    if payload.get("errors"):
        raise FetchError(f"GraphQL returned errors: {payload['errors']}")

    user = payload.get("data", {}).get("user")
    if not user:
        raise FetchError(f"user '{LOGIN}' not found in GraphQL response")

    calendar = user["contributionsCollection"]["contributionCalendar"]
    if not calendar.get("weeks"):
        raise FetchError("GraphQL response had no weeks of data")
    return calendar


def fetch_calendar():
    """Fetch with a couple of retries for transient failures; raises FetchError
    (never sys.exit) if every attempt fails, so the caller decides how to degrade."""
    if not TOKEN:
        raise FetchError(
            "GH_TOKEN is not set. Add a classic PAT with 'read:user' scope as the "
            "GH_CONTRIB_PAT repo secret — the default GITHUB_TOKEN cannot read "
            "contributionsCollection."
        )

    last_err = None
    for attempt in range(3):
        try:
            return _fetch_once()
        except FetchError as e:
            last_err = e
            print(f"WARNING: attempt {attempt + 1}/3 failed: {e}", file=sys.stderr)
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise last_err


def level_for_day(day, max_count):
    lvl = LEVEL_BY_LIGHT_COLOR.get(day["color"])
    if lvl is not None:
        return lvl
    count = day["contributionCount"]
    if count == 0 or max_count == 0:
        return 0
    ratio = count / max_count
    if ratio <= 0.25:
        return 1
    if ratio <= 0.5:
        return 2
    if ratio <= 0.75:
        return 3
    return 4


def lerp_color(c1, c2, t):
    r1, g1, b1 = c1
    r2, g2, b2 = c2
    return (
        round(r1 + (r2 - r1) * t),
        round(g1 + (g2 - g1) * t),
        round(b1 + (b2 - b1) * t),
    )


def build_svg(calendar):
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    max_count = max((d["contributionCount"] for w in weeks for d in w["contributionDays"]), default=0)

    # Rectangular (wider-than-tall) cells so a 6-month grid still reads as a wide,
    # short banner consistent with the rest of the profile's asset cards, instead
    # of the near-square block a 26-week grid would make at GitHub's square cell size.
    n_weeks = max(len(weeks), 1)
    target_grid_width = 640
    gap = 4
    cell_h, gap_v = 9, 4
    pitch_v = cell_h + gap_v
    pitch_w = max(round((target_grid_width + gap) / n_weeks), 14)
    cell_w = pitch_w - gap

    left_margin, top_margin, right_margin, bottom_margin = 34, 40, 20, 42
    grid_w = n_weeks * pitch_w - gap
    grid_h = 7 * pitch_v - gap_v
    width = left_margin + grid_w + right_margin
    height = top_margin + grid_h + bottom_margin

    def cx(week_idx):
        return left_margin + week_idx * pitch_w + cell_w / 2

    def cy(weekday):
        return top_margin + weekday * pitch_v + cell_h / 2

    # --- grid cells + month labels ---
    cells_svg = []
    month_labels = []
    last_month = None
    for wi, week in enumerate(weeks):
        first_day = week["contributionDays"][0] if week["contributionDays"] else None
        if first_day:
            month = datetime.fromisoformat(first_day["date"]).month
            if month != last_month:
                last_month = month
                label = datetime.fromisoformat(first_day["date"]).strftime("%b").upper()
                month_labels.append((cx(wi) - cell_w / 2, top_margin - 10, label))

        for day in week["contributionDays"]:
            lvl = level_for_day(day, max_count)
            x = left_margin + wi * pitch_w
            y = top_margin + day["weekday"] * pitch_v
            fill = DARK_BY_LEVEL[lvl]
            stroke_attr = ' stroke="#22272e"' if lvl == 0 else ""
            cells_svg.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_w}" height="{cell_h}" rx="2" '
                f'fill="{fill}"{stroke_attr}/>'
            )

    # --- runner path: boustrophedon traversal of real cells (down, then up, ...) ---
    points = []  # (x, y, level)
    for wi, week in enumerate(weeks):
        days = sorted(week["contributionDays"], key=lambda d: d["weekday"])
        if wi % 2 == 1:
            days = list(reversed(days))
        for day in days:
            lvl = level_for_day(day, max_count)
            points.append((cx(wi), cy(day["weekday"]), lvl))

    n = len(points)
    path_d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y, _ in points)

    # animateMotion's default (no keyPoints) is constant speed by ARC LENGTH over the
    # duration. Cells are rectangular, so vertical and horizontal segments differ in
    # length — keyTimes for the intensity-driven glow must follow real cumulative
    # distance, not a naive i/(n-1) index fraction, to stay in sync with the orb.
    seg_lens = [0.0]
    for i in range(1, n):
        x0, y0, _ = points[i - 1]
        x1, y1, _ = points[i]
        seg_lens.append(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
    cum = [0.0]
    for d in seg_lens[1:]:
        cum.append(cum[-1] + d)
    total_len = cum[-1] if n > 1 else 0.0
    key_times = [round(c / total_len, 4) if total_len > 0 else 0 for c in cum]
    # keyTimes must be strictly increasing for SMIL; nudge any accidental ties.
    for i in range(1, len(key_times)):
        if key_times[i] <= key_times[i - 1]:
            key_times[i] = min(1.0, key_times[i - 1] + 0.0001)
    key_times_attr = ";".join(str(t) for t in key_times)

    radius_by_level = {0: 3.2, 1: 3.8, 2: 4.4, 3: 5.4, 4: 6.6}
    opacity_by_level = {0: 0.55, 1: 0.68, 2: 0.8, 3: 0.92, 4: 1.0}
    r_values = ";".join(str(radius_by_level[lvl]) for _, _, lvl in points)
    op_values = ";".join(str(opacity_by_level[lvl]) for _, _, lvl in points)

    # Data-driven "burst" halo: near-zero except a bright, brief flash on the
    # actually-highest-intensity days. Consecutive differing values interpolate
    # linearly between their keyTimes in SMIL, so this reads as a smooth pulse.
    burst_r = ";".join("14" if lvl == 4 else ("9" if lvl == 3 else "0") for _, _, lvl in points)
    burst_op = ";".join("0.5" if lvl == 4 else ("0.18" if lvl == 3 else "0") for _, _, lvl in points)

    dur = 30.0
    dur_attr = f"{dur}s"

    weekday_labels = [(0, "MON"), (2, "WED"), (4, "FRI")]
    weekday_svg = "".join(
        f'<text x="{left_margin - 8}" y="{cy(wd) + 3:.1f}" text-anchor="end" '
        f'font-family="Consolas, \'SF Mono\', monospace" font-size="8" letter-spacing="0.5" '
        f'fill="#555">{label}</text>'
        for wd, label in weekday_labels
    )

    month_svg = "".join(
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Consolas, \'SF Mono\', monospace" '
        f'font-size="8" letter-spacing="0.5" fill="#555">{label}</text>'
        for x, y, label in month_labels
    )

    synced = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # --- energy trail: discrete trailing nodes, each riding its own inline copy of
    # the same path but starting further back in time, purple (old/far) -> cyan
    # (fresh/near the orb). No href/mpath indirection — see module docstring.
    PURPLE = (124, 58, 237)
    CYAN = (34, 211, 238)
    trail_nodes = 7
    trail_svg = []
    for i in range(trail_nodes, 0, -1):
        t = i / trail_nodes  # 1 = oldest/farthest back, ~0 = right behind the orb
        color = lerp_color(CYAN, PURPLE, t)
        color_hex = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
        radius = 4.6 * (1 - 0.55 * t)
        opacity = 0.5 * (1 - 0.82 * t)
        begin = -(dur * (i / (trail_nodes + 1)) * 0.14)
        trail_svg.append(
            f'<circle r="{radius:.2f}" fill="{color_hex}" opacity="{opacity:.2f}" '
            f'filter="url(#neonGlowSoft)">'
            f'<animateMotion dur="{dur_attr}" begin="{begin:.2f}s" repeatCount="indefinite" '
            f'rotate="0" path="{path_d}"/>'
            f'</circle>'
        )

    # --- ambient sparkle particles: small, further-lagging, independently twinkling ---
    particles = []
    for i, begin in enumerate((-2.0, -3.6, -5.2)):
        particles.append(
            f'<circle r="1.5" fill="#a78bfa" opacity="0.5" filter="url(#neonGlowSoft)">'
            f'<animateMotion dur="{dur_attr}" begin="{begin}s" repeatCount="indefinite" '
            f'rotate="0" path="{path_d}"/>'
            f'<animate attributeName="opacity" values="0.1;0.6;0.1" dur="{1.4 + i * 0.3}s" '
            f'begin="{begin}s" repeatCount="indefinite"/>'
            f'</circle>'
        )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%"
     role="img" aria-labelledby="neonTitle neonDesc">
  <title id="neonTitle">Neon contribution runner</title>
  <desc id="neonDesc">Animated neon orb tracing {LOGIN}'s real GitHub contribution graph — {total} contributions in the last 6 months. Regenerated automatically by GitHub Actions.</desc>

  <defs>
    <radialGradient id="orbGrad" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="35%" stop-color="#8ff4ff"/>
      <stop offset="75%" stop-color="#7c3aed"/>
      <stop offset="100%" stop-color="#7c3aed" stop-opacity="0"/>
    </radialGradient>
    <filter id="neonGlow" x="-250%" y="-250%" width="600%" height="600%">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
    <filter id="neonGlowSoft" x="-250%" y="-250%" width="600%" height="600%">
      <feGaussianBlur stdDeviation="1.6" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>

  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="14" fill="#0a0a0a" stroke="#1f1f1f"/>

  <text x="20" y="22" font-family="Consolas, 'SF Mono', monospace" font-size="10" letter-spacing="1" fill="#555">SIGNAL // CONTRIB</text>
  <circle cx="{width - 22}" cy="19" r="3" fill="#8f6bff">
    <animate attributeName="opacity" values="1;0.35;1" dur="2.2s" repeatCount="indefinite"/>
  </circle>

  {month_svg}
  {weekday_svg}

  <g>{"".join(cells_svg)}</g>

  <path d="{path_d}" fill="none" stroke="#242433" stroke-width="1" stroke-linejoin="round" opacity="0.3"/>

  {"".join(trail_svg)}
  {"".join(particles)}

  <!-- burst halo: real data-driven flash on the highest-intensity days -->
  <circle fill="#22d3ee" filter="url(#neonGlow)">
    <animateMotion dur="{dur_attr}" repeatCount="indefinite" rotate="0" path="{path_d}"/>
    <animate attributeName="r" values="{burst_r}" keyTimes="{key_times_attr}" dur="{dur_attr}"
      repeatCount="indefinite" calcMode="linear"/>
    <animate attributeName="opacity" values="{burst_op}" keyTimes="{key_times_attr}" dur="{dur_attr}"
      repeatCount="indefinite" calcMode="linear"/>
  </circle>

  <!-- the runner: bright white/cyan core, reacts to real contribution intensity -->
  <circle r="4" fill="url(#orbGrad)" filter="url(#neonGlow)">
    <animateMotion dur="{dur_attr}" repeatCount="indefinite" rotate="0" path="{path_d}"/>
    <animate attributeName="r" values="{r_values}" keyTimes="{key_times_attr}" dur="{dur_attr}"
      repeatCount="indefinite" calcMode="linear"/>
    <animate attributeName="opacity" values="{op_values}" keyTimes="{key_times_attr}" dur="{dur_attr}"
      repeatCount="indefinite" calcMode="linear"/>
  </circle>
  <circle r="1.6" fill="#ffffff">
    <animateMotion dur="{dur_attr}" repeatCount="indefinite" rotate="0" path="{path_d}"/>
  </circle>

  <text x="20" y="{height - 14}" font-family="Consolas, 'SF Mono', monospace" font-size="9" letter-spacing="0.5" fill="#8a8a8a">{total} CONTRIBUTIONS · LAST 6 MONTHS</text>
  <text x="{width - 20}" y="{height - 14}" text-anchor="end" font-family="Consolas, 'SF Mono', monospace" font-size="9" fill="#666">SYNCED {synced}</text>
</svg>
'''
    return svg


def main():
    try:
        calendar = fetch_calendar()
        svg = build_svg(calendar)
    except Exception as e:  # noqa: BLE001 - deliberate: never let this step fail the job
        print(f"WARNING: could not regenerate {OUT_PATH}: {e}. Leaving existing file untouched.",
              file=sys.stderr)
        return

    if "<svg" not in svg or "</svg>" not in svg:
        print("WARNING: generated SVG failed a basic sanity check. Leaving existing file untouched.",
              file=sys.stderr)
        return

    tmp_path = OUT_PATH + ".tmp"
    try:
        os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(svg)
        os.replace(tmp_path, OUT_PATH)  # atomic: never leaves a half-written file
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
    sys.exit(0)  # never-fail contract: this script always exits 0
