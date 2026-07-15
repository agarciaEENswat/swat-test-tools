# agarcia-test-tools

Internal tools for Eagle Eye Networks support and engineering operations — dashboards, Claude skills, and QA utilities.

---

## Credentials — Set This Up First

All tools authenticate via environment variables. The easiest way is a `.env` file — create it once in the repo root and it's picked up automatically.

**Create `scripts/.env`:**

```bash
# Required — JIRA (all tools)
JIRA_EMAIL=your-email@een.com
JIRA_API_TOKEN=your-jira-api-token

# Required — Zulip (dashboard releases tab + morning briefing)
ZULIP_EMAIL=your-email@een.com
ZULIP_API_KEY=your-zulip-api-key
ZULIP_SITE=https://chat.eencloud.com

# Optional — Zulip DM target (morning briefing only)
ZULIP_USER_ID=your-numeric-zulip-id
```

**Where to get them:**
- **JIRA API token:** [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens) → Create API token
- **Zulip API key:** chat.eencloud.com → Personal Settings → Account & Privacy → API key
- **Zulip User ID:** chat.eencloud.com/#settings/account (numeric ID shown in profile)

> Already have these in `~/.zshrc`? No change needed — your existing env vars take priority and the `.env` file is ignored.

---

## Quick Start — SWAT Dashboard

```bash
# 1. Clone
git clone https://github.com/agarciaEENswat/agarcia-test-tools.git
cd agarcia-test-tools/scripts

# 2. Create your .env file (see Credentials section above)

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python3 swat-ci-dashboard.py
```

Then open **http://localhost:8081**.

To run on a different port:
```bash
CI_DASH_PORT=9000 python3 swat-ci-dashboard.py
```

---

## Quick Start — Morning Briefing Skill

Runs a full daily JIRA briefing and sends it to you as a Zulip DM. Requires [Claude Code](https://claude.ai/code).

```bash
# 1. Clone (skip if already done)
git clone https://github.com/agarciaEENswat/agarcia-test-tools.git
cd agarcia-test-tools

# 2. Copy scripts to ~/Scripts
mkdir -p ~/Scripts
cp scripts/jira-stalker.py ~/Scripts/
cp scripts/jira-account-backfill.py ~/Scripts/

# 3. Install the skill
mkdir -p ~/.claude/skills/morning-briefing
cp claude-skills/morning-briefing/SKILL.md ~/.claude/skills/morning-briefing/SKILL.md

# 4. Edit the TEAM list in jira-stalker to match your support team
nano ~/Scripts/jira-stalker.py   # update TEAM = [...] at the top
```

Then in Claude Code:
```
/morning-briefing
```

---

## Tools

### SWAT CI Dashboard

**File:** `scripts/swat-ci-dashboard.py`

A local web dashboard for monitoring customer-impact tickets, the VMSSUP support board, production releases, and daily CI activity.

**Tabs:**

#### Customer Impact
| Section | Description |
|---------|-------------|
| Stat tiles | Total CI tickets, Highest/High/Medium counts, Due ≤3 days |
| By Priority / By Team | Doughnut charts — click to drill down |
| Age Distribution | Tickets bucketed by age with High/Medium breakdown |
| Out of Spec | Tickets violating SLA: Highest >7d, High >14d, any >28d |
| Due Within 3 Days | Tickets with an approaching due date |
| Repeatedly Punted | Tickets added to 3+ sprints without closing |
| Never in a Sprint | Backlog tickets with no engineering commitment |
| Needs Team Response | Surfaced from a loaded morning briefing MD file |

**Reporting section:**
| Section | Description |
|---------|-------------|
| Throughput | Opened vs closed per week, last 4 weeks |
| Account Heat Map | Top accounts by open CI ticket count |
| Engineer Load | Combined CI + VMSSUP count per person |
| Pipeline Health | Avg ticket age per VMSSUP stage |

#### VMSSUP Board
Live view of the VMSSUP Kanban board grouped by assignee, with stall detection for High/Highest tickets with no movement in ≥3 days.

#### Morning Briefing
Drop a `.md` briefing file to render it in-dashboard. Injects a summary banner and a Needs Team Response card into the CI tab.

#### Releases
Last 30 days of production releases pulled from Zulip, correlated with CI tickets opened on the same day. Requires `ZULIP_*` env vars.

#### Daily Activity
Yesterday and today's CI ticket opens and closes at a glance.

#### Daily Delta
Snapshot-based diff — explains exactly why the CI count moved since yesterday (new tickets, labels added, reopened, resolved).

#### ESN Health Check
Enter an ESN to stream a live archiver health check — dhash provisioning, status server, pod key consistency, health scores, node state, and etag coverage. Requires `esn_archiver_check.py` in the same directory and `kubectl` access.

#### ESN Lookup
Enter an ESN to look up device info, sub-account, and reseller from eenadmin. Requires an active eenadmin session.

---

### ESN Archiver Health Check

**File:** `scripts/esn_archiver_check.py`

Standalone CLI tool for ESN archiver diagnostics. Aggregates dhash, status server, registry, pod key consistency, health scores, kubectl node state, and etag coverage into a single report.

```bash
python3 scripts/esn_archiver_check.py <ESN>
# e.g.
python3 scripts/esn_archiver_check.py 10098d23
```

Requires `kubectl` with access to the relevant cluster context.

---

### Morning Briefing (Claude Code Skill)

**File:** `claude-skills/morning-briefing/SKILL.md`

Full daily JIRA briefing sent as a Zulip DM. Covers new tickets, high/medium priority open, customer impact age distribution, needs-team-response, out of spec, sprint carry-over, and per-team breakdowns.

**Install:**
```bash
mkdir -p ~/.claude/skills/morning-briefing
cp claude-skills/morning-briefing/SKILL.md ~/.claude/skills/morning-briefing/SKILL.md
```

Also requires these scripts at `~/Scripts/`:
```bash
cp scripts/jira-stalker.py ~/Scripts/
cp scripts/jira-account-backfill.py ~/Scripts/
```

Run in Claude Code: `/morning-briefing`

---

### JIRA Stalker

**File:** `scripts/jira-stalker.py`

Flags tickets where the support team hasn't responded within a threshold. Groups by last team commenter, sorted by urgency score. Used by the morning briefing skill.

```bash
python3 scripts/jira-stalker.py --prio high --days 1
python3 scripts/jira-stalker.py --prio medium --days 2
```

**Setup:** Edit the `TEAM` list at the top of the file with your team's JIRA display names.

---

### JIRA Account Backfill

**File:** `scripts/jira-account-backfill.py`

Fills in missing account custom fields on CI tickets by parsing the description. Keeps the Account Heat Map accurate.

```bash
python3 scripts/jira-account-backfill.py          # dry run
python3 scripts/jira-account-backfill.py --write  # apply
python3 scripts/jira-account-backfill.py --silent # write + JSON summary (used by morning briefing)
```

---

## Repository Structure

```
agarcia-test-tools/
├── README.md
├── examples/
│   └── morning-briefing-example.md
├── screenshots/
│   └── ci-dashboard.png
├── scripts/
│   ├── swat-ci-dashboard.py          # SWAT CI Dashboard (main)
│   ├── esn_archiver_check.py         # ESN archiver health check CLI
│   ├── jira_client.py                # JIRA API helpers
│   ├── queries.py                    # JQL query constants
│   ├── themes.py                     # Ticket theme classifier
│   ├── jira-stalker.py               # No-response ticket detector
│   ├── jira-account-backfill.py      # Account field backfill
│   └── requirements.txt              # Python dependencies
├── claude-skills/
│   └── morning-briefing/
│       └── SKILL.md
├── qa-starter-kit/
│   └── README.md
└── Notes/
```

---

## License

Internal use for Eagle Eye Networks.
