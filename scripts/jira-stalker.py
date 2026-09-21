#!/usr/bin/env python3
"""
jira-stalker.py — Flag JIRA tickets where the team hasn't responded recently.

Usage:
  python3 jira-stalker.py [--days N] [--prio high|medium|both]

Reads JIRA_EMAIL and JIRA_API_TOKEN from environment.

Examples:
  python3 jira-stalker.py                  # check both queues, 2-day threshold
  python3 jira-stalker.py --days 1         # stricter: flag after 1 day
  python3 jira-stalker.py --prio high      # high priority only
"""

import os
import sys
import json
import argparse
import base64
from collections import defaultdict
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError
from datetime import datetime, timezone, timedelta


def parse_jira_dt(raw):
    """Parse a JIRA timestamp into an aware datetime.

    JIRA returns offsets without a colon ("2026-09-18T08:15:58.883-0500").
    datetime.fromisoformat only accepts that from Python 3.11 on, so insert the
    colon ourselves — otherwise this raises ValueError under 3.9/3.10.
    """
    s = raw.replace("Z", "+00:00")
    if len(s) >= 5 and s[-5] in "+-" and s[-3] != ":":
        s = f"{s[:-2]}:{s[-2:]}"
    return datetime.fromisoformat(s)


# ── Config ────────────────────────────────────────────────────────────────────

JIRA_BASE = "https://eagleeyenetworks.atlassian.net"
JIRA_API  = f"{JIRA_BASE}/rest/api/3"

TEAM = [
    "Christopher Luther",
    "Husain Alshaikhahmed",
    "David Pandy",
    "Adam Garcia",
]

HIGH_JQL = (
    '(project = Support OR project = "Eagle Eye Product Development" AND labels in (customer-impact)) '
    'AND type not in (story, Improvement) '
    'AND status not in (Resolved, "Won\'t Investigate", closed, done) '
    'AND reporter not in (604fb2f681b82500682d022a) '
    'AND (duedate is EMPTY OR duedate <= now()) '
    'AND priority not in (low, lowest) '
    'AND priority = High '
    'ORDER BY priority DESC, updated ASC'
)

MEDIUM_JQL = (
    '(project = Support OR project = "Eagle Eye Product Development" AND labels in (customer-impact)) '
    'AND type not in (story, Improvement) '
    'AND status not in (Resolved, "Won\'t Investigate", closed, done) '
    'AND reporter not in (604fb2f681b82500682d022a) '
    'AND (duedate is EMPTY OR duedate <= now()) '
    'AND priority not in (low, lowest) '
    'AND priority = Medium '
    'ORDER BY priority DESC, updated ASC'
)

# ── ANSI colors (auto-disabled when not a TTY) ────────────────────────────────

USE_COLOR = sys.stdout.isatty()

def red(s):    return f"\033[91m{s}\033[0m" if USE_COLOR else s
def yellow(s): return f"\033[93m{s}\033[0m" if USE_COLOR else s
def green(s):  return f"\033[92m{s}\033[0m" if USE_COLOR else s
def bold(s):   return f"\033[1m{s}\033[0m"  if USE_COLOR else s
def dim(s):    return f"\033[2m{s}\033[0m"  if USE_COLOR else s

# ── HTTP helpers (stdlib only) ────────────────────────────────────────────────

def _auth_header(email, token):
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    return f"Basic {creds}"

DEBUG = False

def jira_get(path, params, auth_header):
    url = f"{JIRA_API}/{path}?{urlencode(params)}"
    if DEBUG:
        print(dim(f"  GET {url}"), file=sys.stderr)
    req = Request(url, headers={"Authorization": auth_header, "Accept": "application/json"})
    try:
        with urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            if DEBUG:
                print(dim(f"  Response keys: {list(data.keys())}"), file=sys.stderr)
                print(dim(f"  Issue count: {len(data.get('issues', []))}"), file=sys.stderr)
                if data.get('warningMessages'):
                    print(yellow(f"  JIRA warnings: {data['warningMessages']}"), file=sys.stderr)
            return data
    except HTTPError as e:
        body = e.read().decode()
        print(red(f"  HTTP {e.code} from JIRA: {body[:400]}"), file=sys.stderr)
        raise

# ── JIRA logic ────────────────────────────────────────────────────────────────

def search_issues(jql, auth_header, max_results=200):
    issues = []
    params = {
        "jql": jql,
        "maxResults": min(50, max_results),
        "fields": "summary,status,assignee,priority,updated,comment,customfield_10007",
    }
    while True:
        data = jira_get("search/jql", params, auth_header)
        issues.extend(data.get("issues", []))
        next_token = data.get("nextPageToken")
        if not next_token or len(issues) >= max_results or not data.get("issues"):
            break
        params["nextPageToken"] = next_token
    return issues


def get_comments_for_issue(issue_key, auth_header):
    data = jira_get(f"issue/{issue_key}/comment", {"maxResults": 100, "orderBy": "-created"}, auth_header)
    return data.get("comments", [])


def last_team_comment(comments):
    """Return (datetime, author_name) of the most recent team comment, or (None, None)."""
    for c in sorted(comments, key=lambda x: x["created"], reverse=True):
        author = c.get("author", {}).get("displayName", "")
        if author in TEAM:
            dt = parse_jira_dt(c["created"])
            return dt, author
    return None, None


def last_any_comment(comments):
    """Return (datetime, author_name, body_text) of the most recent comment from anyone, or (None, None, None)."""
    if not comments:
        return None, None, None
    c = max(comments, key=lambda x: x["created"])
    author = c.get("author", {}).get("displayName", "Unknown")
    dt = parse_jira_dt(c["created"])
    body = _extract_comment_text(c.get("body", ""))
    return dt, author, body


def _extract_comment_text(content):
    """Extract plain text from ADF or string comment body."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if content.get("type") == "text":
            return content.get("text", "")
        if content.get("type") == "hardBreak":
            return "\n"
        if "content" in content:
            return _extract_comment_text(content["content"])
    if isinstance(content, list):
        return "".join(_extract_comment_text(i) for i in content)
    return ""


HANDOFF_KEYWORDS = [
    "please verify", "please validate", "please test", "please confirm", "please check",
    "can you verify", "can you validate", "can you confirm", "can you test", "can you check",
    "ready for verification", "ready for validation", "ready to test", "ready for testing",
    "fix has been", "fix is in", "fix deployed", "fix released",
    "has been deployed", "has been released", "has been fixed",
    "should be fixed", "should be resolved", "should now work",
    "deployed to", "released to", "pushed to",
    "let me know if", "let us know if",
    "waiting for support", "waiting on support",
]


def detect_waiting_on_support(comments):
    """
    Return (True, author, snippet) if any of the last 5 comments looks like
    a handoff to support, and no team member has commented since.
    """
    if not comments:
        return False, None, None
    recent = sorted(comments, key=lambda x: x["created"], reverse=True)[:5]
    for c in recent:
        author = c.get("author", {}).get("displayName", "")
        # Stop scanning if a team member commented after this point
        if author in TEAM:
            return False, None, None
        body = _extract_comment_text(c.get("body", "")).lower()
        for kw in HANDOFF_KEYWORDS:
            if kw in body:
                snippet = _extract_comment_text(c.get("body", "")).strip()[:120]
                return True, author, snippet
    return False, None, None


def get_sprint(fields):
    """Return (sprint_name, days_left, display_str) from customfield_10007."""
    sprints = fields.get("customfield_10007") or []
    if not sprints:
        return None, None, None
    active = [s for s in sprints if s.get("state") == "active"]
    sprint = active[0] if active else sprints[-1]
    name = sprint.get("name", "Unknown sprint")
    end_raw = sprint.get("endDate")
    if not end_raw:
        return name, None, "no end date"
    try:
        end_dt = parse_jira_dt(end_raw)
        days_left = (end_dt.date() - datetime.now(timezone.utc).date()).days
        if days_left < 0:
            display = red(f"⚠ SPRINT ENDED {abs(days_left)}d ago")
        elif days_left == 0:
            display = red("⚠ SPRINT ENDS TODAY")
        elif days_left <= 2:
            display = yellow(f"ends in {days_left}d")
        else:
            display = f"ends in {days_left}d ({end_dt.strftime('%b %d')})"
    except ValueError:
        days_left = None
        display = end_raw
    return name, days_left, display


def urgency_score(last_dt, sprint_days_left):
    """Higher = more urgent. Days since team comment + penalty for overdue sprint."""
    now = datetime.now(timezone.utc)
    if last_dt is None:
        team_days = 30  # never commented = treat as very old
    else:
        team_days = (now - last_dt).total_seconds() / 86400

    sprint_penalty = 0
    if sprint_days_left is not None and sprint_days_left < 0:
        sprint_penalty = abs(sprint_days_left) * 2

    return team_days + sprint_penalty


def format_age(dt):
    delta = datetime.now(timezone.utc) - dt
    hours = int(delta.total_seconds() / 3600)
    if hours < 1:
        return "< 1h ago"
    if hours < 24:
        return f"{hours}h ago"
    return f"{delta.days}d ago"

# ── Core check ────────────────────────────────────────────────────────────────

def run_check(jql, auth_header, days_threshold, label):
    print(f"\n{bold('='*62)}")
    print(f"  {bold(label)}")
    print(f"{bold('='*62)}")

    try:
        issues = search_issues(jql, auth_header)
    except HTTPError:
        return

    if not issues:
        print("  No tickets found matching the query.")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_threshold)
    stale = []
    waiting = []
    fresh = []

    for issue in issues:
        key      = issue["key"]
        summary  = issue["fields"]["summary"]
        assignee = (issue["fields"].get("assignee") or {}).get("displayName", "Unassigned")

        inline = issue["fields"].get("comment", {}).get("comments", [])
        comments = inline if inline else get_comments_for_issue(key, auth_header)

        last_dt, last_by      = last_team_comment(comments)
        any_dt,  any_by, _    = last_any_comment(comments)
        sprint_name, sprint_days_left, sprint_display = get_sprint(issue["fields"])
        score = urgency_score(last_dt, sprint_days_left)
        is_handoff, handoff_by, handoff_snippet = detect_waiting_on_support(comments)

        ticket = {
            "key": key, "summary": summary, "assignee": assignee,
            "last_dt": last_dt, "last_by": last_by,
            "any_dt": any_dt, "any_by": any_by,
            "sprint_name": sprint_name, "sprint_days_left": sprint_days_left,
            "sprint_display": sprint_display, "score": score,
            "handoff_by": handoff_by, "handoff_snippet": handoff_snippet,
        }

        if is_handoff:
            waiting.append(ticket)
        elif last_dt is None or last_dt < cutoff:
            stale.append(ticket)
        else:
            fresh.append(ticket)

    if not stale and not waiting:
        print(f"\n  {green('All tickets have recent team responses.')} ({len(fresh)} total)\n")
        return

    # ── Waiting on support to verify ─────────────────────────────────────────
    if waiting:
        waiting.sort(key=lambda t: t["score"], reverse=True)
        print(f"\n  {yellow(f'WAITING ON SUPPORT TO VERIFY — {len(waiting)} ticket(s)')}\n")
        for t in waiting:
            trunc = t["summary"][:60] + ("…" if len(t["summary"]) > 60 else "")
            sprint_str = f"{t['sprint_name']}  |  {t['sprint_display']}" if t["sprint_name"] else dim("no sprint")
            snippet_str = f"\n       {dim(repr(t['handoff_snippet'][:100]))}" if t["handoff_snippet"] else ""
            print(f"  {bold(t['key'])}  {trunc}")
            last_team_str = ('last team: ' + format_age(t['last_dt'])) if t['last_dt'] else 'no team comment'
            print(f"       {dim('Assignee:')} {t['assignee']}  |  {yellow('handoff by ' + t['handoff_by'])}  |  {dim(last_team_str)}")
            print(f"       {dim('Sprint:')} {sprint_str}{snippet_str}")
            print(f"       {dim('https://eagleeyenetworks.atlassian.net/browse/' + t['key'])}")
            print()
        print()

    # Group stale tickets by last team member who commented
    groups = defaultdict(list)
    for t in stale:
        group_key = t["last_by"] if t["last_by"] else "— No team comment yet —"
        groups[group_key].append(t)

    # Sort each group by urgency score descending
    for g in groups.values():
        g.sort(key=lambda t: t["score"], reverse=True)

    # Print "no team comment" group first, then team members sorted by max score
    ordered_groups = []
    no_comment_group = groups.pop("— No team comment yet —", [])
    if no_comment_group:
        ordered_groups.append(("— No team comment yet —", no_comment_group))
    for member in sorted(groups, key=lambda m: max(t["score"] for t in groups[m]), reverse=True):
        ordered_groups.append((member, groups[member]))

    total_stale = sum(len(g) for _, g in ordered_groups)
    print(f"\n  {red(f'NEEDS RESPONSE — {total_stale} ticket(s)')}\n")

    for member, tickets in ordered_groups:
        print(f"  {bold(member)}  {dim(f'({len(tickets)} ticket(s))')}")
        print(f"  {'─'*58}")
        for t in tickets:
            score_str = f"[{int(t['score'])}]"
            if t["score"] >= 10:
                score_display = red(score_str)
            elif t["score"] >= 5:
                score_display = yellow(score_str)
            else:
                score_display = dim(score_str)

            if t["last_dt"] is None:
                team_str = red("no team comment")
            else:
                age_h = (datetime.now(timezone.utc) - t["last_dt"]).total_seconds() / 3600
                color = red if age_h > 48 else yellow
                team_str = color(f"team: {format_age(t['last_dt'])}")

            last_str = dim(f"last: {format_age(t['any_dt'])} by {t['any_by']}") if t["any_dt"] else dim("no comments")
            sprint_str = f"{t['sprint_name']}  |  {t['sprint_display']}" if t["sprint_name"] else dim("no sprint")

            trunc = t["summary"][:60] + ("…" if len(t["summary"]) > 60 else "")
            print(f"  {score_display} {bold(t['key'])}  {trunc}")
            print(f"       {dim('Assignee:')} {t['assignee']}  |  {team_str}  |  {last_str}")
            print(f"       {dim('Sprint:')} {sprint_str}")
            print(f"       {dim(JIRA_BASE + '/browse/' + t['key'])}")
            print()
        print()

    if fresh:
        print(dim(f"  {len(fresh)} ticket(s) have recent responses — OK"))

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Flag JIRA tickets where the team hasn't commented recently.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Reads JIRA_EMAIL and JIRA_API_TOKEN from environment."
    )
    parser.add_argument(
        "--days", type=float, default=2.0,
        help="Threshold in days (default: 2). Accepts decimals, e.g. 0.5 for 12 hours."
    )
    parser.add_argument(
        "--prio", choices=["high", "medium", "both"], default="both",
        help="Which priority queue to check (default: both)"
    )
    parser.add_argument("--debug", action="store_true", help="Print raw API request/response info")
    args = parser.parse_args()

    email = os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_API_TOKEN")
    if not email or not token:
        print("ERROR: JIRA_EMAIL and JIRA_API_TOKEN must be set in environment.", file=sys.stderr)
        sys.exit(1)
    auth_header = _auth_header(email, token)
    global DEBUG
    DEBUG = args.debug

    threshold_str = f"{args.days}d" if args.days >= 1 else f"{int(args.days*24)}h"
    print(f"\n{bold('JIRA Stalker')} — no-response threshold: {bold(threshold_str)}")
    print(f"Team: {', '.join(TEAM)}")

    if args.prio in ("high", "both"):
        run_check(HIGH_JQL, auth_header, args.days, "HIGH PRIORITY")
    if args.prio in ("medium", "both"):
        run_check(MEDIUM_JQL, auth_header, args.days, "MEDIUM PRIORITY")

    print()


if __name__ == "__main__":
    main()
