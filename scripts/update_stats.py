#!/usr/bin/env python3
"""Generate assets/stats.svg from live GitHub (+ optional LeetCode) data.

No third-party services or dependencies. Uses the workflow's GITHUB_TOKEN.
Usage:
    GITHUB_TOKEN=... python scripts/update_stats.py
    python scripts/update_stats.py --mock scripts/mock_data.json   # offline test
"""
import argparse
import datetime as dt
import html
import json
import os
import sys
import urllib.request

GH_USER = os.environ.get("GH_USER", "Keerthana-G-Pillai")
LC_USER = os.environ.get("LC_USER", "Keerthana_G_Pillai")
OUT = os.environ.get("STATS_OUT", "assets/stats.svg")
# Notebook JSON inflates byte counts and hides the real Python work.
EXCLUDE_LANGS = {"Jupyter Notebook"}

GH_QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 8, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

LC_QUERY = """
query($u: String!) {
  matchedUser(username: $u) {
    submitStats { acSubmissionNum { difficulty count } }
  }
}
"""


def post_json(url, payload, headers):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_github():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    data = post_json(
        "https://api.github.com/graphql",
        {"query": GH_QUERY, "variables": {"login": GH_USER}},
        {"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    if "errors" in data:
        sys.exit(f"GitHub GraphQL error: {data['errors']}")
    return data["data"]["user"]


def fetch_leetcode():
    try:
        data = post_json(
            "https://leetcode.com/graphql",
            {"query": LC_QUERY, "variables": {"u": LC_USER}},
            {"Content-Type": "application/json", "Referer": "https://leetcode.com"},
        )
        rows = data["data"]["matchedUser"]["submitStats"]["acSubmissionNum"]
        return next(r["count"] for r in rows if r["difficulty"] == "All")
    except Exception as exc:  # LeetCode is optional; never fail the run over it
        print(f"LeetCode skipped: {exc}", file=sys.stderr)
        return None


def streaks(days, today):
    counts = {d["date"]: d["contributionCount"] for d in days}
    dates = sorted(counts)
    longest = run = 0
    prev = None
    for d in dates:
        cur = dt.date.fromisoformat(d)
        if counts[d] > 0:
            run = run + 1 if prev and (cur - prev).days == 1 else 1
            longest = max(longest, run)
        else:
            run = 0
        prev = cur if counts[d] > 0 else None
    # current streak: walk back from today; today may still be empty
    cur_streak = 0
    day = today
    if counts.get(day.isoformat(), 0) == 0:
        day -= dt.timedelta(days=1)
    while counts.get(day.isoformat(), 0) > 0:
        cur_streak += 1
        day -= dt.timedelta(days=1)
    return cur_streak, longest


def language_mix(repos, limit=5):
    sizes, colors = {}, {}
    for repo in repos:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            if name in EXCLUDE_LANGS:
                continue
            sizes[name] = sizes.get(name, 0) + e["size"]
            colors[name] = e["node"]["color"] or "#8b949e"
    total = sum(sizes.values()) or 1
    top = sorted(sizes.items(), key=lambda kv: -kv[1])[:limit]
    return [(n, s / total * 100, colors[n]) for n, s in top]


def build_svg(user, leetcode, today):
    repos = user["repositories"]["nodes"]
    cc = user["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    cur, longest = streaks(days, today)
    stars = sum(r["stargazerCount"] for r in repos)
    langs = language_mix(repos)

    metrics = [
        ("Contributions (1y)", cc["contributionCalendar"]["totalContributions"]),
        ("Commits (1y)", cc["totalCommitContributions"]),
        ("Pull requests (1y)", cc["totalPullRequestContributions"]),
        ("Public repos", user["repositories"]["totalCount"]),
        ("Stars earned", stars),
        ("Current streak", f"{cur} d"),
        ("Longest streak", f"{longest} d"),
    ]
    if leetcode is not None:
        metrics.append(("LeetCode solved", leetcode))

    W = 800
    rows = []
    for i, (label, value) in enumerate(metrics):
        x = 28 + (i % 2) * 190
        y = 84 + (i // 2) * 44
        rows.append(
            f'<text x="{x}" y="{y}" class="lbl">{html.escape(label)}</text>'
            f'<text x="{x}" y="{y + 20}" class="val">{html.escape(str(value))}</text>'
        )
    H = 84 + ((len(metrics) + 1) // 2) * 44 + 8

    bar_x, bar_w, bar_y = 440, 332, 74
    segs, legend, cx = [], [], bar_x
    for i, (name, pct, color) in enumerate(langs):
        w = bar_w * pct / 100
        segs.append(f'<rect x="{cx:.1f}" y="{bar_y}" width="{w:.1f}" height="10" fill="{color}"/>')
        cx += w
        lx = bar_x + (i % 2) * 170
        ly = bar_y + 36 + (i // 2) * 26
        legend.append(
            f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{color}"/>'
            f'<text x="{lx + 16}" y="{ly}" class="leg">{html.escape(name)} {pct:.1f}%</text>'
        )

    stamp = today.strftime("%d %b %Y")
    return f"""<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="GitHub stats for {html.escape(GH_USER)}">
  <style>
    text {{ font-family:'Segoe UI',Ubuntu,'Helvetica Neue',Arial,sans-serif; }}
    .bg  {{ fill:#ffffff; stroke:#d0d7de; }}
    .ttl {{ font-size:16px; font-weight:600; fill:#7c3aed; }}
    .lbl {{ font-size:12px; fill:#656d76; }}
    .val {{ font-size:18px; font-weight:600; fill:#1f2328; }}
    .leg {{ font-size:12px; fill:#1f2328; }}
    .ts  {{ font-size:10px; fill:#656d76; }}
    @media (prefers-color-scheme: dark) {{
      .bg  {{ fill:#0d1117; stroke:#30363d; }}
      .ttl {{ fill:#a78bfa; }}
      .lbl, .ts {{ fill:#8b949e; }}
      .val, .leg {{ fill:#e6edf3; }}
    }}
  </style>
  <rect class="bg" x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="10"/>
  <text x="28" y="38" class="ttl">GitHub stats</text>
  <text x="{bar_x}" y="38" class="ttl">Top languages</text>
  {''.join(rows)}
  {''.join(segs)}
  {''.join(legend)}
  <text x="{W - 16}" y="{H - 10}" text-anchor="end" class="ts">updated {stamp}</text>
</svg>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", help="JSON file with a GraphQL `user` object (offline test)")
    args = ap.parse_args()

    if args.mock:
        with open(args.mock) as f:
            user, leetcode = json.load(f), 123
        today = dt.date(2026, 9, 20)
    else:
        user, leetcode = fetch_github(), fetch_leetcode()
        today = dt.datetime.now(dt.timezone.utc).date()

    svg = build_svg(user, leetcode, today)
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
