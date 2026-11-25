"""Generate an animated GitHub stats card that includes private contributions.

Reads a token from the GH_TOKEN environment variable (a classic personal access
token with `repo` and `read:user` scopes), queries the GraphQL API as that user
and writes an SVG card to the path given as the first argument.
"""

import datetime as dt
import json
import os
import sys
import urllib.request

API = "https://api.github.com/graphql"


def gql(token, query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-stats-card"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if data.get("errors"):
        raise SystemExit(f"GraphQL error: {data['errors']}")
    return data["data"]


def collect(token):
    base = gql(
        token,
        """query {
          viewer {
            login name createdAt
            pullRequests { totalCount }
            merged: pullRequests(states: MERGED) { totalCount }
            issues { totalCount }
            repositories(ownerAffiliations: OWNER, first: 100) {
              totalCount nodes { stargazerCount }
            }
            repositoriesContributedTo(
              contributionTypes: [COMMIT, PULL_REQUEST], first: 1, includeUserRepositories: true
            ) { totalCount }
            contributionsCollection { contributionCalendar { totalContributions } }
          }
        }""",
    )["viewer"]

    # All-time contributions: the API caps one collection at a year, so sum per year.
    start_year = int(base["createdAt"][:4])
    now = dt.datetime.now(dt.timezone.utc)
    all_time = 0
    for year in range(start_year, now.year + 1):
        frm = f"{year}-01-01T00:00:00Z"
        to = f"{year}-12-31T23:59:59Z" if year < now.year else now.strftime("%Y-%m-%dT%H:%M:%SZ")
        res = gql(
            token,
            """query($from: DateTime!, $to: DateTime!) {
              viewer { contributionsCollection(from: $from, to: $to) {
                contributionCalendar { totalContributions }
              } }
            }""",
            {"from": frm, "to": to},
        )
        all_time += res["viewer"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]

    return {
        "name": base["name"] or base["login"],
        "all_time": all_time,
        "last_year": base["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "prs": base["pullRequests"]["totalCount"],
        "merged": base["merged"]["totalCount"],
        "repos": base["repositories"]["totalCount"],
        "contributed": base["repositoriesContributedTo"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in base["repositories"]["nodes"]),
    }


def fmt(n):
    return f"{n:,}"


def render(s):
    tiles = [
        ("Total Contributions", fmt(s["all_time"]), "all time", "#a78bfa"),
        ("Last 12 Months", fmt(s["last_year"]), "contributions", "#38bdf8"),
        ("Pull Requests", fmt(s["prs"]), f"{fmt(s['merged'])} merged", "#f472b6"),
        ("Repositories", fmt(s["repos"]), f"contributed to {fmt(s['contributed'])}", "#34d399"),
    ]
    w, h = 820, 200
    tile_w, gap, x0, y0 = 182, 14, 26, 64
    parts = []
    for i, (label, value, sub, color) in enumerate(tiles):
        x = x0 + i * (tile_w + gap)
        delay = 0.15 + i * 0.15
        parts.append(f"""
  <g class="tile" style="animation-delay:{delay:.2f}s">
    <rect x="{x}" y="{y0}" width="{tile_w}" height="108" rx="12" fill="#161b22" stroke="#30363d"/>
    <rect x="{x}" y="{y0}" width="4" height="108" rx="2" fill="{color}"/>
    <text x="{x + 18}" y="{y0 + 28}" class="label">{label}</text>
    <text x="{x + 18}" y="{y0 + 70}" class="value" fill="{color}">{value}</text>
    <text x="{x + 18}" y="{y0 + 92}" class="sub">{sub}</text>
  </g>""")
    updated = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).strftime("%d %b %Y")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{s['name']}'s GitHub stats">
  <title>{s['name']}'s GitHub stats, including private work</title>
  <style>
    text {{ font-family: 'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif; }}
    .title {{ font-size: 18px; font-weight: 700; fill: #a78bfa; }}
    .note {{ font-size: 11px; fill: #8b949e; }}
    .label {{ font-size: 12px; font-weight: 600; fill: #c9d1d9; }}
    .value {{ font-size: 30px; font-weight: 800; }}
    .sub {{ font-size: 11px; fill: #8b949e; }}
    .tile {{ opacity: 0; animation: rise .7s ease-out forwards; }}
    @keyframes rise {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: translateY(0); }} }}
  </style>
  <rect width="{w}" height="{h}" rx="14" fill="#0d1117"/>
  <text x="26" y="40" class="title">{s['name']}'s GitHub Stats</text>
  <text x="{w - 26}" y="40" class="note" text-anchor="end">incl. private work · updated {updated}</text>
{''.join(parts)}
</svg>
"""


def main():
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN is not set")
    out = sys.argv[1] if len(sys.argv) > 1 else "github-stats.svg"
    stats = collect(token)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(stats))
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
