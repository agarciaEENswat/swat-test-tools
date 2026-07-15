#!/usr/bin/env python3
"""EEN Customer Impact Health — local dashboard with team breakdown."""

import os, json, re, subprocess, pathlib
from flask import Flask, jsonify, render_template_string, request as flask_request
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from datetime import datetime, timezone, timedelta
from collections import defaultdict

app = Flask(__name__)

# Load credentials from shell if not already in environment
def _load_env():
    result = subprocess.run(
        ['zsh', '-c', 'source ~/.zshrc 2>/dev/null && env'],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if '=' in line:
            k, _, v = line.partition('=')
            if k in ('JIRA_EMAIL', 'JIRA_API_TOKEN') and not os.environ.get(k):
                os.environ[k] = v

_load_env()

EMAIL = os.environ.get('JIRA_EMAIL', '')
TOKEN = os.environ.get('JIRA_API_TOKEN', '')
BASE  = 'https://eagleeyenetworks.atlassian.net'

CI_BASE = (
    '((project = EENS AND reporter not in (604fb2f681b82500682d022a)) '
    'OR (project in (EEPD, Infrastructure) AND labels in (customer-impact))) '
    'AND issuetype not in (Improvement, story) '
    'AND statusCategory not in (Done) '
    'AND priority not in (Low, Lowest) '
    'AND (duedate is EMPTY OR duedate <= now())'
)

VMSSUP_JQL = (
    'project = VMSSUP '
    'AND statusCategory not in (Done) '
    'AND NOT (description ~ "task id" AND reporter in (604fb2f681b82500682d022a))'
)

# Board column → status names (from board config status IDs)
VMSSUP_COLUMNS = [
    ("Backlog",            ["Backlog"]),
    ("Assistance / To-Do", ["Assistance", "Support Assistance"]),
    ("Triage",             ["Triaging"]),
    ("Engineering",        ["Investigation", "Engineering Work", "Infrastructure Work", "In Progress"]),
    ("Support Review",     ["Support Review", "Resolved Review"]),
]

CI_HIST_BASE = (
    '((project = EENS AND reporter not in (604fb2f681b82500682d022a)) '
    'OR (project in (EEPD, Infrastructure) AND labels in (customer-impact))) '
    'AND issuetype not in (Improvement, story) '
    'AND priority not in (Low, Lowest)'
)

FIELDS_FULL  = ['summary','status','priority','assignee','duedate','labels',
                'customfield_10500','created','project','sprint','customfield_11063','description']

def _extract_adf_text(content):
    if isinstance(content, str): return content
    if isinstance(content, dict):
        if content.get('type') == 'text': return content.get('text', '')
        if content.get('type') == 'hardBreak': return '\n'
        if 'content' in content: return _extract_adf_text(content['content'])
    if isinstance(content, list): return ''.join(_extract_adf_text(i) for i in content)
    return ''
FIELDS_SHORT = ['summary','status','priority','assignee','duedate','project','created']


def jira_search(jql, fields, max_results=100):
    issues, next_token = [], None
    while True:
        body = {'jql': jql, 'maxResults': max_results, 'fields': fields}
        if next_token:
            body['nextPageToken'] = next_token
        r = subprocess.run(
            ['curl', '-s', '-u', f'{EMAIL}:{TOKEN}',
             '-X', 'POST', f'{BASE}/rest/api/3/search/jql',
             '-H', 'Content-Type: application/json',
             '-d', json.dumps(body)],
            capture_output=True, text=True
        )
        d = json.loads(r.stdout)
        batch = d.get('issues', d.get('values', []))
        issues.extend(batch)
        next_token = d.get('nextPageToken')
        if not next_token or not batch:
            break
    return issues


def fmt_issue(i, now):
    f = i['fields']
    created = datetime.fromisoformat(f['created'].replace('Z', '+00:00'))
    age = (now - created).days
    return {
        'key':      i['key'],
        'summary':  f.get('summary', ''),
        'status':   (f.get('status') or {}).get('name', ''),
        'priority': (f.get('priority') or {}).get('name', ''),
        'assignee': (f.get('assignee') or {}).get('displayName', 'Unassigned'),
        'duedate':       f.get('duedate') or '',
        'project':       (f.get('project') or {}).get('key', ''),
        'age_days':      age,
        'created_date':  created.strftime('%Y-%m-%d'),
        'url':           f'{BASE}/browse/{i["key"]}',
    }


@app.route('/api/data')
def api_data():
    now = datetime.now(timezone.utc)

    # All CI tickets (paginated)
    all_issues = jira_search(CI_BASE, FIELDS_FULL)

    # Aggregations
    prio_counts  = defaultdict(int)
    team_data    = defaultdict(lambda: {'total': 0, 'highest': 0, 'high': 0, 'medium': 0})
    assignee_load = defaultdict(lambda: {'ci': 0, 'ci_highest': 0, 'ci_high': 0})
    acct_data     = defaultdict(lambda: {'total': 0, 'high': 0, 'medium': 0})

    for issue in all_issues:
        f    = issue['fields']
        prio = (f.get('priority') or {}).get('name', 'Medium')
        team = (f.get('customfield_10500') or {}).get('name', 'Unassigned')
        prio_counts[prio] += 1
        team_data[team]['total'] += 1
        if prio == 'Highest':
            team_data[team]['highest'] += 1
        elif prio == 'High':
            team_data[team]['high'] += 1
        else:
            team_data[team]['medium'] += 1

        # Assignee load
        assignee = (f.get('assignee') or {}).get('displayName', 'Unassigned')
        assignee_load[assignee]['ci'] += 1
        if prio == 'Highest':   assignee_load[assignee]['ci_highest'] += 1
        elif prio == 'High':    assignee_load[assignee]['ci_high'] += 1

        # Account heat map
        acct_raw = f.get('customfield_11063')
        if isinstance(acct_raw, dict):
            acct_name = acct_raw.get('value') or acct_raw.get('name') or ''
        else:
            acct_name = str(acct_raw).strip() if acct_raw else ''
        # Fallback: parse from description when field is empty
        if not acct_name:
            desc_text = _extract_adf_text(f.get('description') or {})
            m = re.search(r'(?:Master\s+)?Account:\s*\d+\s*[-–]\s*(.+)', desc_text, re.IGNORECASE)
            if m:
                acct_name = m.group(1).strip().split('\n')[0].strip()
        if acct_name:
            acct_data[acct_name]['total'] += 1
            if prio in ('Highest', 'High'): acct_data[acct_name]['high'] += 1
            else: acct_data[acct_name]['medium'] += 1
        else:
            acct_data['__unattributed__']['total'] += 1
            if prio in ('Highest', 'High'): acct_data['__unattributed__']['high'] += 1
            else: acct_data['__unattributed__']['medium'] += 1

    # Age distribution buckets
    AGE_BUCKETS = [
        ("< 1 week",   0,   7),
        ("1–2 weeks",  7,   14),
        ("2–4 weeks",  14,  28),
        ("1–3 months", 28,  90),
        ("3–6 months", 90,  180),
        ("6+ months",  180, 99999),
    ]
    age_dist = {lbl: {'total': 0, 'high': 0, 'medium': 0} for lbl, _, _ in AGE_BUCKETS}

    # Focused filter queries (computed from already-fetched data)
    three_days   = (now + timedelta(days=3)).date()
    due_soon     = []
    punted       = []
    never_sprint = []
    out_of_spec  = []

    for issue in all_issues:
        f    = issue['fields']
        prio = (f.get('priority') or {}).get('name', 'Medium')
        fmted = fmt_issue(issue, now)
        age  = fmted['age_days']

        # Age distribution
        for lbl, lo, hi in AGE_BUCKETS:
            if lo <= age < hi:
                age_dist[lbl]['total'] += 1
                if prio in ('Highest', 'High'):
                    age_dist[lbl]['high'] += 1
                else:
                    age_dist[lbl]['medium'] += 1
                break

        # Out of spec
        if (prio == 'Highest' and age > 7) or (prio == 'High' and age > 14) or (age > 28):
            out_of_spec.append(fmted)

        dd = f.get('duedate')
        if dd and dd <= str(three_days):
            due_soon.append(fmted)
        if 'repeatedly-punted' in (f.get('labels') or []):
            punted.append(fmted)
        sprint_val = f.get('sprint')
        if not sprint_val:
            never_sprint.append(fmted)

    out_of_spec.sort(key=lambda x: (
        {'Highest': 0, 'High': 1}.get(x['priority'], 2), -x['age_days']
    ))

    never_sprint.sort(key=lambda x: x['age_days'], reverse=True)

    teams_sorted = sorted(team_data.items(), key=lambda x: -x[1]['total'])

    # Build per-team ticket lists for inline panel
    teams_tickets   = defaultdict(list)
    account_tickets = defaultdict(list)
    for issue in all_issues:
        f    = issue['fields']
        team = (f.get('customfield_10500') or {}).get('name', 'Unassigned')
        teams_tickets[team].append(fmt_issue(issue, now))

        acct_raw = f.get('customfield_11063')
        if isinstance(acct_raw, dict):
            acct_key = acct_raw.get('value') or acct_raw.get('name') or ''
        else:
            acct_key = str(acct_raw).strip() if acct_raw else ''
        if not acct_key:
            desc_text = _extract_adf_text(f.get('description') or {})
            m = re.search(r'(?:Master\s+)?Account:\s*\d+\s*[-–]\s*(.+)', desc_text, re.IGNORECASE)
            if m:
                acct_key = m.group(1).strip().split('\n')[0].strip()
        account_tickets[acct_key or '__none__'].append(fmt_issue(issue, now))

    return jsonify({
        'total':         len(all_issues),
        'prio_counts':   dict(prio_counts),
        'teams':         [{'name': k, **v} for k, v in teams_sorted],
        'teams_tickets':   {k: sorted(v, key=lambda x: -x['age_days']) for k, v in teams_tickets.items()},
        'account_tickets': {k: sorted(v, key=lambda x: -x['age_days']) for k, v in account_tickets.items()},
        'age_dist':      [{'label': lbl, **age_dist[lbl]} for lbl, _, _ in AGE_BUCKETS],
        'out_of_spec':   out_of_spec,
        'due_soon':      sorted(due_soon, key=lambda x: x['duedate']),
        'punted':        punted,
        'never_sprint':  never_sprint[:20],
        'assignee_load': sorted([{'name': k, **v} for k, v in assignee_load.items()],
                                  key=lambda x: -x['ci']),
        'account_heat':  sorted([{'account': k, **v} for k, v in acct_data.items() if k != '__unattributed__'],
                                  key=lambda x: -x['total'])[:15],
        'account_attributed': {
            'total':  sum(v['total']  for k, v in acct_data.items() if k != '__unattributed__'),
            'high':   sum(v['high']   for k, v in acct_data.items() if k != '__unattributed__'),
            'medium': sum(v['medium'] for k, v in acct_data.items() if k != '__unattributed__'),
        },
        'account_unattributed': dict(acct_data.get('__unattributed__', {'total': 0, 'high': 0, 'medium': 0})),
        'refreshed_at':  now.isoformat(),
    })


@app.route('/api/vmssup')
def api_vmssup():
    now = datetime.now(timezone.utc)
    fields = ['summary', 'status', 'priority', 'assignee', 'created', 'updated']
    issues = jira_search(VMSSUP_JQL, fields, max_results=200)

    status_to_col = {}
    for col_name, statuses in VMSSUP_COLUMNS:
        for s in statuses:
            status_to_col[s] = col_name

    DISPLAY_COLS = [col for col, _ in VMSSUP_COLUMNS if col != 'Backlog']
    PRIO_ORDER   = {'Highest': 0, 'High': 1, 'Medium': 2}

    prio_counts   = defaultdict(int)
    assignee_grid = defaultdict(lambda: {c: [] for c in DISPLAY_COLS})
    all_tickets   = []

    for i in issues:
        f    = i['fields']
        prio = (f.get('priority') or {}).get('name', 'Medium')
        created = datetime.fromisoformat(f['created'].replace('Z', '+00:00'))
        updated = datetime.fromisoformat(f['updated'].replace('Z', '+00:00'))
        t = {
            'key':        i['key'],
            'summary':    f.get('summary', ''),
            'status':     (f.get('status') or {}).get('name', ''),
            'priority':   prio,
            'assignee':   (f.get('assignee') or {}).get('displayName', 'Unassigned'),
            'age_days':   (now - created).days,
            'stale_days': (now - updated).days,
            'url':        f'{BASE}/browse/{i["key"]}',
        }
        prio_counts[prio] += 1
        all_tickets.append(t)
        col = status_to_col.get(t['status'])
        if col and col in DISPLAY_COLS:
            assignee_grid[t['assignee']][col].append(t)

    # Build sorted assignee rows
    assignees = []
    for name in sorted(assignee_grid):
        cols  = {}
        total = 0
        for col in DISPLAY_COLS:
            tickets = sorted(
                assignee_grid[name][col],
                key=lambda x: (PRIO_ORDER.get(x['priority'], 3), x['status'])
            )
            cols[col] = tickets
            total    += len(tickets)
        assignees.append({'name': name, 'total': total, 'columns': cols})

    # Stalled: High/Highest not updated in ≥3 days
    stalled = [t for t in all_tickets
               if t['stale_days'] >= 3 and t['priority'] in ('Highest', 'High')]
    stalled.sort(key=lambda x: (x['priority'] != 'Highest', -x['stale_days']))

    return jsonify({
        'total':        len(issues),
        'prio_counts':  dict(prio_counts),
        'assignees':    assignees,
        'display_cols': DISPLAY_COLS,
        'stalled':      stalled,
        'refreshed_at': now.isoformat(),
    })


@app.route('/api/reporting')
def api_reporting():
    now = datetime.now(timezone.utc)
    opened = jira_search(
        CI_HIST_BASE + ' AND created >= -28d',
        ['created'], max_results=200
    )
    closed_issues = jira_search(
        CI_HIST_BASE + ' AND statusCategory in (Done) AND resolved >= -28d',
        ['resolutiondate'], max_results=200
    )
    weeks = []
    for w in range(3, -1, -1):
        end_dt   = now - timedelta(days=w * 7)
        start_dt = now - timedelta(days=(w + 1) * 7)
        end_d    = end_dt.date()
        start_d  = start_dt.date()
        label    = f'{start_d.strftime("%-m/%-d")}–{end_d.strftime("%-m/%-d")}'
        o = sum(1 for i in opened
                if start_d <= datetime.fromisoformat(
                    i['fields']['created'].replace('Z', '+00:00')).date() < end_d)
        c = sum(1 for i in closed_issues
                if i['fields'].get('resolutiondate') and
                start_d <= datetime.fromisoformat(
                    i['fields']['resolutiondate'].replace('Z', '+00:00')).date() < end_d)
        weeks.append({'label': label, 'opened': o, 'closed': c})
    return jsonify({'throughput_weeks': weeks, 'refreshed_at': now.isoformat()})


@app.route('/')
def index():
    return render_template_string(HTML)


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>EEN Ops Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:       #0d1117;
  --surface:  #161b22;
  --surface2: #1c2128;
  --border:   #30363d;
  --text:     #c9d1d9;
  --muted:    #8b949e;
  --blue:     #58a6ff;
  --green:    #3fb950;
  --red:      #f85149;
  --orange:   #f0883e;
  --yellow:   #d29922;
  --purple:   #bc8cff;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border);
}
header h1 { font-size: 16px; font-weight: 600; }
.header-right { display: flex; align-items: center; gap: 12px; }
#refresh-time { font-size: 12px; color: var(--muted); }
#refresh-btn {
  padding: 5px 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-size: 12px;
  cursor: pointer;
}
#refresh-btn:hover { border-color: var(--blue); }
#refresh-btn.spinning { color: var(--muted); cursor: not-allowed; }
.jira-search {
  display: flex;
  align-items: center;
  gap: 0;
}
#jira-search-input {
  padding: 5px 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-right: none;
  border-radius: 6px 0 0 6px;
  color: var(--text);
  font-size: 12px;
  width: 140px;
  outline: none;
}
#jira-search-input::placeholder { color: var(--muted); }
#jira-search-input:focus { border-color: var(--blue); }
#jira-search-btn {
  padding: 5px 10px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0 6px 6px 0;
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
}
#jira-search-btn:hover { border-color: var(--blue); color: var(--blue); }

.wrapper { padding: 20px 24px; display: flex; flex-direction: column; gap: 20px; }

/* Stat tiles */
.stats-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}
.stat-tile {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  cursor: pointer;
  text-decoration: none;
  transition: border-color .15s;
}
.stat-tile:hover { border-color: var(--blue); }
.stat-tile .val {
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
}
.stat-tile .lbl {
  font-size: 11px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .06em;
}
.val.total   { color: var(--blue); }
.val.highest { color: var(--red); }
.val.high    { color: var(--orange); }
.val.medium  { color: #4a9eff; }
.val.due     { color: var(--yellow); }

/* Two-column row */
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

/* Cards */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  resize: vertical;
  min-height: 120px;
}
.card-header {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--muted);
  flex-shrink: 0;
  user-select: none;
}
.card-body { padding: 14px; flex: 1; overflow-y: auto; min-height: 0; }

/* Chart */
.chart-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  height: 100%;
  min-height: 0;
}
#priority-chart { max-width: 220px; max-height: 220px; flex-shrink: 0; }
#team-chart { max-width: 220px; max-height: 220px; flex-shrink: 0; }
.legend { width: 100%; display: flex; flex-direction: column; gap: 4px; overflow-y: auto; min-height: 0; }
.legend-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  text-decoration: none;
  color: var(--text);
  padding: 3px 4px;
  border-radius: 4px;
  cursor: pointer;
}
.legend-row:hover { background: var(--surface2); }
.legend-row .dot-label { display: flex; align-items: center; gap: 8px; }
.legend-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.legend-count { font-weight: 600; color: var(--text); }

/* Team table */
.team-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.team-table th {
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--muted);
  padding: 0 8px 8px 8px;
  border-bottom: 1px solid var(--border);
}
.team-table th.num, .team-table td.num { text-align: right; }
.team-table td {
  padding: 7px 8px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.team-table tr:last-child td { border-bottom: none; }
.team-table tr:hover td { background: var(--surface2); }
.team-table tbody tr { cursor: pointer; }
.team-name { color: var(--text); font-weight: 500; }
.unassigned { color: var(--muted); font-style: italic; }
.bar-wrap { display: flex; align-items: center; gap: 8px; }
.bar-bg { flex: 1; height: 6px; background: var(--border); border-radius: 3px; min-width: 60px; }
.bar-fill { height: 100%; border-radius: 3px; background: var(--blue); transition: width .3s; }
.num-total { font-weight: 700; color: var(--text); min-width: 28px; text-align: right; }
.num-high { color: var(--orange); min-width: 24px; text-align: right; }
.num-med  { color: #4a9eff; min-width: 24px; text-align: right; }

/* Three-column row */
.three-col { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }

/* Ticket list */
.ticket-list { display: flex; flex-direction: column; gap: 1px; }
.ticket-item {
  display: grid;
  grid-template-columns: auto auto 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 7px 0;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}
.ticket-item:last-child { border-bottom: none; }
.ticket-key {
  color: var(--blue);
  font-weight: 600;
  font-size: 12px;
  white-space: nowrap;
  text-decoration: none;
}
.ticket-key:hover { text-decoration: underline; }
.prio-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 5px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: .04em;
  white-space: nowrap;
}
.prio-Highest { background: rgba(248,81,73,.2); color: var(--red); }
.prio-High    { background: rgba(240,136,62,.2); color: var(--orange); }
.prio-Medium  { background: rgba(88,166,255,.15); color: var(--blue); }
.ticket-summary { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ticket-meta { color: var(--muted); font-size: 11px; white-space: nowrap; }
.empty { color: var(--muted); font-size: 13px; font-style: italic; padding: 8px 0; }

/* Age distribution */
.age-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.age-table td { padding: 5px 8px; vertical-align: middle; }
.age-table tr:hover td { background: var(--surface2); }
.age-label { color: var(--muted); white-space: nowrap; width: 90px; }
.age-bar-cell { width: 100%; }
.age-bar-bg { background: var(--border); border-radius: 3px; height: 8px; position: relative; }
.age-bar-high { background: var(--orange); border-radius: 3px 0 0 3px; height: 100%; float: left; }
.age-bar-med  { background: var(--blue);   border-radius: 0; height: 100%; float: left; }
.age-count { color: var(--text); font-weight: 600; text-align: right; white-space: nowrap; width: 36px; }
.age-breakdown { color: var(--muted); font-size: 11px; white-space: nowrap; width: 140px; }

/* Out of spec */
.oos-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.oos-table th {
  text-align: left; padding: 0 8px 7px; font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: .05em; color: var(--muted);
  border-bottom: 1px solid var(--border);
}
.oos-table td { padding: 7px 8px; border-bottom: 1px solid var(--border); vertical-align: middle; }
.oos-table tr:last-child td { border-bottom: none; }
.oos-table tr:hover td { background: var(--surface2); }
.age-pill {
  font-size: 11px; font-weight: 700; padding: 2px 6px; border-radius: 4px;
  background: rgba(248,81,73,.15); color: var(--red); white-space: nowrap;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--muted);
  font-size: 14px;
  gap: 10px;
}
.spinner {
  width: 16px; height: 16px;
  border: 2px solid var(--border);
  border-top-color: var(--blue);
  border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Modal */
.modal-overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.6);
  z-index: 100;
  align-items: flex-start;
  justify-content: center;
  padding: 60px 24px;
}
.modal-overlay.open { display: flex; }
.modal {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  width: 100%;
  max-width: 860px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.modal-title { font-size: 14px; font-weight: 600; }
.modal-close {
  background: none;
  border: none;
  color: var(--muted);
  font-size: 18px;
  cursor: pointer;
  line-height: 1;
  padding: 2px 6px;
}
.modal-close:hover { color: var(--text); }
.modal-body { overflow-y: auto; padding: 4px 0; }
.modal-ticket {
  display: grid;
  grid-template-columns: 100px 70px 1fr 130px 60px;
  gap: 10px;
  align-items: center;
  padding: 8px 18px;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}
.modal-ticket:last-child { border-bottom: none; }
.modal-ticket:hover { background: var(--surface2); }
.modal-col-hdr {
  display: grid;
  grid-template-columns: 100px 70px 1fr 130px 60px;
  gap: 10px;
  padding: 8px 18px 6px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
}

/* MD Viewer */
.drop-zone {
  border: 2px dashed var(--border);
  border-radius: 10px;
  padding: 48px 24px;
  text-align: center;
  color: var(--muted);
  font-size: 14px;
  cursor: pointer;
  transition: border-color .2s, background .2s;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.drop-zone:hover, .drop-zone.drag-over {
  border-color: var(--blue);
  background: rgba(88,166,255,.05);
  color: var(--text);
}
.drop-zone-icon { font-size: 32px; }
.drop-zone-hint { font-size: 12px; color: var(--muted); }
.md-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px 8px 0 0;
  border-bottom: none;
}
.md-filename { font-size: 13px; font-weight: 500; color: var(--text); }
.md-clear-btn {
  padding: 4px 10px;
  background: none;
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
}
.md-clear-btn:hover { border-color: var(--red); color: var(--red); }
.md-body {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0 0 8px 8px;
  padding: 28px 36px;
  line-height: 1.7;
  font-size: 14px;
  overflow-x: auto;
}
.md-body h1 { font-size: 22px; font-weight: 700; color: var(--text); margin: 0 0 16px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.md-body h2 { font-size: 17px; font-weight: 600; color: var(--text); margin: 24px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.md-body h3 { font-size: 14px; font-weight: 600; color: var(--blue); margin: 18px 0 8px; }
.md-body h4 { font-size: 13px; font-weight: 600; color: var(--muted); margin: 14px 0 6px; text-transform: uppercase; letter-spacing: .05em; }
.md-body p  { color: var(--text); margin: 0 0 10px; }
.md-body ul, .md-body ol { color: var(--text); padding-left: 22px; margin: 0 0 10px; }
.md-body li { margin-bottom: 4px; }
.md-body a  { color: var(--blue); text-decoration: none; }
.md-body a:hover { text-decoration: underline; }
.md-body strong { color: var(--text); font-weight: 600; }
.md-body em { color: var(--muted); }
.md-body code {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 5px;
  color: var(--orange);
}
.md-body pre {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 14px 16px;
  overflow-x: auto;
  margin: 0 0 12px;
}
.md-body pre code { background: none; border: none; padding: 0; color: var(--text); font-size: 12px; }
.md-body blockquote {
  border-left: 3px solid var(--border);
  margin: 0 0 12px;
  padding: 4px 16px;
  color: var(--muted);
}
.md-body table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 0 0 12px; }
.md-body table th { text-align: left; padding: 7px 10px; background: var(--surface2); color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .05em; border-bottom: 1px solid var(--border); }
.md-body table td { padding: 7px 10px; border-bottom: 1px solid var(--border); color: var(--text); }
.md-body table tr:last-child td { border-bottom: none; }
.md-body hr { border: none; border-top: 1px solid var(--border); margin: 20px 0; }

/* Briefing banner */
.briefing-banner {
  display: flex;
  align-items: center;
  gap: 0;
  flex-wrap: wrap;
  background: rgba(88,166,255,.07);
  border: 1px solid rgba(88,166,255,.25);
  border-radius: 8px;
  padding: 9px 16px;
  font-size: 13px;
}
.briefing-banner-title { color: var(--blue); font-weight: 600; margin-right: 16px; }
.briefing-sep { color: var(--border); margin: 0 14px; }
.briefing-item { color: var(--text); }

/* Tabs */
.tab-bar {
  display: flex;
  gap: 2px;
  padding: 0 24px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
}
.tab {
  padding: 10px 18px;
  font-size: 13px;
  font-weight: 500;
  color: var(--muted);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color .15s, border-color .15s;
  margin-bottom: -1px;
}
.tab:hover { color: var(--text); }
.tab.active { color: var(--blue); border-bottom-color: var(--blue); }

/* Assignee board */
.assignee-board {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.assignee-group { border-bottom: 1px solid var(--border); }
.assignee-group:last-child { border-bottom: none; }
.assignee-group.collapsed .assignee-body { display: none; }
.assignee-group.collapsed .assignee-chevron { transform: rotate(-90deg); }
.assignee-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: var(--surface);
  cursor: pointer;
  user-select: none;
}
.assignee-header:hover { background: var(--surface2); }
.assignee-chevron {
  font-size: 11px;
  color: var(--muted);
  transition: transform .15s;
  display: inline-block;
}
.assignee-name  { font-size: 14px; font-weight: 600; }
.assignee-count { font-size: 12px; color: var(--muted); }
.board-cols-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border-top: 1px solid var(--border);
}
.board-col { border-right: 1px solid var(--border); min-height: 56px; }
.board-col:last-child { border-right: none; }
.board-col-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}
.board-col-count {
  font-size: 10px;
  font-weight: 700;
  color: var(--text);
  background: var(--border);
  padding: 1px 5px;
  border-radius: 8px;
}
.board-col-tickets {
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: rgba(0,0,0,.12);
  min-height: 12px;
}
.board-ticket {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 9px 10px 8px 10px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-left-width: 3px;
  border-radius: 4px;
  text-decoration: none;
  color: inherit;
  transition: filter .15s;
}
.board-ticket:hover { filter: brightness(1.1); }
.board-ticket-summary { font-size: 13px; color: var(--text); line-height: 1.4; }
.board-ticket-footer {
  display: flex;
  align-items: center;
  gap: 6px;
}
/* Reporting section */
.section-divider {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: var(--muted);
  padding: 8px 0 0;
  border-top: 1px solid var(--border);
}
</style>
</head>
<body>

<header>
  <h1>EEN Ops Dashboard</h1>
  <div class="header-right">
    <div class="jira-search">
      <input id="jira-search-input" type="text" placeholder="EENS-12345…"
             onkeydown="if(event.key==='Enter') jiraSearch()">
      <button id="jira-search-btn" onclick="jiraSearch()">→</button>
    </div>
    <span id="refresh-time">Loading…</span>
    <button id="refresh-btn" onclick="load()">Refresh</button>
  </div>
</header>

<nav class="tab-bar">
  <button class="tab active" data-tab="ci" onclick="switchTab('ci')">Customer Impact</button>
  <button class="tab" data-tab="vmssup" onclick="switchTab('vmssup')">VMSSUP Board</button>
  <button class="tab" data-tab="md" onclick="switchTab('md')">Morning Briefing</button>
</nav>

<div id="panel-ci">
  <div id="briefing-banner-wrap" style="padding:12px 24px 0;display:none">
    <div id="briefing-banner" class="briefing-banner"></div>
  </div>
  <div class="wrapper" id="app">
    <div class="loading"><div class="spinner"></div> Loading JIRA data…</div>
  </div>
</div>
<div id="panel-vmssup" style="display:none">
  <div class="wrapper" id="vmssup-app">
    <div class="loading"><div class="spinner"></div> Loading VMSSUP board…</div>
  </div>
</div>
<div id="panel-md" style="display:none">
  <div class="wrapper" id="md-app">
    <div class="drop-zone" id="drop-zone" onclick="document.getElementById('md-file-input').click()"
         ondragover="event.preventDefault();this.classList.add('drag-over')"
         ondragleave="this.classList.remove('drag-over')"
         ondrop="handleDrop(event)">
      <div class="drop-zone-icon">📄</div>
      <div>Drop a <strong>.md</strong> file here, or click to browse</div>
      <div class="drop-zone-hint">Morning briefing reports are saved to ~/Documents/Morning Briefing/</div>
    </div>
    <input type="file" id="md-file-input" accept=".md,text/markdown,text/plain" style="display:none" onchange="handleFileInput(event)">
    <div id="md-content" style="display:none">
      <div class="md-toolbar">
        <span class="md-filename" id="md-filename"></span>
        <button class="md-clear-btn" onclick="clearMd()">✕ Clear</button>
      </div>
      <div class="md-body" id="md-body"></div>
    </div>
  </div>
</div>

<div class="modal-overlay" id="modal-overlay" onclick="closeModal(event)">
  <div class="modal">
    <div class="modal-header">
      <span class="modal-title" id="modal-title"></span>
      <button class="modal-close" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-body" id="modal-body"></div>
  </div>
</div>

<script>
const JIRA_NAV = 'https://eagleeyenetworks.atlassian.net/issues/?jql=';
const CI_BASE  = '((project = EENS AND reporter not in (604fb2f681b82500682d022a)) OR (project in (EEPD, Infrastructure) AND labels in (customer-impact))) AND issuetype not in (Improvement, story) AND statusCategory not in (Done) AND priority not in (Low, Lowest) AND (duedate is EMPTY OR duedate <= now())';

let prioChart      = null;
let teamChart      = null;
let teamData       = [];   // stored so chart onClick can reference by index
let teamsTickets   = {};   // team name → ticket list
let otherTeamNames = [];   // team names rolled into "Other"
let ciData         = null;
let vmssupData     = null;
let accountTickets = {};
let reportingData  = null;
let throughputChart = null;
let currentTab     = 'ci';

function jiraSearch() {
  const val = document.getElementById('jira-search-input').value.trim().toUpperCase();
  if (!val) return;
  window.open(`https://eagleeyenetworks.atlassian.net/browse/${val}`, '_blank');
  document.getElementById('jira-search-input').value = '';
}

function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.getElementById('panel-ci').style.display     = tab === 'ci'     ? '' : 'none';
  document.getElementById('panel-vmssup').style.display = tab === 'vmssup' ? '' : 'none';
  document.getElementById('panel-md').style.display     = tab === 'md'     ? '' : 'none';
  if (tab === 'md') {
    document.getElementById('refresh-time').textContent = mdFilename ? mdFilename : 'No file loaded';
  } else {
    const d = tab === 'ci' ? ciData : vmssupData;
    if (d) document.getElementById('refresh-time').textContent = 'Refreshed ' + formatRefreshTime(d.refreshed_at);
  }
}

let mdFilename   = '';
let briefingData = null;

function parseBriefingData(text) {
  const d = {};
  const dateM = text.match(/## Morning Briefing[^\n]*?(\d{4}-\d{2}-\d{2})/);
  if (dateM) d.date = dateM[1];
  const totalM = text.match(/Total Open Customer Impact Tickets:\s*(\d+)(?:\s*([▲▼]\d+))?/);
  if (totalM) { d.ciTotal = parseInt(totalM[1]); d.ciDelta = totalM[2] || null; }
  const oosM = text.match(/Out of Spec Work Items\s*\((\d+)\)/);
  if (oosM) d.outOfSpec = parseInt(oosM[1]);
  const nrHighM = text.match(/\*\*High\*\*[^\n]*?(\d+)\s*ticket/);
  if (nrHighM) d.needsHigh = parseInt(nrHighM[1]);
  const nrMedM = text.match(/\*\*Medium\*\*[^\n]*?(\d+)\s*ticket/);
  if (nrMedM) d.needsMed = parseInt(nrMedM[1]);
  // Extract full Needs Team Response section
  const ntrM = text.match(/##\s*Needs Team Response\n([\s\S]*?)(?=\n##\s|$)/);
  if (ntrM) d.needsResponseMd = ntrM[1].trim();
  return Object.keys(d).length > 1 ? d : null;
}

function showBriefingBanner(data) {
  if (!data) return;
  const parts = [];
  if (data.ciTotal !== undefined) {
    const dColor = data.ciDelta ? (data.ciDelta.startsWith('▲') ? 'var(--orange)' : 'var(--green)') : '';
    const dHtml  = data.ciDelta ? ` <strong style="color:${dColor}">${data.ciDelta}</strong>` : '';
    parts.push(`<span class="briefing-item">CI total this morning: <strong>${data.ciTotal}</strong>${dHtml}</span>`);
  }
  if (data.needsHigh !== undefined || data.needsMed !== undefined) {
    const h = data.needsHigh || 0, m = data.needsMed || 0;
    parts.push(`<span class="briefing-item">Needs response: <strong style="color:var(--orange)">${h} High</strong> · <strong style="color:var(--blue)">${m} Med</strong></span>`);
  }
  if (data.outOfSpec !== undefined) {
    parts.push(`<span class="briefing-item">Out of spec: <strong style="color:var(--red)">${data.outOfSpec}</strong></span>`);
  }
  const dateStr = data.date ? ` — ${data.date}` : '';
  document.getElementById('briefing-banner').innerHTML =
    `<span class="briefing-banner-title">📋 Morning Briefing${dateStr}</span>` +
    parts.map(p => `<span class="briefing-sep">|</span>${p}`).join('');
  document.getElementById('briefing-banner-wrap').style.display = '';
}

function updateNeedsResponseCard() {
  const existing = document.getElementById('card-needs-response');
  if (existing) existing.remove();
  if (!briefingData || !briefingData.needsResponseMd) return;
  const app = document.getElementById('app');
  if (!app) return;
  const card = document.createElement('div');
  card.className = 'card';
  card.id = 'card-needs-response';
  card.innerHTML = `
    <div class="card-header">Needs Team Response <span style="color:var(--muted);font-weight:400;font-size:10px;margin-left:6px;text-transform:none;letter-spacing:0">from this morning's briefing</span></div>
    <div class="card-body md-body" style="padding:12px 18px">${marked.parse(briefingData.needsResponseMd)}</div>
  `;
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  if (saved['card-needs-response']) card.style.height = saved['card-needs-response'] + 'px';
  const reportingSection = document.getElementById('reporting-section');
  if (reportingSection) app.insertBefore(card, reportingSection);
  else app.appendChild(card);
  // Watch the new card for resize
  const ro = new ResizeObserver(() => { let t; clearTimeout(t); t = setTimeout(saveSizes, 400); });
  ro.observe(card);
}

function loadMdContent(text, filename) {
  mdFilename = filename;
  document.getElementById('md-filename').textContent = filename;
  document.getElementById('md-body').innerHTML = marked.parse(text);
  document.getElementById('drop-zone').style.display  = 'none';
  document.getElementById('md-content').style.display = '';
  if (currentTab === 'md') document.getElementById('refresh-time').textContent = filename;
  briefingData = parseBriefingData(text);
  showBriefingBanner(briefingData);
  updateNeedsResponseCard();
}

function clearMd() {
  mdFilename = '';
  briefingData = null;
  document.getElementById('drop-zone').style.display  = '';
  document.getElementById('md-content').style.display = 'none';
  document.getElementById('md-body').innerHTML = '';
  document.getElementById('md-file-input').value = '';
  document.getElementById('briefing-banner-wrap').style.display = 'none';
  if (currentTab === 'md') document.getElementById('refresh-time').textContent = 'No file loaded';
  updateNeedsResponseCard();
}

function handleFileInput(evt) {
  const file = evt.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => loadMdContent(e.target.result, file.name);
  reader.readAsText(file);
}

function handleDrop(evt) {
  evt.preventDefault();
  document.getElementById('drop-zone').classList.remove('drag-over');
  const file = evt.dataTransfer.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => loadMdContent(e.target.result, file.name);
  reader.readAsText(file);
}

function jiraLink(extraJql) {
  const jql = (extraJql ? CI_BASE + ' AND ' + extraJql : CI_BASE) + ' ORDER BY priority DESC, updated ASC';
  return JIRA_NAV + encodeURIComponent(jql);
}

const PRIO_COLORS = {
  'Highest': '#f85149',
  'High':    '#f0883e',
  'Medium':  '#4a9eff',
};

const TEAM_PALETTE = [
  '#58a6ff','#3fb950','#f0883e','#bc8cff','#f85149',
  '#d29922','#39d353','#ff7b72','#79c0ff','#8b949e',
];

function openTeamModal(teamName) {
  let tickets;
  if (teamName === 'Other') {
    tickets = otherTeamNames.flatMap(n => teamsTickets[n] || []);
    tickets.sort((a, b) => b.age_days - a.age_days);
  } else {
    tickets = teamsTickets[teamName] || [];
  }
  document.getElementById('modal-title').textContent = `${teamName} — ${tickets.length} ticket${tickets.length !== 1 ? 's' : ''}`;
  document.getElementById('modal-body').innerHTML = `
    <div class="modal-col-hdr"><span>Key</span><span>Priority</span><span>Summary</span><span>Assignee</span><span>Age</span></div>
    ${tickets.map(t => `
      <div class="modal-ticket">
        <a class="ticket-key" href="${t.url}" target="_blank">${t.key}</a>
        ${prioBadge(t.priority)}
        <span class="ticket-summary" title="${t.summary}">${t.summary}</span>
        <span style="color:var(--muted);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.assignee}</span>
        <span style="color:var(--muted);font-size:11px">${t.age_days}d</span>
      </div>`).join('')}
  `;
  document.getElementById('modal-overlay').classList.add('open');
}

function openAccountModal(rawName) {
  const tickets     = accountTickets[rawName] || [];
  const displayName = rawName === '__none__' ? 'No Account' : rawName.replace(/^\d{6,8}(?:\s*[-–]\s*|\s+)/, '');
  document.getElementById('modal-title').textContent = `${displayName} — ${tickets.length} ticket${tickets.length !== 1 ? 's' : ''}`;
  document.getElementById('modal-body').innerHTML = `
    <div class="modal-col-hdr"><span>Key</span><span>Priority</span><span>Summary</span><span>Assignee</span><span>Age</span></div>
    ${tickets.map(t => `
      <div class="modal-ticket">
        <a class="ticket-key" href="${t.url}" target="_blank">${t.key}</a>
        ${prioBadge(t.priority)}
        <span class="ticket-summary" title="${t.summary}">${t.summary}</span>
        <span style="color:var(--muted);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${t.assignee}</span>
        <span style="color:var(--muted);font-size:11px">${t.age_days}d</span>
      </div>`).join('')}
  `;
  document.getElementById('modal-overlay').classList.add('open');
}

function closeModal(evt) {
  if (evt && evt.target !== document.getElementById('modal-overlay')) return;
  document.getElementById('modal-overlay').classList.remove('open');
}

function formatRefreshTime(iso) {
  const d = new Date(iso);
  const local = d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', timeZoneName: 'short'});
  const utcH  = String(d.getUTCHours()).padStart(2,'0');
  const utcM  = String(d.getUTCMinutes()).padStart(2,'0');
  return `${local} (${utcH}:${utcM} UTC)`;
}

function prioBadge(p) {
  return `<span class="prio-badge prio-${p}">${p}</span>`;
}

function ticketRows(tickets, {showDue=false, showCreated=false}={}) {
  if (!tickets.length) return `<div class="empty">None.</div>`;
  return `<div class="ticket-list">${tickets.map(t => `
    <div class="ticket-item">
      <a class="ticket-key" href="${t.url}" target="_blank">${t.key}</a>
      ${prioBadge(t.priority)}
      <span class="ticket-summary" title="${t.summary}">${t.summary}</span>
      <span class="ticket-meta">${
        showDue && t.duedate ? 'due ' + t.duedate :
        showCreated ? t.created_date :
        t.assignee !== 'Unassigned' ? t.assignee.split(' ')[0] : '—'
      }</span>
    </div>`).join('')}</div>`;
}

function makeDoughnut(canvasId, labels, vals, colors, onClickFn) {
  const ctx = document.getElementById(canvasId).getContext('2d');
  return new Chart(ctx, {
    type: 'doughnut',
    data: { labels, datasets: [{ data: vals, backgroundColor: colors, borderWidth: 2, borderColor: '#161b22' }] },
    options: {
      cutout: '60%',
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => ` ${c.label}: ${c.parsed}` } },
      },
      onClick: (evt, elements) => { if (elements.length) onClickFn(elements[0].index); },
      onHover:  (evt, elements) => { evt.native.target.style.cursor = elements.length ? 'pointer' : 'default'; },
    }
  });
}

function legendHtml(labels, colors, counts, linkFn) {
  return labels.map((lbl, i) => `
    <a class="legend-row" href="${linkFn(lbl)}" target="_blank">
      <div class="dot-label">
        <div class="legend-dot" style="background:${colors[i]}"></div>
        <span>${lbl}</span>
      </div>
      <span class="legend-count">${counts[i]}</span>
    </a>`).join('');
}

function ageDistHtml(buckets) {
  const max = Math.max(...buckets.map(b => b.total), 1);
  return `<table class="age-table">${buckets.map(b => {
    const highPct = Math.round(b.high / max * 100);
    const medPct  = Math.round(b.medium / max * 100);
    const parts = [];
    if (b.high)   parts.push(`H:${b.high}`);
    if (b.medium) parts.push(`M:${b.medium}`);
    return `<tr>
      <td class="age-label">${b.label}</td>
      <td class="age-bar-cell">
        <div class="age-bar-bg" style="overflow:hidden">
          <div class="age-bar-high" style="width:${highPct}%"></div>
          <div class="age-bar-med"  style="width:${medPct}%"></div>
        </div>
      </td>
      <td class="age-count">${b.total}</td>
      <td class="age-breakdown">${parts.join(', ') || '—'}</td>
    </tr>`;
  }).join('')}</table>`;
}

function outOfSpecHtml(tickets) {
  if (!tickets.length) return `<div class="empty">None — all within SLA.</div>`;
  return `<table class="oos-table">
    <thead><tr><th>Key</th><th>Priority</th><th>Age</th><th>Assignee</th><th>Summary</th></tr></thead>
    <tbody>${tickets.map(t => `
      <tr>
        <td><a class="ticket-key" href="${t.url}" target="_blank">${t.key}</a></td>
        <td>${prioBadge(t.priority)}</td>
        <td><span class="age-pill">${t.age_days}d</span></td>
        <td style="color:var(--muted);font-size:11px;white-space:nowrap">${t.assignee.split(' ')[0]}</td>
        <td class="ticket-summary" title="${t.summary}">${t.summary}</td>
      </tr>`).join('')}
    </tbody>
  </table>`;
}

function accountHeatHtml(accounts, unattributed, attributed) {
  if (!accounts || !accounts.length) return `<div class="empty">No account data — most CI tickets may lack account info.</div>`;
  const ua         = unattributed || {total: 0, high: 0, medium: 0};
  const attr        = attributed  || {total: 0, high: 0, medium: 0};
  const max         = Math.max(...accounts.map(a => a.total), 1);
  const grandTotal  = attr.total  + (ua.total  || 0);
  const grandHigh   = attr.high   + (ua.high   || 0);
  const grandMed    = attr.medium + (ua.medium || 0);
  const attrPct     = grandTotal ? Math.round(attr.total / grandTotal * 100) : 100;
  return `<table class="team-table">
    <thead><tr>
      <th>Account</th>
      <th class="num" style="color:var(--orange)">H+</th>
      <th class="num" style="color:#4a9eff">Med</th>
      <th class="num">Total</th>
    </tr></thead>
    <thead style="position:sticky;top:0;background:var(--surface);z-index:1">
      <tr style="border-bottom:2px solid var(--border)">
        <td style="padding:7px 8px;font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em">
          All CI Tickets
          <span style="font-weight:400;color:${attrPct>=90?'var(--green)':'var(--yellow)'};margin-left:6px">${attrPct}% attributed</span>
        </td>
        <td class="num num-high" style="font-weight:700">${grandHigh}</td>
        <td class="num num-med"  style="font-weight:700">${grandMed}</td>
        <td class="num num-total">${grandTotal}</td>
      </tr>
    </thead>
    <tbody>${accounts.map(a => {
      const pct         = Math.round(a.total / max * 100);
      const displayName = a.account.replace(/^\d{6,8}(?:\s*[-–]\s*|\s+)/, '');
      const safeKey     = a.account.replace(/\\/g,'\\\\').replace(/'/g,"\\'");
      return `<tr style="cursor:pointer" onclick="openAccountModal('${safeKey}')" title="Click to view tickets">
        <td>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="team-name" style="min-width:100px;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${a.account}">${displayName}</span>
            <div class="bar-bg" style="flex:1;min-width:40px"><div class="bar-fill" style="width:${pct}%"></div></div>
          </div>
        </td>
        <td class="num num-high">${a.high || 0}</td>
        <td class="num num-med">${a.medium || 0}</td>
        <td class="num num-total">${a.total}</td>
      </tr>`;
    }).join('')}
    ${ua.total ? `
    <tr style="opacity:.55;cursor:pointer" onclick="openAccountModal('__none__')" title="Click to view tickets with no account">
      <td>
        <div style="display:flex;align-items:center;gap:8px">
          <span class="team-name" style="min-width:100px;max-width:180px;font-style:italic;color:var(--muted)">No Account</span>
          <div class="bar-bg" style="flex:1;min-width:40px"><div class="bar-fill" style="width:${Math.round(ua.total/max*100)}%;background:var(--border)"></div></div>
        </div>
      </td>
      <td class="num" style="color:var(--muted)">${ua.high || 0}</td>
      <td class="num" style="color:var(--muted)">${ua.medium || 0}</td>
      <td class="num" style="color:var(--muted)">${ua.total}</td>
    </tr>` : ''}
    </tbody>
  </table>`;
}

function engineerLoadHtml(loadList, maxLoad) {
  if (!loadList.length) return `<div class="empty">No data.</div>`;
  return `<table class="team-table">
    <thead><tr>
      <th>Engineer</th>
      <th class="num" style="color:#4a9eff">CI</th>
      <th class="num" style="color:var(--orange)">VMSSUP</th>
      <th class="num">Total</th>
    </tr></thead>
    <tbody>${loadList.map(e => {
      const pct = Math.round(e.total / maxLoad * 100);
      return `<tr>
        <td>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="team-name" style="min-width:80px;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${e.name.split(' ').slice(0,2).join(' ')}</span>
            <div class="bar-bg" style="flex:1;min-width:40px"><div class="bar-fill" style="width:${pct}%;background:var(--purple)"></div></div>
          </div>
        </td>
        <td class="num" style="color:#4a9eff">${e.ci}</td>
        <td class="num" style="color:var(--orange)">${e.vmssup}</td>
        <td class="num num-total">${e.total}</td>
      </tr>`;
    }).join('')}
    </tbody>
  </table>`;
}

function pipelineHealthHtml(stageStats, cols) {
  const avgs = cols.map(c => stageStats[c] && stageStats[c].count ? Math.round(stageStats[c].total / stageStats[c].count) : 0);
  const maxAvg = Math.max(...avgs, 1);
  return `<table class="team-table">
    <thead><tr>
      <th>Stage</th>
      <th class="num">Tickets</th>
      <th class="num">Avg Age</th>
    </tr></thead>
    <tbody>${cols.map((col, idx) => {
      const s = stageStats[col] || {total: 0, count: 0};
      const avg = avgs[idx];
      const pct = Math.round(avg / maxAvg * 100);
      const color = avg > 14 ? 'var(--red)' : avg > 7 ? 'var(--orange)' : 'var(--green)';
      const pillBg = avg > 14 ? 'rgba(248,81,73,.15)' : avg > 7 ? 'rgba(240,136,62,.15)' : 'rgba(63,185,80,.15)';
      return `<tr>
        <td>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="team-name" style="min-width:110px">${col}</span>
            <div class="bar-bg" style="flex:1;min-width:40px"><div class="bar-fill" style="width:${pct}%;background:${color}"></div></div>
          </div>
        </td>
        <td class="num" style="color:var(--muted)">${s.count}</td>
        <td class="num"><span class="age-pill" style="background:${pillBg};color:${color}">${avg}d</span></td>
      </tr>`;
    }).join('')}
    </tbody>
  </table>`;
}

function renderReporting(ci, vmssup, rep) {
  if (!rep || !ci || !vmssup) return;
  const app = document.getElementById('app');
  if (!app) return;

  // Engineer load: merge CI assignees with VMSSUP assignees
  const vmssupByName = {};
  for (const a of vmssup.assignees) vmssupByName[a.name] = a.total;
  const loadMap = {};
  for (const a of (ci.assignee_load || [])) {
    loadMap[a.name] = {ci: a.ci, vmssup: vmssupByName[a.name] || 0};
  }
  for (const [name, cnt] of Object.entries(vmssupByName)) {
    if (!loadMap[name]) loadMap[name] = {ci: 0, vmssup: cnt};
  }
  const loadList = Object.entries(loadMap)
    .filter(([n]) => n !== 'Unassigned')
    .map(([name, d]) => ({name, ci: d.ci, vmssup: d.vmssup, total: d.ci + d.vmssup}))
    .sort((a, b) => b.total - a.total)
    .slice(0, 15);
  const maxLoad = Math.max(...loadList.map(e => e.total), 1);

  // Pipeline stage stats from vmssupData
  const stageStats = {};
  for (const col of vmssup.display_cols) stageStats[col] = {total: 0, count: 0};
  for (const a of vmssup.assignees) {
    for (const col of vmssup.display_cols) {
      for (const t of (a.columns[col] || [])) {
        stageStats[col].total += t.age_days;
        stageStats[col].count++;
      }
    }
  }

  // Throughput
  const weeks = rep.throughput_weeks || [];
  const weekLabels  = weeks.map(w => w.label);
  const openedVals  = weeks.map(w => w.opened);
  const closedVals  = weeks.map(w => w.closed);

  const section = document.createElement('div');
  section.id = 'reporting-section';
  section.innerHTML = `
    <div class="section-divider">Reporting</div>

    <div class="card" id="card-throughput">
      <div class="card-header">Throughput — Opened vs Closed (Last 4 Weeks)</div>
      <div class="card-body">
        <div class="chart-wrap" style="padding:8px 0">
          <canvas id="throughput-chart" style="max-height:220px;width:100%"></canvas>
        </div>
      </div>
    </div>

    <div class="two-col">
      <div class="card" id="card-account-heat">
        <div class="card-header">Account Heat Map — Top Accounts by Open CI Tickets</div>
        <div class="card-body">${accountHeatHtml(ci.account_heat, ci.account_unattributed, ci.account_attributed)}</div>
      </div>
      <div class="card" id="card-engineer-load">
        <div class="card-header">Engineer Load — CI + VMSSUP Combined</div>
        <div class="card-body">${engineerLoadHtml(loadList, maxLoad)}</div>
      </div>
    </div>

    <div class="card" id="card-pipeline">
      <div class="card-header">VMSSUP Pipeline Health — Avg Ticket Age by Stage</div>
      <div class="card-body">${pipelineHealthHtml(stageStats, vmssup.display_cols)}</div>
    </div>
  `;
  app.appendChild(section);

  // Draw throughput chart
  if (throughputChart) { throughputChart.destroy(); throughputChart = null; }
  const ctx = document.getElementById('throughput-chart');
  if (ctx) {
    throughputChart = new Chart(ctx.getContext('2d'), {
      type: 'bar',
      data: {
        labels: weekLabels,
        datasets: [
          { label: 'Opened', data: openedVals, backgroundColor: 'rgba(248,81,73,0.55)', borderColor: '#f85149', borderWidth: 1, borderRadius: 4 },
          { label: 'Closed', data: closedVals, backgroundColor: 'rgba(63,185,80,0.55)',  borderColor: '#3fb950', borderWidth: 1, borderRadius: 4 },
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: { labels: { color: '#c9d1d9', font: { size: 11 } } },
          tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${c.parsed.y}` } },
        },
        scales: {
          x: { ticks: { color: '#8b949e', font: { size: 11 } }, grid: { color: '#30363d' } },
          y: { ticks: { color: '#8b949e', font: { size: 11 } }, grid: { color: '#30363d' }, beginAtZero: true, precision: 0 },
        }
      }
    });
  }

  // Restore sizes for new cards then start watching
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  ['card-throughput','card-account-heat','card-engineer-load','card-pipeline'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const h = saved[id] || CARD_DEFAULTS[id];
    if (h) el.style.height = h + 'px';
  });
}

function renderVmssup(d) {
  const p       = d.prio_counts;
  const highest = p['Highest'] || 0;
  const high    = p['High']    || 0;
  const medium  = p['Medium']  || 0;

  function vmssupLink(extra) {
    const base = 'project = VMSSUP AND statusCategory not in (Done) AND NOT (description ~ "task id" AND reporter in (604fb2f681b82500682d022a))';
    return JIRA_NAV + encodeURIComponent(extra ? base + ' AND ' + extra : base);
  }

  const PRIO_BORDER = { 'Highest': 'var(--red)', 'High': 'var(--orange)', 'Medium': 'var(--blue)' };

  function boardTicket(t) {
    const color = PRIO_BORDER[t.priority] || 'var(--border)';
    return `
      <a class="board-ticket" href="${t.url}" target="_blank" style="border-left-color:${color}">
        <div class="board-ticket-summary">${t.summary}</div>
        <div class="board-ticket-footer">
          <span class="ticket-key" style="font-size:11px">${t.key}</span>
          ${prioBadge(t.priority)}
          <span style="color:var(--muted);font-size:10px;margin-left:auto">${t.age_days}d</span>
        </div>
      </a>`;
  }

  function assigneeRow(a) {
    const colsHtml = d.display_cols.map(col => {
      const tickets = a.columns[col] || [];
      const cntHtml = tickets.length ? `<span class="board-col-count">${tickets.length}</span>` : '';
      return `
        <div class="board-col">
          <div class="board-col-header">${col}${cntHtml}</div>
          <div class="board-col-tickets">${tickets.map(boardTicket).join('')}</div>
        </div>`;
    }).join('');
    return `
      <div class="assignee-group">
        <div class="assignee-header" onclick="this.parentElement.classList.toggle('collapsed')">
          <span class="assignee-chevron">▾</span>
          <span class="assignee-name">${a.name}</span>
          <span class="assignee-count">(${a.total} work item${a.total !== 1 ? 's' : ''})</span>
        </div>
        <div class="assignee-body">
          <div class="board-cols-row">${colsHtml}</div>
        </div>
      </div>`;
  }

  const stalledHtml = d.stalled.length ? `
    <div class="card">
      <div class="card-header">Stalled — High/Highest, No Movement ≥3 Days (${d.stalled.length})</div>
      <div class="card-body">
        <table class="oos-table">
          <thead><tr><th>Key</th><th>Priority</th><th>Stale</th><th>Assignee</th><th>Summary</th></tr></thead>
          <tbody>${d.stalled.map(t => `
            <tr>
              <td><a class="ticket-key" href="${t.url}" target="_blank">${t.key}</a></td>
              <td>${prioBadge(t.priority)}</td>
              <td><span class="age-pill" style="background:rgba(240,136,62,.15);color:var(--orange)">${t.stale_days}d</span></td>
              <td style="color:var(--muted);font-size:11px;white-space:nowrap">${t.assignee.split(' ')[0]}</td>
              <td class="ticket-summary" title="${t.summary}">${t.summary}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>` : '';

  document.getElementById('vmssup-app').innerHTML = `
    <div class="stats-row">
      <a class="stat-tile" href="${vmssupLink()}" target="_blank"><div class="val total">${d.total}</div><div class="lbl">Total Open</div></a>
      <a class="stat-tile" href="${vmssupLink('priority = Highest')}" target="_blank"><div class="val highest">${highest}</div><div class="lbl">Highest</div></a>
      <a class="stat-tile" href="${vmssupLink('priority = High')}" target="_blank"><div class="val high">${high}</div><div class="lbl">High</div></a>
      <a class="stat-tile" href="${vmssupLink('priority = Medium')}" target="_blank"><div class="val medium">${medium}</div><div class="lbl">Medium</div></a>
      <a class="stat-tile" href="${vmssupLink('updated <= -3d AND priority in (Highest, High)')}" target="_blank"><div class="val due">${d.stalled.length}</div><div class="lbl">Stalled ≥3d</div></a>
    </div>

    <div class="assignee-board">
      ${d.assignees.map(assigneeRow).join('')}
    </div>

    ${stalledHtml}
  `;
}

function render(d) {
  const p       = d.prio_counts;
  const highest = p['Highest'] || 0;
  const high    = p['High']    || 0;
  const medium  = p['Medium']  || 0;

  // Store globally for click handlers
  teamsTickets   = d.teams_tickets;
  accountTickets = d.account_tickets || {};

  otherTeamNames = [];
  const displayTeams = d.teams;
  teamData = displayTeams;

  const prioLabels  = ['Highest','High','Medium'].filter(k => p[k]);
  const prioVals    = prioLabels.map(k => p[k]);
  const prioColors  = prioLabels.map(k => PRIO_COLORS[k]);

  const teamLabels  = displayTeams.map(t => t.name);
  const teamVals    = displayTeams.map(t => t.total);
  const teamColors  = displayTeams.map((_, i) => TEAM_PALETTE[i % TEAM_PALETTE.length]);

  document.getElementById('app').innerHTML = `
    <!-- Stats -->
    <div class="stats-row">
      <a class="stat-tile" href="${jiraLink()}" target="_blank"><div class="val total">${d.total}</div><div class="lbl">Total CI</div></a>
      <a class="stat-tile" href="${jiraLink('priority = Highest')}" target="_blank"><div class="val highest">${highest}</div><div class="lbl">Highest</div></a>
      <a class="stat-tile" href="${jiraLink('priority = High')}" target="_blank"><div class="val high">${high}</div><div class="lbl">High</div></a>
      <a class="stat-tile" href="${jiraLink('priority = Medium')}" target="_blank"><div class="val medium">${medium}</div><div class="lbl">Medium</div></a>
      <a class="stat-tile" href="${jiraLink('duedate <= 3d AND duedate is not EMPTY')}" target="_blank"><div class="val due">${d.due_soon.length}</div><div class="lbl">Due ≤3 days</div></a>
    </div>

    <!-- Needs Team Response (from morning briefing MD) -->
    <!-- Two charts -->
    <div class="two-col">
      <div class="card" id="card-priority">
        <div class="card-header">By Priority</div>
        <div class="card-body">
          <div class="chart-wrap">
            <canvas id="priority-chart"></canvas>
            <div class="legend">
              ${legendHtml(prioLabels, prioColors, prioVals, lbl => jiraLink('priority = ' + lbl))}
            </div>
          </div>
        </div>
      </div>
      <div class="card" id="card-team">
        <div class="card-header">By Engineering Team</div>
        <div class="card-body">
          <div class="chart-wrap">
            <canvas id="team-chart"></canvas>
            <div class="legend">
              ${teamLabels.map((lbl, i) => {
                const pct = Math.round(teamVals[i] / d.total * 100);
                return `
                <div class="legend-row" style="cursor:pointer" onclick="openTeamModal('${lbl.replace(/'/g,"\\'")}')">
                  <div class="dot-label">
                    <div class="legend-dot" style="background:${teamColors[i]}"></div>
                    <span>${lbl}</span>
                  </div>
                  <span class="legend-count">${teamVals[i]} <span style="color:var(--muted);font-weight:400;font-size:11px">(${pct}%)</span></span>
                </div>`;
              }).join('')}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Age dist + Out of spec -->
    <div class="two-col">
      <div class="card" id="card-age-dist">
        <div class="card-header">Age Distribution</div>
        <div class="card-body">
          ${ageDistHtml(d.age_dist)}
        </div>
      </div>
      <div class="card" id="card-out-of-spec">
        <div class="card-header">Out of Spec (${d.out_of_spec.length})</div>
        <div class="card-body">
          ${outOfSpecHtml(d.out_of_spec)}
        </div>
      </div>
    </div>

    <!-- Filters row -->
    <div class="three-col">
      <div class="card" id="card-due-soon">
        <div class="card-header">Due Within 3 Days (${d.due_soon.length})</div>
        <div class="card-body">${ticketRows(d.due_soon, {showDue: true})}</div>
      </div>
      <div class="card" id="card-punted">
        <div class="card-header">Repeatedly Punted (${d.punted.length})</div>
        <div class="card-body">${ticketRows(d.punted, {showCreated: true})}</div>
      </div>
      <div class="card" id="card-never-sprint">
        <div class="card-header">Never in a Sprint (${d.never_sprint.length}${d.never_sprint.length===20?'+':''})</div>
        <div class="card-body">${ticketRows(d.never_sprint, {showCreated: true})}</div>
      </div>
    </div>

  `;

  if (prioChart) prioChart.destroy();
  prioChart = makeDoughnut('priority-chart', prioLabels, prioVals, prioColors, (i) => {
    window.open(jiraLink('priority = ' + prioLabels[i]), '_blank');
  });

  if (teamChart) teamChart.destroy();
  teamChart = makeDoughnut('team-chart', teamLabels, teamVals, teamColors, (i) => {
    openTeamModal(teamData[i].name);
  });
}

const CARD_IDS = ['card-needs-response','card-priority','card-team','card-age-dist','card-out-of-spec','card-due-soon','card-punted','card-never-sprint','card-throughput','card-account-heat','card-engineer-load','card-pipeline'];
const CARD_DEFAULTS = {
  'card-priority':     378,
  'card-team':         379,
  'card-age-dist':     369,
  'card-out-of-spec':  369,
  'card-due-soon':     420,
  'card-punted':       420,
  'card-never-sprint': 420,
  'card-throughput':   320,
  'card-account-heat': 420,
  'card-engineer-load':420,
  'card-pipeline':     300,
};
const STORAGE_KEY = 'ci-dash-sizes';

function saveSizes() {
  const sizes = {};
  CARD_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (el) sizes[id] = el.offsetHeight;
  });
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sizes));
}

function restoreSizes() {
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  CARD_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const h = saved[id] || CARD_DEFAULTS[id];
    if (h) el.style.height = h + 'px';
  });
}

function watchSizes() {
  let timer;
  const ro = new ResizeObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(saveSizes, 400);
  });
  CARD_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (el) ro.observe(el);
  });
}

async function load() {
  const btn = document.getElementById('refresh-btn');
  btn.textContent = 'Loading…';
  btn.classList.add('spinning');
  btn.disabled = true;
  try {
    const [ciResp, vmssupResp, repResp] = await Promise.all([fetch('/api/data'), fetch('/api/vmssup'), fetch('/api/reporting')]);
    ciData        = await ciResp.json();
    vmssupData    = await vmssupResp.json();
    reportingData = await repResp.json();
    render(ciData);
    renderVmssup(vmssupData);
    renderReporting(ciData, vmssupData, reportingData);
    updateNeedsResponseCard();
    restoreSizes();
    watchSizes();
    const active = currentTab === 'ci' ? ciData : vmssupData;
    document.getElementById('refresh-time').textContent = 'Refreshed ' + formatRefreshTime(active.refreshed_at);
  } catch(e) {
    document.getElementById('app').innerHTML = `<div class="loading" style="color:var(--red)">Error loading data: ${e}</div>`;
  } finally {
    btn.textContent = 'Refresh';
    btn.classList.remove('spinning');
    btn.disabled = false;
  }
}

load();
setInterval(load, 5 * 60 * 1000); // auto-refresh every 5 min
</script>
</body>
</html>
"""

@app.route('/api/releases')
def api_releases():
    zulip_email = os.environ.get('ZULIP_EMAIL', '')
    zulip_key   = os.environ.get('ZULIP_API_KEY', '')
    zulip_site  = os.environ.get('ZULIP_SITE', '')

    r = subprocess.run(
        ['curl', '-s', '-u', f'{zulip_email}:{zulip_key}',
         f'{zulip_site}/api/v1/messages?anchor=newest&num_before=100&num_after=0'
         '&narrow=%5B%7B%22operator%22%3A%22stream%22%2C%22operand%22%3A%22Announce%3A%20Video%20Production%20Releases%22%7D%5D'],
        capture_output=True, text=True
    )
    data     = json.loads(r.stdout)
    messages = data.get('messages', [])

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    releases = []
    by_day   = {}

    for m in messages:
        ts = datetime.fromtimestamp(m['timestamp'], tz=timezone.utc)
        if ts < cutoff:
            continue
        day = ts.strftime('%Y-%m-%d')
        by_day[day] = by_day.get(day, 0) + 1
        keys = re.findall(r'EEPD-\d+', m.get('content', ''))
        text = re.sub(r'<[^>]+>', '', m.get('content', ''))
        text = re.sub(r'\n+', '\n', text).strip()
        releases.append({
            'timestamp': ts.isoformat(),
            'date':      day,
            'topic':     m.get('subject', ''),
            'sender':    m.get('sender_full_name', ''),
            'eepd_keys': list(dict.fromkeys(keys)),
            'text':      text[:400],
        })

    cutoff_str = cutoff.strftime('%Y-%m-%d')
    ci_opened  = jira_search(
        f'{CI_HIST_BASE} AND created >= "{cutoff_str}"',
        ['created', 'summary', 'priority', 'status', 'project'], max_results=500
    )
    tickets_by_day = {}
    for issue in ci_opened:
        day = issue['fields']['created'][:10]
        tickets_by_day.setdefault(day, []).append({
            'key':      issue['key'],
            'summary':  issue['fields'].get('summary', ''),
            'priority': (issue['fields'].get('priority') or {}).get('name', ''),
            'status':   (issue['fields'].get('status') or {}).get('name', ''),
            'url':      f'{BASE}/browse/{issue["key"]}',
        })

    releases.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify({
        'releases':              releases,
        'by_day':                by_day,
        'total':                 len(releases),
        'tickets_by_day':        {day: len(v) for day, v in tickets_by_day.items()},
        'tickets_detail_by_day': tickets_by_day,
        'tickets_total':         len(ci_opened),
        'refreshed_at':          datetime.now(timezone.utc).isoformat(),
    })


@app.route('/api/daily-activity')
def api_daily_activity():
    import concurrent.futures, glob as _glob

    now_cdt   = datetime.now(timezone.utc) - timedelta(hours=5)
    today     = now_cdt.date()
    today_str = today.isoformat()

    cache_files = sorted(_glob.glob(os.path.expanduser('~/.claude/morning-briefing-cache/*.json')))
    prev_caches = [f for f in cache_files if os.path.basename(f) != f'{today_str}.json']
    yesterday_str = os.path.basename(prev_caches[-1]).replace('.json', '') if prev_caches else (today - timedelta(days=1)).isoformat()

    BASE_JQL = (
        '((project = EENS AND reporter not in (604fb2f681b82500682d022a)) '
        'OR (project in (EEPD, Infrastructure) AND labels = "customer-impact"))'
    )
    CLOSED = '"Closed","Done","resolved","Won\'t Investigate","Not Needed","Duplicate"'
    FIELDS = ['summary', 'status', 'priority', 'assignee']

    queries = {
        'yesterday_opened': f'{BASE_JQL} AND created >= "{yesterday_str}" AND created < "{today_str}" ORDER BY created ASC',
        'yesterday_closed': f'{BASE_JQL} AND status changed to ({CLOSED}) AFTER "{yesterday_str} 00:00" BEFORE "{today_str} 00:00" ORDER BY updated ASC',
        'today_opened':     f'{BASE_JQL} AND created >= "{today_str}" ORDER BY created ASC',
        'today_closed':     f'{BASE_JQL} AND status changed to ({CLOSED}) AFTER "{today_str} 00:00" ORDER BY updated ASC',
    }

    def run_query(item):
        key, jql = item
        try:
            issues = jira_search(jql, FIELDS, max_results=100)
        except Exception:
            issues = []
        return key, [
            {
                'key':      i['key'],
                'summary':  (i['fields'].get('summary') or '')[:80],
                'priority': (i['fields'].get('priority') or {}).get('name', '?'),
                'status':   (i['fields'].get('status') or {}).get('name', '?'),
                'assignee': (i['fields'].get('assignee') or {}).get('displayName', 'Unassigned'),
            }
            for i in issues
        ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        results = dict(ex.map(run_query, queries.items()))

    return jsonify({'yesterday': yesterday_str, 'today': today_str, 'data': results})


# ---------------------------------------------------------------------------
# Daily delta — snapshot-based CI count tracking
# ---------------------------------------------------------------------------

SNAPSHOT_DIR = pathlib.Path(__file__).parent / 'ci-snapshots'

_DELTA_JQL = (
    'project in (EEPD, Infrastructure, EENS) '
    'AND labels in (customer-impact) '
    'AND issuetype not in (Improvement, story) '
    'AND status not in (closed, Done, resolved, "Won\'t Investigate", "Not Needed", Duplicate)'
)
_DELTA_FIELDS = ['summary', 'priority', 'status', 'created', 'labels']


def _save_snapshot(date_str, ids):
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    p = SNAPSHOT_DIR / f'{date_str}.json'
    p.write_text(json.dumps({'date': date_str, 'count': len(ids),
                             'ids': sorted(ids),
                             'saved_at': datetime.now(timezone.utc).isoformat()}))


def _load_snapshot(date_str):
    p = SNAPSHOT_DIR / f'{date_str}.json'
    return json.loads(p.read_text()) if p.exists() else None


def _explain_entry(key, since_str, email, token):
    r = subprocess.run(
        ['curl', '-s', '-u', f'{email}:{token}',
         f'https://eagleeyenetworks.atlassian.net/rest/api/3/issue/{key}/changelog'],
        capture_output=True, text=True
    )
    try:
        for h in reversed(json.loads(r.stdout).get('values', [])):
            if h.get('created', '')[:10] < since_str:
                continue
            author = h.get('author', {}).get('displayName', 'someone')
            date   = h.get('created', '')[:10]
            for item in h.get('items', []):
                field = item.get('field', '')
                if field == 'labels':
                    from_l = set((item.get('fromString') or '').split())
                    to_l   = set((item.get('toString')   or '').split())
                    if 'customer-impact' in to_l and 'customer-impact' not in from_l:
                        return 'label_added', f'customer-impact label added by {author} on {date}'
                if field == 'priority':
                    return 'priority_change', f'Priority {item.get("fromString")} → {item.get("toString")} on {date}'
                if field == 'status':
                    from_s, to_s = item.get('fromString', ''), item.get('toString', '')
                    excluded = {'Closed', 'Done', 'Resolved', "Won't Investigate", 'Not Needed', 'Duplicate'}
                    if from_s in excluded and to_s not in excluded:
                        return 'reopened', f'Reopened ({from_s} → {to_s}) on {date}'
    except Exception:
        pass
    return 'unknown', 'No clear changelog reason'


def _explain_exit(key, email, token):
    r = subprocess.run(
        ['curl', '-s', '-u', f'{email}:{token}',
         f'https://eagleeyenetworks.atlassian.net/rest/api/3/issue/{key}?fields=status,summary,priority,labels'],
        capture_output=True, text=True
    )
    try:
        d          = json.loads(r.stdout)
        returned_key = d.get('key', key)
        f          = d['fields']
        status     = f.get('status', {}).get('name', '?')
        labels     = f.get('labels') or []
        if returned_key != key:
            return 'converted', f'Moved to {returned_key}', f, returned_key
        excluded_statuses = {'Closed', 'Done', 'Resolved', "Won't Investigate", 'Not Needed', 'Duplicate'}
        if status in excluded_statuses:
            return 'resolved', f'Status → {status}', f, status
        if 'customer-impact' not in labels:
            return 'label_removed', 'customer-impact label removed', f, status
        return 'unknown', f'Still open ({status}) but no longer in query', f, status
    except Exception:
        return 'unknown', 'Could not fetch ticket', {}, '?'


@app.route('/api/daily-delta')
def api_daily_delta():
    import concurrent.futures

    email = os.environ.get('JIRA_EMAIL', '')
    token = os.environ.get('JIRA_API_TOKEN', '')

    now_cdt       = datetime.now(timezone.utc) - timedelta(hours=5)
    today_str     = now_cdt.date().isoformat()
    yesterday_str = (now_cdt.date() - timedelta(days=1)).isoformat()

    today_issues = jira_search(_DELTA_JQL, _DELTA_FIELDS, max_results=500)
    today_map    = {i['key']: i for i in today_issues}
    today_ids    = set(today_map)
    _save_snapshot(today_str, today_ids)

    yesterday_snap = _load_snapshot(yesterday_str)
    if not yesterday_snap:
        snaps = sorted(SNAPSHOT_DIR.glob('*.json')) if SNAPSHOT_DIR.exists() else []
        snaps = [s for s in snaps if s.stem != today_str]
        yesterday_snap = json.loads(snaps[-1].read_text()) if snaps else None

    if not yesterday_snap:
        return jsonify({
            'today': today_str, 'yesterday': yesterday_str,
            'today_count': len(today_ids), 'yesterday_count': None,
            'delta': None, 'no_baseline': True, 'entered': [], 'exited': [],
        })

    yesterday_ids   = set(yesterday_snap['ids'])
    yesterday_count = yesterday_snap['count']
    baseline_date   = yesterday_snap['date']
    entered_keys    = today_ids - yesterday_ids
    exited_keys     = yesterday_ids - today_ids

    def categorize_entered(key):
        f        = today_map[key].get('fields', {})
        created  = (f.get('created') or '')[:10]
        summary  = (f.get('summary') or '')[:70]
        priority = (f.get('priority') or {}).get('name', '?')
        if created >= baseline_date:
            return {'key': key, 'summary': summary, 'priority': priority,
                    'created': created, 'reason': 'created', 'detail': f'Created {created}'}
        reason, detail = _explain_entry(key, baseline_date, email, token)
        return {'key': key, 'summary': summary, 'priority': priority,
                'created': created, 'reason': reason, 'detail': detail}

    def categorize_exited(key):
        reason, detail, f, status = _explain_exit(key, email, token)
        summary  = (f.get('summary') or key)[:70]
        priority = (f.get('priority') or {}).get('name', '?')
        return {'key': key, 'summary': summary, 'priority': priority,
                'status': status, 'reason': reason, 'detail': detail}

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        entered = list(ex.map(categorize_entered, entered_keys))
        exited  = list(ex.map(categorize_exited,  exited_keys))

    prio_order = {'Highest': 0, 'High': 1, 'Medium': 2, 'Low': 3, 'Lowest': 4}

    entered_key_map        = {e['key']: e for e in entered}
    converted              = []
    exited_converted_keys  = set()
    entered_converted_keys = set()
    for e in exited:
        if e['reason'] == 'converted':
            new_key = e['detail'].replace('Moved to ', '')
            if new_key in entered_key_map:
                converted.append({'old_key': e['key'], 'new_key': new_key,
                                   'summary': e['summary'], 'priority': e['priority'],
                                   'detail': f'{e["key"]} → {new_key} (moved between projects)'})
                exited_converted_keys.add(e['key'])
                entered_converted_keys.add(new_key)

    entered = [e for e in entered if e['key'] not in entered_converted_keys]
    exited  = [e for e in exited  if e['key'] not in exited_converted_keys]
    entered.sort(key=lambda x: prio_order.get(x['priority'], 5))
    exited.sort(key=lambda x:  prio_order.get(x['priority'], 5))

    return jsonify({
        'today':           today_str,
        'yesterday':       baseline_date,
        'today_count':     len(today_ids),
        'yesterday_count': yesterday_count,
        'delta':           len(today_ids) - yesterday_count,
        'no_baseline':     False,
        'entered':         entered,
        'exited':          exited,
        'converted':       converted,
    })


@app.route('/api/esn_health_stream')
def api_esn_health_stream():
    from flask import Response, stream_with_context
    from html import escape as html_escape
    import re as _re, sys

    esn = (flask_request.args.get('esn') or '').strip().lower()
    if not esn:
        return jsonify({'error': 'esn required'}), 400

    script = pathlib.Path(__file__).parent / 'esn_archiver_check.py'

    _ANSI = _re.compile(r'\x1b\[([0-9;]*)m')

    def ansi_to_html(text):
        result, last, open_spans = [], 0, 0
        for m in _ANSI.finditer(text):
            result.append(html_escape(text[last:m.start()]))
            code = m.group(1)
            if code in ('0', ''):
                result.append('</span>' * open_spans); open_spans = 0
            elif code == '1':  result.append('<span style="font-weight:600">');  open_spans += 1
            elif code == '31': result.append('<span style="color:#ff6b6b">');    open_spans += 1
            elif code == '32': result.append('<span style="color:#69db7c">');    open_spans += 1
            elif code == '33': result.append('<span style="color:#ffd43b">');    open_spans += 1
            last = m.end()
        result.append(html_escape(text[last:]))
        result.append('</span>' * open_spans)
        return ''.join(result)

    def generate():
        try:
            proc = subprocess.Popen(
                [sys.executable, str(script), esn],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
            for line in proc.stdout:
                stripped = line.rstrip('\n')
                if stripped.startswith('__JSON__:'):
                    yield f"event: summary\ndata: {stripped[9:]}\n\n"
                else:
                    yield f"data: {json.dumps(ansi_to_html(stripped))}\n\n"
            proc.wait()
        except Exception as e:
            yield f"data: {json.dumps('<span style=\"color:#ff6b6b\">ERROR: ' + html_escape(str(e)) + '</span>')}\n\n"
        yield f"data: {json.dumps('__DONE__')}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


def _eenadmin_fetch(search, search_type, session_id):
    import urllib.request, html, re as _re
    url = (f'https://eenadmin.eagleeyenetworks.com/eenadmin/search/'
           f'?search={urllib.request.quote(search)}&search_type={search_type}')
    req = urllib.request.Request(url, headers={
        'Cookie':     f'vbsadmin_sessionid={session_id}',
        'User-Agent': 'CI-Dashboard/1.0',
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        if '/login/' in resp.geturl():
            raise PermissionError('session_expired')
        body = resp.read().decode('utf-8', errors='replace')
    headers = []
    hdr_m = _re.search(r'<thead[^>]*>(.*?)</thead>', body, _re.DOTALL | _re.IGNORECASE)
    if hdr_m:
        headers = [html.unescape(_re.sub(r'<[^>]+>', '', h).strip())
                   for h in _re.findall(r'<th[^>]*>(.*?)</th>', hdr_m.group(1), _re.DOTALL | _re.IGNORECASE)
                   if h.strip()]
    rows = []
    for row in _re.findall(r'<tr[^>]*>(.*?)</tr>', body, _re.DOTALL | _re.IGNORECASE):
        cells = [html.unescape(_re.sub(r'<[^>]+>', '', c).strip())
                 for c in _re.findall(r'<td[^>]*>(.*?)</td>', row, _re.DOTALL | _re.IGNORECASE)]
        cells = [c for c in cells if c]
        if cells and len(cells) > 2:
            rows.append(dict(zip(headers, cells)) if headers else cells)
    return rows


def _parse_account_id(account_str):
    import re as _re
    m = _re.match(r'(\d{8})', (account_str or '').strip())
    return m.group(1) if m else None


@app.route('/api/esn_lookup')
def api_esn_lookup():
    esn        = (flask_request.args.get('esn') or '').strip().lower()
    session_id = os.environ.get('EENADMIN_SESSION', '')
    if not esn:
        return jsonify({'error': 'esn required'}), 400
    if not session_id:
        return jsonify({'error': 'no_session'}), 401
    try:
        device_rows = _eenadmin_fetch(esn, 'Device', session_id)
    except PermissionError:
        return jsonify({'error': 'session_expired'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 502

    if not device_rows:
        return jsonify({'esn': esn, 'found': False})

    dev         = device_rows[0]
    account_str = dev.get('Account', '')
    sub_acct_id = _parse_account_id(account_str)
    archivers   = dev.get('Archivers', '')
    sub_info = master_info = master_id = None

    if sub_acct_id:
        try:
            sub_rows = _eenadmin_fetch(sub_acct_id, 'Account', session_id)
            if sub_rows:
                sub_info  = sub_rows[0]
                master_id = sub_info.get('Master') or sub_info.get('master')
        except Exception:
            pass

    if master_id and master_id != '00000001':
        try:
            master_rows = _eenadmin_fetch(master_id, 'Account', session_id)
            if master_rows:
                master_info = master_rows[0]
        except Exception:
            pass

    return jsonify({
        'esn':   esn,
        'found': True,
        'device': {
            'esn':       dev.get('ESN', esn),
            'name':      dev.get('Name', ''),
            'firmware':  dev.get('Firmware', ''),
            'model':     ' '.join(dev.get('Model/HwVersion', '').split()),
            'serial':    dev.get('Serial #', ''),
            'ip':        dev.get('IP Address', ''),
            'archivers': [a.strip() for a in archivers.split(',') if a.strip()],
            'cameras':   dev.get('Cameras', ''),
        },
        'sub_account': {
            'id':      sub_info.get('ID', sub_acct_id) if sub_info else sub_acct_id,
            'name':    sub_info.get('Name', account_str) if sub_info else account_str,
            'cluster': sub_info.get('Cluster', '') if sub_info else '',
            'status':  sub_info.get('Status', '') if sub_info else '',
        } if sub_acct_id else None,
        'reseller': {
            'id':      master_info.get('ID', master_id) if master_info else master_id,
            'name':    master_info.get('Name', '') if master_info else '',
            'cluster': master_info.get('Cluster', '') if master_info else '',
            'status':  master_info.get('Status', '') if master_info else '',
        } if master_id and master_id != '00000001' else None,
    })


if __name__ == '__main__':
    port = int(os.environ.get('CI_DASH_PORT', 8081))
    print(f'\n  Customer Impact Health → http://localhost:{port}\n')
    app.run(host='127.0.0.1', port=port, debug=False, threaded=True)
