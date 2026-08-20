#!/usr/bin/env python3
"""Generate assets/neon-contributions.svg from real GitHub contribution data.

Stdlib-only (no pip install needed in CI). Reads GH_TOKEN (a PAT with
read:user scope) and GH_LOGIN from the environment, queries the GraphQL
contributionsCollection for the trailing 12 months, and renders a dark,
neon "energy runner" traversal of the actual contribution grid as an
animated SVG (SMIL animateMotion — no embedded JS, since GitHub strips
inline scripts).

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
from datetime import datetime, timezone

LOGIN = os.environ.get("GH_LOGIN", "kartikeyajay2006")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT_PATH = os.environ.get("OUT_PATH", "assets/neon-contributions.svg")


class FetchError(Exception):
    pass

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
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
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode("utf-8")
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


def build_svg(calendar):
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    max_count = max((d["contributionCount"] for w in weeks for d in w["contributionDays"]), default=0)

    cell, gap = 10, 3
    pitch = cell + gap
    n_weeks = len(weeks)

    left_margin, top_margin, right_margin, bottom_margin = 32, 44, 18, 46
    grid_w = n_weeks * pitch - gap
    grid_h = 7 * pitch - gap
    width = left_margin + grid_w + right_margin
    height = top_margin + grid_h + bottom_margin

    def cx(week_idx):
        return left_margin + week_idx * pitch + cell / 2

    def cy(weekday):
        return top_margin + weekday * pitch + cell / 2

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
                month_labels.append((cx(wi) - cell / 2, top_margin - 10, label))

        for day in week["contributionDays"]:
            lvl = level_for_day(day, max_count)
            x = left_margin + wi * pitch
            y = top_margin + day["weekday"] * pitch
            fill = DARK_BY_LEVEL[lvl]
            stroke_attr = ' stroke="#22272e"' if lvl == 0 else ""
            cells_svg.append(
                f'<rect x="{int(x)}" y="{int(y)}" width="{cell}" height="{cell}" rx="2.5" '
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
    # cell size is even, so every vertex lands on a whole-number coordinate
    path_d = "M " + " L ".join(f"{int(x)} {int(y)}" for x, y, _ in points)

    key_times = [round(i / (n - 1), 4) if n > 1 else 0 for i in range(n)]
    key_times_attr = ";".join(str(t) for t in key_times)

    radius_by_level = {0: 3.0, 1: 3.4, 2: 3.9, 3: 4.6, 4: 5.6}
    opacity_by_level = {0: 0.45, 1: 0.6, 2: 0.72, 3: 0.86, 4: 1.0}
    r_values = ";".join(str(radius_by_level[lvl]) for _, _, lvl in points)
    op_values = ";".join(str(opacity_by_level[lvl]) for _, _, lvl in points)

    seg_len = pitch
    total_len = seg_len * (n - 1) if n > 1 else 0
    dur = "26s"
    dash_visible = seg_len * 9

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

    # Particles trail the orb in time (negative begin = already progressed) but ride the
    # same path via <mpath> so no per-point keyframe list needs duplicating.
    particles = []
    for offset in ("-1.4s", "-2.9s", "-4.3s"):
        particles.append(f'''
    <circle r="1.6" fill="#8f6bff" opacity="0.55" filter="url(#neonGlowSoft)">
      <animateMotion dur="{dur}" begin="{offset}" repeatCount="indefinite" rotate="0" calcMode="linear">
        <mpath href="#runnerPath" xlink:href="#runnerPath"/>
      </animateMotion>
      <animate attributeName="opacity" values="0.15;0.6;0.15" dur="1.6s" begin="{offset}" repeatCount="indefinite"/>
    </circle>''')

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     viewBox="0 0 {width} {height}" width="100%"
     role="img" aria-labelledby="neonTitle neonDesc">
  <title id="neonTitle">Neon contribution runner</title>
  <desc id="neonDesc">Animated traversal of {LOGIN}'s real GitHub contribution graph — {total} contributions in the last year. Regenerated automatically by GitHub Actions.</desc>

  <defs>
    <linearGradient id="neonTrailGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#7c3aed"/>
      <stop offset="55%" stop-color="#5b8def"/>
      <stop offset="100%" stop-color="#22d3ee"/>
    </linearGradient>
    <radialGradient id="orbGrad" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#eafcff"/>
      <stop offset="45%" stop-color="#67e8f9"/>
      <stop offset="100%" stop-color="#7c3aed" stop-opacity="0"/>
    </radialGradient>
    <filter id="neonGlow" x="-200%" y="-200%" width="500%" height="500%">
      <feGaussianBlur stdDeviation="2.6" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
    <filter id="neonGlowSoft" x="-200%" y="-200%" width="500%" height="500%">
      <feGaussianBlur stdDeviation="1.4" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
    <path id="runnerPath" d="{path_d}"/>
  </defs>

  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="14" fill="#0a0a0a" stroke="#1f1f1f"/>

  <text x="20" y="24" font-family="Consolas, 'SF Mono', monospace" font-size="10" letter-spacing="1" fill="#555">SIGNAL // CONTRIB</text>
  <circle cx="{width - 22}" cy="21" r="3" fill="#8f6bff">
    <animate attributeName="opacity" values="1;0.35;1" dur="2.2s" repeatCount="indefinite"/>
  </circle>

  {month_svg}
  {weekday_svg}

  <g>{"".join(cells_svg)}</g>

  <use href="#runnerPath" xlink:href="#runnerPath" fill="none" stroke="#2a2a3a" stroke-width="1"
       stroke-linejoin="round" opacity="0.35"/>

  <use href="#runnerPath" xlink:href="#runnerPath" fill="none" stroke="url(#neonTrailGrad)"
       stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" filter="url(#neonGlow)"
       stroke-dasharray="{dash_visible:.1f} {total_len + dash_visible:.1f}" opacity="0.9">
    <animate attributeName="stroke-dashoffset" values="0;-{total_len + dash_visible:.1f}" dur="{dur}"
      repeatCount="indefinite" calcMode="linear"/>
  </use>
  {"".join(particles)}

  <circle r="3" fill="url(#orbGrad)" filter="url(#neonGlow)">
    <animateMotion dur="{dur}" repeatCount="indefinite" rotate="0" keyPoints="{key_times_attr}"
      keyTimes="{key_times_attr}" calcMode="linear">
      <mpath href="#runnerPath" xlink:href="#runnerPath"/>
    </animateMotion>
    <animate attributeName="r" values="{r_values}" keyTimes="{key_times_attr}" dur="{dur}"
      repeatCount="indefinite" calcMode="linear"/>
    <animate attributeName="opacity" values="{op_values}" keyTimes="{key_times_attr}" dur="{dur}"
      repeatCount="indefinite" calcMode="linear"/>
  </circle>

  <text x="20" y="{height - 14}" font-family="Consolas, 'SF Mono', monospace" font-size="9" letter-spacing="0.5" fill="#8a8a8a">{total} CONTRIBUTIONS · LAST 12 MONTHS</text>
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
        print(f"WARNING: generated SVG failed a basic sanity check. Leaving existing file untouched.",
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
