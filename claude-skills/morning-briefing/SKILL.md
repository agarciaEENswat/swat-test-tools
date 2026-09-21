---
name: morning-briefing
description: Run the daily morning JIRA briefing for Eagle Eye Networks support. Covers new VMSSUP tickets since yesterday, open high/medium priority tickets, and team response staleness via jira-stalker. Use when user asks for "morning briefing" or "daily briefing".
allowed-tools: Bash
---

# Morning Briefing

Runs a full daily JIRA briefing for the EEN support team. Covers three sections:
1. New tickets since yesterday
2. Open high/medium priority tickets
3. Team response staleness (via jira-stalker.py)

## CRITICAL: Credentials

Every command that talks to JIRA or Zulip must run under `~/.local/bin/briefing-env`, which
exports the credentials from the Bitwarden `shell-env` note into that one
process:

```bash
~/.local/bin/briefing-env --check    # confirm creds resolve before starting; runs nothing
```

`source ~/.zshrc` does **not** work here — `bw-env.zsh` only *defines* `bwload`
and deliberately does not run at shell startup, and every tool call is a fresh
process anyway, so nothing inherits a `bwload` from another terminal.

If `--check` reports the vault is locked, stop and tell the user to run
`~/.local/bin/briefing-env --unlock` in their own terminal (it needs their master password).
Do not attempt the unlock from here — there is no tty to prompt on.

Because the outer shell expands `$JIRA_EMAIL` before `~/.local/bin/briefing-env` runs, always
defer expansion to the child with `sh -c '...'` and pass JSON bodies on stdin
via `-d @-`, as every example below does.

## Step 0 — Account Field Backfill

Before anything else, backfill account fields on any CI tickets that are missing them:

```bash
~/.local/bin/briefing-env python3 ~/Scripts/jira-account-backfill.py --silent
```

This outputs a single JSON line. Parse it:
```python
import json, subprocess, os
result = json.loads(backfill_output)
# {"updated": [{"key": "EEPD-XXXXX", "acct": "...", "sub": "..."}, ...], "failed": [], "total": N}
```

Store as `backfill_result`. If `result["total"] > 0`, add an Account Field Updates section to the report (see Output Format). If total is 0, skip the section entirely — no noise on clean days.

## Step 1 — Load Yesterday's Snapshot

Before running any sections, load yesterday's cache file (if it exists):

```bash
mkdir -p ~/.claude/morning-briefing-cache
YESTERDAY=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d yesterday +%Y-%m-%d)
CACHE_FILE="$HOME/.claude/morning-briefing-cache/${YESTERDAY}.json"
if [ -f "$CACHE_FILE" ]; then cat "$CACHE_FILE"; else echo "{}"; fi
```

Store this as `yesterday_snapshot`. Use it to compute deltas throughout the briefing:
- If a count increased: show `▲N`
- If a count decreased: show `▼N`  
- If unchanged: show no delta
- If no yesterday data: show no delta (first run)

## Key Facts

- Support tickets use project key `VMSSUP` (not `EENS` — the board URL says EENS but the JQL project key is VMSSUP)
- Exclude bot-created tickets: `NOT (description ~ "task id" AND reporter in (604fb2f681b82500682d022a))`
- Always use `statusCategory != Done` on priority queries — otherwise old closed tickets flood results
- Do NOT include new EEPD tickets — only VMSSUP for new ticket alerts
- Today's date is always available in the system context

## Section 1 — New Tickets Since Yesterday

```bash
~/.local/bin/briefing-env sh -c 'curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://eagleeyenetworks.atlassian.net/rest/api/3/search/jql" \
  -H "Content-Type: application/json" -d @-' <<'JSON'
{
  "jql": "project = VMSSUP AND created >= \"YYYY-MM-DD\" AND NOT (description ~ \"task id\" AND reporter in (604fb2f681b82500682d022a)) ORDER BY created DESC",
  "maxResults": 30,
  "fields": ["summary", "status", "priority", "created", "assignee"]
}
JSON
```

Replace `YYYY-MM-DD` with yesterday's date.

Parse and display as a table: Ticket | Priority | Status | Assignee | Created | Summary

### 1b — New EEPD/Infrastructure customer-impact tickets since yesterday

Run in parallel with Section 1:

```bash
~/.local/bin/briefing-env sh -c 'curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://eagleeyenetworks.atlassian.net/rest/api/3/search/jql" \
  -H "Content-Type: application/json" -d @-' <<'JSON'
{
  "jql": "project in (EEPD, Infrastructure) AND labels in (customer-impact) AND created >= \"YYYY-MM-DD\" AND issuetype not in (Improvement, story) ORDER BY created DESC",
  "maxResults": 30,
  "fields": ["summary", "status", "priority", "created", "assignee", "project", "labels"]
}
JSON
```

Display as a table: Ticket | Project | Priority | Status | Assignee | Created | Summary
If none: show `None.`

## Section 2 — Open High Priority (flag if no update in ≥3 days)

```bash
~/.local/bin/briefing-env sh -c 'curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://eagleeyenetworks.atlassian.net/rest/api/3/search/jql" \
  -H "Content-Type: application/json" -d @-' <<'JSON'
{
  "jql": "project = VMSSUP AND priority in (Highest, High) AND statusCategory != Done AND NOT (description ~ \"task id\" AND reporter in (604fb2f681b82500682d022a)) ORDER BY updated ASC",
  "maxResults": 20,
  "fields": ["summary", "status", "priority", "updated", "created", "assignee"]
}
JSON
```

Flag tickets with `updated >= 3 days ago` as `*** NO MOVEMENT`.
Display as a table: Ticket | Priority | Status | Assignee | Created | Summary

## Section 3 — Open Medium Priority (flag if no update in ≥7 days)

```bash
~/.local/bin/briefing-env sh -c 'curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://eagleeyenetworks.atlassian.net/rest/api/3/search/jql" \
  -H "Content-Type: application/json" -d @-' <<'JSON'
{
  "jql": "project = VMSSUP AND priority = Medium AND statusCategory != Done AND NOT (description ~ \"task id\" AND reporter in (604fb2f681b82500682d022a)) ORDER BY updated ASC",
  "maxResults": 20,
  "fields": ["summary", "status", "priority", "updated", "created", "assignee"]
}
JSON
```

Flag tickets with `updated >= 7 days ago` as `*** STALLED`.
Display as a table: Ticket | Status | Assignee | Created | Summary

## Section 4 — Total Open Customer Impact Tickets

Fetch all tickets (paginate if needed) to compute age distribution:

```bash
~/.local/bin/briefing-env sh -c 'curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://eagleeyenetworks.atlassian.net/rest/api/3/search/jql" \
  -H "Content-Type: application/json" -d @-' <<'JSON'
{
  "jql": "((project = EENS AND reporter not in (604fb2f681b82500682d022a)) OR (project in (EEPD, Infrastructure) AND labels in (customer-impact))) AND issuetype not in (Improvement, story) AND status not in (closed, Done, resolved, \"Won't Investigate\", \"Not Needed\", Duplicate) AND priority not in (Low, Lowest) AND (duedate is EMPTY OR duedate <= now()) ORDER BY created ASC",
  "maxResults": 100,
  "fields": ["created", "priority", "customfield_10500"]
}
JSON
```

If `nextPageToken` is present in the response, keep paginating until all tickets are collected.

Then compute age distribution with priority breakdown in Python:

```python
from datetime import datetime, timezone
from collections import defaultdict

BUCKET_LABELS = ["< 1 week", "1–2 weeks", "2–4 weeks", "1–3 months", "3–6 months", "6+ months"]
buckets = {b: defaultdict(int) for b in BUCKET_LABELS}
now = datetime.now(timezone.utc)

def normalize_priority(p):
    if p in ("Highest", "High"): return "High"
    if p in ("Lowest", "Low"):   return "Low"
    return p  # Medium

def parse_jira_dt(raw):
    # JIRA returns offsets without a colon ("...883-0500"), which
    # fromisoformat only accepts from Python 3.11 on. `python3` here is 3.9.
    s = raw.replace("Z", "+00:00")
    if len(s) >= 5 and s[-5] in "+-" and s[-3] != ":":
        s = f"{s[:-2]}:{s[-2:]}"
    return datetime.fromisoformat(s)

for issue in issues:
    created = parse_jira_dt(issue["fields"]["created"])
    days = (now - created).days
    prio = normalize_priority((issue["fields"].get("priority") or {}).get("name", "Medium"))
    if days < 7:        buckets["< 1 week"][prio] += 1
    elif days < 14:     buckets["1–2 weeks"][prio] += 1
    elif days < 28:     buckets["2–4 weeks"][prio] += 1
    elif days < 90:     buckets["1–3 months"][prio] += 1
    elif days < 180:    buckets["3–6 months"][prio] += 1
    else:               buckets["6+ months"][prio] += 1
```

Display total count (with delta from yesterday if available) and a bar chart (bars scaled to max bucket, 10 chars wide). For the priority breakdown, only show priorities that are non-zero in that bucket, in order: High, Medium, Low:

```
### Total Open Customer Impact Tickets: 41 ▲2

Age Distribution:
  < 1 week    ████░░░░░░  4   (High: 2, Medium: 2)
  1–2 weeks   ██████░░░░  6   (High: 1, Medium: 5)
  2–4 weeks   ████████░░  9   (Medium: 9)
  1–3 months  ███████░░░  8   (High: 3, Medium: 5)
  3–6 months  ████░░░░░░  4   (Medium: 4)
  6+ months   ███░░░░░░░  3   (Medium: 2, Low: 1)
```

Compare today's ticket IDs against `yesterday_snapshot.customer_impact_ids` to list newly added and resolved tickets beneath the chart:
```
  New since yesterday: EEPD-115400, EEPD-115401
  Resolved since yesterday: EEPD-113200
```

## Section 5 — Out of Spec Work Items

Customer-impact tickets that have been open longer than allowed for their priority:
- **Highest**: open > 7 days
- **High**: open > 14 days
- **Any**: open > 28 days

```bash
~/.local/bin/briefing-env sh -c 'curl -s -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
  -X POST "https://eagleeyenetworks.atlassian.net/rest/api/3/search/jql" \
  -H "Content-Type: application/json" -d @-' <<'JSON'
{
  "jql": "((project = EENS AND reporter not in (604fb2f681b82500682d022a)) OR (project in (EEPD, Infrastructure) AND labels in (customer-impact))) AND issuetype not in (Improvement, story) AND statusCategory not in (Done) AND priority not in (Low, Lowest) AND (duedate is EMPTY OR duedate <= now()) AND ((priority in (High) AND created < \"-14d\") OR (priority in (Highest) AND created < \"-7d\") OR (created < \"-28d\")) ORDER BY priority DESC, created ASC",
  "maxResults": 50,
  "fields": ["summary", "status", "priority", "created", "assignee", "project"]
}
JSON
```

Display as a table: Ticket | Project | Priority | Status | Assignee | Age | Summary
Include age in days. Lead with total count and delta vs yesterday (`yesterday_snapshot.out_of_spec_ids`).
Note tickets that are newly out-of-spec today vs yesterday, and any that have been resolved.

## Section 7 — Sprint Carry-Over Analysis

This section runs **after Section 4** since it reuses the customer-impact ticket keys already collected.

For each ticket key, fetch the changelog. This snippet reads credentials from
`os.environ`, so the interpreter itself must be launched under the wrapper —
`~/.local/bin/briefing-env python3 script.py`, not a bare `python3`:

```python
import subprocess, json, os

def fetch_changelog(key, email, token):
    url = f"https://eagleeyenetworks.atlassian.net/rest/api/3/issue/{key}/changelog"
    r = subprocess.run(
        ['curl', '-s', '-u', f'{email}:{token}', url],
        capture_output=True, text=True
    )
    try:
        data = json.loads(r.stdout)
        histories = data.get('values', [])
        sprint_changes = []
        for h in histories:
            for item in h.get('items', []):
                if item.get('field') == 'Sprint':
                    sprint_changes.append({
                        'date': h['created'][:10],
                        'from': item.get('fromString', ''),
                        'to': item.get('toString', '')
                    })
        return sprint_changes
    except:
        return []

email = os.environ.get('JIRA_EMAIL')
token = os.environ.get('JIRA_API_TOKEN')
changelogs = {key: fetch_changelog(key, email, token) for key in ticket_keys}
```

Categorize each ticket:
- **Repeatedly punted**: 3+ sprint changes — these keep getting added to sprints without being closed
- **Carried over**: 1-2 sprint changes — started but not finished
- **Never in a sprint**: 0 sprint changes — sitting in backlog with no commitment

Display summary counts and a breakdown table:

```
### Sprint Carry-Over Analysis
  Repeatedly punted (3+ sprints):  N  (these need escalation)
  Carried over (1-2 sprints):      N
  Never in a sprint (backlog):     N  (no engineering commitment)

🚨 Repeatedly Punted:
  EEPD-XXXXX | High | In Progress | 45d | Assignee | Summary (X sprints)

⚠ Never in a Sprint (oldest first):
  EEPD-XXXXX | Medium | To Do | 32d | Assignee | Summary
```

Save sprint carry-over IDs to the snapshot for delta comparison:
- `sprint_punted_ids`: tickets with 3+ sprint changes
- `sprint_backlog_ids`: tickets with 0 sprint changes

### Auto-label Repeatedly Punted Tickets

After categorizing, sync the `repeatedly-punted` JIRA label so it always reflects current sprint-change counts. This makes the set queryable via JQL (`labels = "repeatedly-punted"`) without hardcoding keys.

Add the label to tickets newly qualifying (3+ sprints). Remove it from tickets that previously had it but no longer qualify (e.g. resolved).

```python
import subprocess, json, os

email = os.environ.get('JIRA_EMAIL')
token = os.environ.get('JIRA_API_TOKEN')
BASE = "https://eagleeyenetworks.atlassian.net/rest/api/3/issue"

def get_labels(key):
    r = subprocess.run(['curl', '-s', '-u', f'{email}:{token}', f'{BASE}/{key}?fields=labels'],
        capture_output=True, text=True)
    return [l['name'] for l in json.loads(r.stdout).get('fields', {}).get('labels', [])]

def set_labels(key, labels):
    body = json.dumps({"update": {"labels": [{"set": labels}]}})
    subprocess.run(['curl', '-s', '-u', f'{email}:{token}', '-X', 'PUT',
        '-H', 'Content-Type: application/json', '-d', body, f'{BASE}/{key}'],
        capture_output=True)

# Add label to newly punted tickets
for key in punted_keys:
    labels = get_labels(key)
    if 'repeatedly-punted' not in labels:
        set_labels(key, labels + ['repeatedly-punted'])
        print(f"  + labeled {key}")

# Remove label from tickets that no longer qualify
prev_punted = set(yesterday_snapshot.get('sprint_punted_ids', []))
for key in prev_punted - set(punted_keys):
    labels = get_labels(key)
    if 'repeatedly-punted' in labels:
        set_labels(key, [l for l in labels if l != 'repeatedly-punted'])
        print(f"  - removed label from {key}")
```

The live JQL for this set (bookmarkable):
```
labels = "repeatedly-punted" ORDER BY created ASC
```

## Section 8 — Open Tickets by Engineering Team

Using the customer-impact tickets already collected in Section 4, group by `customfield_10500` (Team field):

```python
from collections import defaultdict

team_counts = defaultdict(lambda: {"total": 0, "high": 0, "medium": 0, "low": 0})

for issue in issues:
    team = (issue["fields"].get("customfield_10500") or {}).get("name", "Unassigned")
    prio = normalize_priority((issue["fields"].get("priority") or {}).get("name", "Medium"))
    team_counts[team]["total"] += 1
    team_counts[team][prio.lower()] += 1

# Sort by total descending
sorted_teams = sorted(team_counts.items(), key=lambda x: x[1]["total"], reverse=True)
```

Display as a table sorted by total, with priority breakdown:

```
### Open Customer Impact Tickets by Team

| Team                  | Total | High | Medium | Low |
|-----------------------|-------|------|--------|-----|
| Video - Storage (252) |    12 |    3 |      8 |   1 |
| ...                   |   ... |  ... |    ... | ... |
| Unassigned            |     2 |    0 |      2 |   0 |
```

Compare totals against `yesterday_snapshot.team_counts` and show deltas (▲/▼) in the Total column where changed.

Save `team_counts` to today's snapshot as a dict of `{team_name: total}`.

## Section 6 — Needs Team Response + Waiting on Support (jira-stalker)

Run the stalker script twice — once for high (1-day threshold), once for medium (2-day threshold). Run in parallel with Section 4:

```bash
~/.local/bin/briefing-env python3 ~/Scripts/jira-stalker.py --prio high --days 1 2>&1
~/.local/bin/briefing-env python3 ~/Scripts/jira-stalker.py --prio medium --days 2 2>&1
```

The stalker now outputs **two buckets**:

**WAITING ON SUPPORT TO VERIFY** — tickets where a non-team member's recent comment contains handoff language ("please validate", "fix deployed", "has been released", etc.) and no team member has commented since. These are tickets where **we** own the next action — not engineering. Surface these prominently at the top of Section 6, before Needs Team Response.

**NEEDS RESPONSE** — tickets where the team hasn't replied within the threshold. Present results grouped by last team commenter. Include urgency score, assignee, last team comment age, latest activity, and sprint deadline. Highlight:
- Sprint already ended (urgent)
- Score >= 10 (very overdue)
- "No team comment yet" group (critical)

## Output Format

```
## Morning Briefing — [DATE]

### New Tickets Since Yesterday
[table or "None"]

### High Priority — Open
[table with NO MOVEMENT flags, or "None currently open"]

### Medium Priority — Open
[table with STALLED flags]

### Total Open Customer Impact Tickets: N

### Waiting on Support to Verify (N tickets)  ← omit section if 0
[ticket | assignee | handoff by | snippet of handoff comment]

### Needs Team Response
**High** (>1 day without team reply — N tickets)
[grouped by last team member, urgency score, sprint info]

**Medium** (>2 days without team reply — N tickets)
[grouped by last team member, urgency score, sprint info]

### Out of Spec Work Items (N)
[table: Ticket | Project | Priority | Status | Assignee | Age | Summary]

### Sprint Carry-Over Analysis
  Repeatedly punted (3+ sprints):  N
  Carried over (1-2 sprints):      N
  Never in a sprint (backlog):     N
[punted tickets listed with sprint count]
[top 10 oldest never-in-sprint tickets]

### Open Tickets by Engineering Team
[table: Team | Total (±delta) | High | Medium | Low]

### Account Field Updates (N tickets backfilled)  ← only include if N > 0
- KEY → Account Name / Sub-account Name
- KEY → Account Name
```

Run all sections in parallel where possible (sections 1, 2, 3, 5, 6 are independent API calls that can run concurrently; sections 7 and 8 run after section 4 completes).

## Save Today's Snapshot

After all sections are compiled, save a cache file for tomorrow's comparison. Use Python to write the JSON properly:

```python
import json, os, glob
from datetime import datetime

data = {
  "date": TODAY,
  "customer_impact_total": N,
  "customer_impact_ids": [...],
  "out_of_spec_total": N,
  "out_of_spec_ids": [...],
  "open_high_ids": [...],
  "open_medium_ids": [...],
  "needs_response_high_ids": [...],
  "needs_response_medium_ids": [...],
  "sprint_punted_ids": [...],     # tickets with 3+ sprint changes
  "sprint_backlog_ids": [...],    # tickets never in a sprint
  "team_counts": {"Team Name": N, ...}  # total open customer-impact per team
}

os.makedirs(os.path.expanduser('~/.claude/morning-briefing-cache'), exist_ok=True)
with open(os.path.expanduser(f'~/.claude/morning-briefing-cache/{TODAY}.json'), 'w') as f:
    json.dump(data, f, indent=2)

# Keep only last 7 days
for old in glob.glob(os.path.expanduser('~/.claude/morning-briefing-cache/*.json')):
    if os.path.getmtime(old) < (datetime.now().timestamp() - 7*86400):
        os.remove(old)
```

## Generate Detailed Report Document

Before sending to Zulip, generate a full markdown report file at `~/Documents/Morning Briefing/morning-briefing-YYYY-MM-DD.md`. Create the directory if it doesn't exist (`mkdir -p ~/Documents/Morning\ Briefing`). Using a date-based filename means same-day reruns automatically overwrite the previous file.

The document should contain **all sections in full detail** — every ticket listed, not just summaries. This is the shareable version for leadership. Include:

1. Header with date and key metrics
2. Section 1: All new tickets (full table)
3. Section 2 & 3: All high/medium open tickets (full tables with NO MOVEMENT / STALLED flags)
4. Section 4: Customer impact age chart + full ticket list
5. Section 6: Waiting on Support to Verify (if any) + Full jira-stalker output — Needs Team Response (High + Medium)
6. Section 5: Full out-of-spec table
7. Section 7: Full sprint carry-over breakdown — all three categories (punted, carried over, never in sprint) with complete ticket details
8. Section 8: Open tickets by engineering team
9. Account Field Updates: only if `backfill_result["total"] > 0` — list each updated ticket as `KEY → Account / Sub-account`

## Final Step — Upload Document and Send Briefing to Zulip

### Step 1: Upload the report document

```bash
~/.local/bin/briefing-env sh -c 'curl -s -u "$ZULIP_EMAIL:$ZULIP_API_KEY" \
  "$ZULIP_SITE/api/v1/user_uploads" \
  -F "filename=@$HOME/Documents/Morning Briefing/morning-briefing-YYYY-MM-DD.md"' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['uri'])"
```

That prints the `DOC_URI` to use in the message below.

### Step 2: Send briefing DM with document link

Append the document link to the end of the briefing message:

```
---
📎 [Full Detail Report](DOC_URI)
```

Write the message body to a file first, then let curl URL-encode it from there —
the briefing contains newlines, backticks and quotes that mangle badly when
inlined into a shell argument:

```bash
# briefing body already written to /tmp/briefing-msg.md
~/.local/bin/briefing-env sh -c 'curl -s -u "$ZULIP_EMAIL:$ZULIP_API_KEY" \
  "$ZULIP_SITE/api/v1/messages" \
  -d "type=direct" \
  -d "to=[747]" \
  --data-urlencode "content@/tmp/briefing-msg.md"'
```

Format the Zulip message in plain markdown (same content as shown in the Claude response). No need to confirm before sending — this is an automated step.
