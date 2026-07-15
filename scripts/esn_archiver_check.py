#!/usr/bin/env python3
"""
Read-only ESN archiver health check.

Purpose:
  Single-pane-of-glass ESN archiver health check. Aggregates information
  that would otherwise require checking dhash, pod keys, bridge health scores,
  kubectl node state, and etag coverage across multiple tools and tabs.
  Intended for initial diagnosis — strictly read-only, makes no changes.
  Requires kubectl access.

Usage:
  python3 esn_archiver_check.py <ESN>
  python3 esn_archiver_check.py 10098d23

Sections:
  [1] ESN dhash provisioning key  — cluster, pod, retention, archiver list
  [2] Status Server               — live cloudConnectionStatus, edgeReportedDeviceStatus
  [3] Registry                    — apiv3 registration status and connect state
  [4] Pod key consistency         — confirms dhash and pod agree on archiver state
  [5] Bridge health scores        — load-based scores (0.0–1.0); archiver live connect state
  [6] Archiver node state         — kubectl NODE_READY / NODE_UNKNOWN
  [7] Etag coverage               — per-archiver coverage % and gap detection

Data Sources:
  - http://dproxy.test.eencloud.com/api/v2/dhash/node/v2/com.eencloud.dhash.esn:{esn}:provisioning
  - http://status-server.{pod}.eencloud.com:5001/api/v2/Status
  - https://registry.{pod}.eencloud.com/api/v2/Search?Include=czts&Device_in={esn}
  - http://dproxy.test.eencloud.com/api/v2/dhash/node/v1/com.eencloud.dhash.pod:{pod}:provisioning/{archiver_id}
  - http://dproxy.test.eencloud.com/api/v2/dhash/node/v2/com.eencloud.dhash.esn:{esn}:archiver/health
  - http://{archiver_id}.eagleeyenetworks.com:28080/query/cameras?c={esn}
  - kubectl get node {archiver_id} --context {pod}                — archiver node state
  - kubectl exec {pod} -- find /mnt/{disk}/{esn}/a                — etag file listing

What to look for:
  - All archivers DRAINED         → camera has no upload or playback path
  - All scores 0.0                → archivers overloaded or all drained
  - Score < 0.1                   → archiver heavily loaded, uploads/playback degraded
  - NODE_UNKNOWN + SS_LEVEL_SYNCED → stale dhash state; run fix_drained_mismatch.py
  - Etag coverage < 100%          → missing footage for those dates
  - Health key modified > 1h ago  → bridge not checking in; investigate bridge health
  - cloudConnectionStatus != connected → device not reaching cloud
  - Registry apiv3status != online    → registration issue
  - Archiver connect != STRM          → camera not streaming to archiver
"""

import argparse
import json
import re
import socket
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

DPROXY_V1 = "http://dproxy.test.eencloud.com/api/v2/dhash/node/v1"
DPROXY_V2 = "http://dproxy.test.eencloud.com/api/v2/dhash/node/v2"
KUBECTL    = str(Path.home() / "kubectl")

POD_TO_CLUSTER = {
    "aus1p1":"c001","aus1p2":"c005","aus1p3":"c012","aus1p4":"c014","aus1p5":"c015",
    "aus1p7":"c016","aus1p8":"c017","aus1p9":"c018","aus1p10":"c020","aus1p11":"c021",
    "aus1p12":"c023","aus1p13":"c024","aus1p14":"c026","aus1p15":"c027","aus1p16":"c028",
    "aus1p17":"c030","aus2p1":"c031","aus2p2":"c032","nrt1p1":"c006","hnd1p1":"c007",
    "hkg1p1":"c011","fra1p1":"c013","fra1p2":"c019","lon1p1":"c022","yyz1p1":"c025",
    "ruh1p1":"c029","aus1p6":"c004",
}

RED    = "\033[31m"
YELLOW = "\033[33m"
GREEN  = "\033[32m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def red(t):    return f"{RED}{t}{RESET}"
def yellow(t): return f"{YELLOW}{t}{RESET}"
def green(t):  return f"{GREEN}{t}{RESET}"
def bold(t):   return f"{BOLD}{t}{RESET}"


# ── dhash helpers ────────────────────────────────────────────────────────────

def fetch_dhash(key, v2=False):
    base = DPROXY_V2 if v2 else DPROXY_V1
    resp = requests.get(f"{base}/{key}", timeout=10)
    resp.raise_for_status()
    body = resp.json()
    if body.get("status_code") != 200:
        raise RuntimeError(f"dhash status {body.get('status_code')} for {key}")
    return body["data"]


def parse_ts(ts):
    return datetime.strptime(ts.split(".")[0], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def age_str(ts):
    s = int((datetime.now(timezone.utc) - parse_ts(ts)).total_seconds())
    if s < 120:   return f"{s}s ago"
    if s < 7200:  return f"{s//60}m ago"
    if s < 86400: return f"{s//3600}h ago"
    return f"{s//86400}d ago"


COMPARE_FIELDS = ("sync_status", "ip_address", "disk_label")

def diff_archivers(esn_list, pod_list):
    esn_by_id = {a["id"]: a for a in esn_list}
    pod_by_id = {a["id"]: a for a in pod_list}
    diffs = set(esn_by_id.keys()).symmetric_difference(pod_by_id.keys())
    for aid in esn_by_id.keys() & pod_by_id.keys():
        if any(esn_by_id[aid].get(f) != pod_by_id[aid].get(f) for f in COMPARE_FIELDS):
            diffs.add(aid)
    return diffs


# ── kubectl helpers ──────────────────────────────────────────────────────────

def kubectl_node_state(archiver_id, context):
    """Returns (state_str, detail) — state is NODE_READY/NODE_UNKNOWN/NODE_NOT_READY/NODE_NOT_FOUND."""
    try:
        r = subprocess.run(
            [KUBECTL, "get", "node", archiver_id, "--context", context,
             "-o", "jsonpath={.status.conditions[?(@.type==\"Ready\")].status}"],
            capture_output=True, text=True, timeout=10
        )
        val = r.stdout.strip()
        if r.returncode != 0 or not val:
            # Node not found
            return "NODE_NOT_FOUND", "node does not exist in cluster"
        if val == "True":
            return "NODE_READY", ""
        if val == "Unknown":
            return "NODE_UNKNOWN", "kubelet stopped posting — node unreachable"
        if val == "False":
            return "NODE_NOT_READY", "node exists but condition is False"
        return f"NODE_{val.upper()}", ""
    except Exception as e:
        return "KUBECTL_ERROR", str(e)


def kubectl_archiver_pod(archiver_id, context):
    """Find the archiver pod name running on this node (standard or SFIO)."""
    for label in ("release=archiver", "release=archiver-sfio"):
        try:
            r = subprocess.run(
                [KUBECTL, "get", "pod", "-l", label,
                 "--context", context,
                 f"--field-selector=spec.nodeName={archiver_id}",
                 "-o", "jsonpath={.items[0].metadata.name}"],
                capture_output=True, text=True, timeout=10
            )
            name = r.stdout.strip()
            if name:
                return name, label == "release=archiver-sfio"
        except Exception:
            pass
    return None, False


def kubectl_etag_list(pod_name, context, disk_label, esn, timeout=90):
    """List all etag paths for an ESN on a given disk via kubectl exec (read-only find)."""
    try:
        r = subprocess.run(
            [KUBECTL, "exec", pod_name, "--context", context, "--",
             "find", f"/mnt/{disk_label}/{esn}/a",
             "-maxdepth", "4", "-name", "*.etag"],
            capture_output=True, text=True, timeout=timeout
        )
        if r.returncode != 0:
            return None, r.stderr.strip()
        return r.stdout.strip().splitlines(), None
    except Exception as e:
        return None, str(e)


# ── etag analysis ────────────────────────────────────────────────────────────

ETAG_RE = re.compile(r'/(\d{4})/(\d{2})/(\d{2})/(\d{4}\d{2}\d{2}\d{2})\d{4}')

def analyse_etags(paths, retention_days):
    """
    Parse etag paths, count unique hour slots per day within retention window.
    Returns list of (date_str, unique_hours) sorted oldest-first, and a gaps list.
    Today's date is excluded from the <24 check since the day is always incomplete.
    """
    cutoff   = datetime.now(timezone.utc) - timedelta(days=retention_days)
    today_str = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    hours_by_day = defaultdict(set)

    for p in paths:
        m = ETAG_RE.search(p)
        if not m:
            continue
        y, mo, d, hh = m.group(1), m.group(2), m.group(3), m.group(4)[:10]
        date_str = f"{y}/{mo}/{d}"
        try:
            day_dt = datetime(int(y), int(mo), int(d), tzinfo=timezone.utc)
        except ValueError:
            continue
        if day_dt < cutoff:
            continue
        hours_by_day[date_str].add(hh)

    if not hours_by_day:
        return [], []

    sorted_days = sorted(hours_by_day.keys())
    gaps = []

    # Check for missing calendar days within range (excluding today)
    first = datetime.strptime(sorted_days[0], "%Y/%m/%d")
    last  = datetime.strptime(sorted_days[-1], "%Y/%m/%d")
    all_days = set()
    cur = first
    while cur <= last:
        all_days.add(cur.strftime("%Y/%m/%d"))
        cur += timedelta(days=1)

    missing_days = sorted(d for d in all_days - set(sorted_days) if d != today_str)
    if missing_days:
        gaps.append(f"Missing calendar days: {missing_days[:5]}{'...' if len(missing_days)>5 else ''}")

    rows = [(d, len(h)) for d, h in sorted(hours_by_day.items())]
    # Exclude today from incomplete-day check — it's never going to have 24 slots yet
    incomplete = [(d, h) for d, h in rows if h < 24 and d != today_str]
    if incomplete:
        gaps.append(f"{len(incomplete)} day(s) with <24 hour slots: " +
                    ", ".join(f"{d}({h}h)" for d, h in incomplete[:5]) +
                    ("..." if len(incomplete) > 5 else ""))

    return rows, gaps


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Read-only ESN archiver health check")
    parser.add_argument("esn", help="Camera ESN (e.g. 10100885)")
    args = parser.parse_args()
    esn = args.esn.lower()

    issues          = []
    warnings        = []
    next_steps      = []
    archiver_scores = {}   # aid -> float score
    archiver_etag   = {}   # aid -> {covered, retention, coverage_pct, gaps}
    cloud_status    = None
    edge_status     = None
    apiv3_status    = None
    archiver_connect = None

    # ── 1. ESN provisioning key ──────────────────────────────────────────────
    esn_key = f"com.eencloud.dhash.esn:{esn}:provisioning"
    print(f"\n{bold('='*62)}")
    print(f"{bold('ESN ARCHIVER HEALTH CHECK')}  —  {esn}")
    print(f"{bold('='*62)}")
    print(f"\n{bold('[ 1 ] ESN dhash provisioning key')}")
    print(f"  {esn_key}")

    try:
        esn_data  = fetch_dhash(esn_key)
        esn_value = esn_data["value"]
    except Exception as e:
        print(red(f"  ERROR: {e}"))
        sys.exit(1)

    pod      = esn_value.get("pod", "?")
    cluster  = esn_value.get("cluster", "?")
    cam_type = esn_value.get("type", "?")
    modified = esn_data.get("modified", "")
    sequence = esn_data.get("sequence", "?")

    print(f"  pod={pod}  cluster={cluster}  type={cam_type}")
    print(f"  modified: {modified}  ({age_str(modified)})  seq={sequence}")

    cam_settings = esn_value.get("camera_settings", {}) or {}
    retention    = cam_settings.get("cloud_retention_days") or 30
    preview_only = cam_settings.get("preview_only_cloud_retention", 0)

    # Camera age from create_timestamp
    create_ts  = esn_value.get("create_timestamp", "")
    cam_age_h  = None
    if create_ts:
        try:
            ct = datetime.strptime(create_ts.split(".")[0], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            cam_age_h = (datetime.now(timezone.utc) - ct).total_seconds() / 3600
        except Exception:
            pass
    new_camera = cam_age_h is not None and cam_age_h < 48

    age_note = f"  ← added {int(cam_age_h)}h ago" if cam_age_h is not None and cam_age_h < 48 else ""
    print(f"  retention: {retention}d cloud  preview_only={preview_only}{age_note}")

    archivers = esn_value.get("archivers", [])
    pending   = esn_value.get("pending", [])
    print(f"\n  Archivers ({len(archivers)}):")
    for a in archivers:
        sync  = a.get("sync_status", "?")
        sid   = a.get("id", "?")
        ip    = a.get("ip_address", "-")
        disk  = a.get("disk_label", "-")
        apod  = a.get("p") or pod
        acluster = POD_TO_CLUSTER.get(apod, "?")
        cross = acluster != cluster and acluster != "?"
        cluster_str = f"  {red(f'cluster={acluster} ← WRONG CLUSTER')}" if cross else f"  cluster={acluster}"
        print(f"  {sid:<8}  {sync:<22}  ip={ip:<18}  disk={disk}{cluster_str}")
        if sync == "SS_LEVEL_UNSYNCED":
            warnings.append(f"{sid} is SS_LEVEL_UNSYNCED")
        if cross:
            issues.append(f"{sid} is on {acluster} ({apod}) but account is on {cluster} ({pod})")

    if pending:
        print(f"\n  Pending: {pending}")
        warnings.append(f"Pending archiver operations: {pending}")

    # ── 2. Status Server ─────────────────────────────────────────────────────
    print(f"\n{bold('[ 2 ] Status Server')}")
    try:
        status_url = f"http://status-server.{pod}.eencloud.com:5001/api/v2/Status"
        sr = requests.get(status_url, timeout=10).json()
        device_status = next(
            (r for r in sr.get("data", {}).get("results", []) if r.get("esn") == esn),
            None
        )
        if device_status is None:
            print(yellow(f"  ESN not found in status server"))
            warnings.append("ESN not found in status server")
        else:
            sv2       = device_status.get("deviceStatusV2", {}) or {}
            cloud     = sv2.get("cloudConnectionStatus", "?")
            edge      = sv2.get("edgeReportedDeviceStatus", "?")
            error     = sv2.get("deviceSpecificError") or ""
            raw_status = device_status.get("status", "?")

            cloud_status = cloud
            edge_status  = edge

            if cloud == "connected":
                print(green(f"  cloudConnectionStatus=connected"))
            else:
                print(red(f"  cloudConnectionStatus={cloud}"))
                issues.append(f"Status Server: cloudConnectionStatus={cloud}")

            print(f"  edgeReportedStatus:  {edge}")
            print(f"  rawStatus:           {raw_status}")
            if error:
                print(yellow(f"  deviceSpecificError: {error}"))
                warnings.append(f"Status Server deviceSpecificError: {error}")
    except Exception as e:
        print(yellow(f"  Not available: {e}"))

    # ── 3. Registry ──────────────────────────────────────────────────────────
    print(f"\n{bold('[ 3 ] Registry')}")
    try:
        reg_url = f"https://registry.{pod}.eencloud.com/api/v2/Search?Include=czts&Device_in={esn}"
        rr = requests.get(reg_url, timeout=10).json()
        reg_result = (rr.get("data", {}).get("results") or [{}])[0]
        reg_status  = reg_result.get("status", {}) or {}
        apiv3       = reg_status.get("apiv3status", "?")
        connect     = reg_status.get("connect", "?")
        reg_ts      = reg_status.get("ts", "?")

        apiv3_status = apiv3

        if apiv3 == "online":
            print(green(f"  apiv3status=online"))
        else:
            print(red(f"  apiv3status={apiv3}"))
            issues.append(f"Registry: apiv3status={apiv3}")

        print(f"  connect:   {connect}")
        print(f"  timestamp: {reg_ts}")
    except Exception as e:
        print(yellow(f"  Not available: {e}"))

    # ── 4. Pod key consistency ───────────────────────────────────────────────
    print(f"\n{bold('[ 4 ] Pod key consistency check')}")
    seen_keys = set()

    for a in archivers:
        aid  = a.get("id")
        apod = a.get("p") or pod
        if not aid or (apod, aid) in seen_keys:
            continue
        seen_keys.add((apod, aid))

        try:
            pod_data    = fetch_dhash(f"com.eencloud.dhash.pod:{apod}:provisioning/{aid}")
            pod_entries = pod_data["value"]
            pod_mod     = pod_data.get("modified", "")
            match       = next((e for e in pod_entries if e.get("id") == esn), None)

            if match is None:
                msg = f"ESN {esn} NOT FOUND in pod key {apod}/{aid}"
                print(red(f"  {aid:<8}  ✗ NOT IN POD KEY  ({len(pod_entries)} entries, modified {age_str(pod_mod)})"))
                issues.append(msg)
                continue

            diff_ids = diff_archivers(archivers, match.get("archivers", []))
            if diff_ids:
                esn_ids = {x["id"] for x in archivers}
                pod_ids = {x["id"] for x in match.get("archivers", [])}
                missing = sorted(esn_ids - pod_ids)
                extra   = sorted(pod_ids - esn_ids)
                changed = sorted(diff_ids - set(missing) - set(extra))
                print(yellow(f"  {aid:<8}  ⚠ MISMATCH  ({len(pod_entries)} entries, modified {age_str(pod_mod)})"))
                if missing: print(red(f"           missing from pod key : {missing}")); issues.append(f"Pod {apod}/{aid}: missing {missing}")
                if extra:   print(yellow(f"           extra in pod key     : {extra}")); warnings.append(f"Pod {apod}/{aid}: extra {extra}")
                if changed: print(yellow(f"           field mismatch       : {changed}")); warnings.append(f"Pod {apod}/{aid}: field mismatch {changed}")
            else:
                print(green(f"  {aid:<8}  ✓ Consistent  ({len(pod_entries)} entries, modified {age_str(pod_mod)})"))
        except Exception as e:
            print(red(f"  {aid:<8}  ERROR: {e}"))
            warnings.append(f"Could not fetch pod key {apod}/{aid}: {e}")

    # ── 5. Bridge health scores + archiver live connect ─────────────────────
    print(f"\n{bold('[ 5 ] Bridge archiver health scores')}")
    ip_to_archiver = {a.get("ip_address"): a.get("id") for a in archivers if a.get("ip_address")}
    health_key = f"com.eencloud.dhash.esn:{esn}:archiver/health"
    try:
        hdata  = fetch_dhash(health_key, v2=True)
        hvalue = hdata["value"]
        print(f"  bridge={hvalue.get('hostname','?')}  modified={hdata.get('modified','')} ({age_str(hdata.get('modified','20200101000000.000'))})")
        print()
        for entry in sorted(hvalue.get("archivers", []), key=lambda x: x.get("score", 0), reverse=True):
            ip    = entry.get("ip", "?")
            score = entry.get("score", 0.0)
            aid   = ip_to_archiver.get(ip, f"?({ip})")
            archiver_scores[aid] = score
            if score == 0.0:
                print(f"  {aid:<8}  " + red(f"score=0.0000  ← score=0, customer never routed here"))
                issues.append(f"{aid} score=0.0 — excluded from playback routing")
            elif score < 0.1:
                print(f"  {aid:<8}  " + yellow(f"score={score:.4f}  ← low"))
            else:
                print(f"  {aid:<8}  " + green(f"score={score:.4f}"))
    except Exception as e:
        print(yellow(f"  Not available: {e}"))

    # Archiver live connect status
    synced_archivers = [a for a in archivers if a.get("sync_status") == "SS_LEVEL_SYNCED"]
    if synced_archivers:
        first_archiver = synced_archivers[0].get("id")
        try:
            cam_url = f"http://{first_archiver}.eagleeyenetworks.com:28080/query/cameras?c={esn}"
            cr = requests.get(cam_url, timeout=10).json()
            cam_data = cr.get(esn, {})
            if cam_type == "camera":
                props = (cam_data.get("properties") or [{}])[0]
                cam_stat = props.get("status", {}) or {}
                connect  = cam_stat.get("connect", "?")
                sticky   = cam_stat.get("stickyconnect", "?")
                model    = cam_stat.get("model", "?")
                version  = cam_stat.get("version", "?")
                print()
                archiver_connect = connect

                if connect == "STRM":
                    print(green(f"  Archiver connect=STRM (streaming)"))
                elif connect in ("ATTD", "IGND"):
                    print(yellow(f"  Archiver connect={connect}"))
                    warnings.append(f"Archiver reports connect={connect} — not streaming")
                else:
                    print(red(f"  Archiver connect={connect}"))
                    issues.append(f"Archiver reports connect={connect}")
                print(f"  stickyconnect: {sticky}  model: {model}  version: {version}")
            elif cam_type == "bridge":
                health = cam_data.get("health")
                print()
                if health:
                    bad = [k for k, v in health.items() if v != "OK"]
                    if not bad:
                        print(green(f"  Archiver bridge health: OK"))
                    else:
                        print(red(f"  Archiver bridge health failures: {bad}"))
                        issues.append(f"Archiver bridge health failures: {bad}")
                else:
                    status_hex = cam_data.get("status_hex", "?")
                    print(yellow(f"  Archiver: no health block  status_hex={status_hex}"))
        except Exception as e:
            print(yellow(f"\n  Archiver live status not available: {e}"))

    # ── 6. Node state (kubectl) ──────────────────────────────────────────────
    print(f"\n{bold('[ 6 ] Archiver node state (kubectl)')}")
    archiver_states = {}
    for a in archivers:
        aid  = a.get("id")
        apod = a.get("p") or pod
        sync = a.get("sync_status", "?")
        if not aid:
            continue
        state, detail = kubectl_node_state(aid, apod)
        archiver_states[aid] = state
        detail_str = f"  — {detail}" if detail else ""

        if state == "NODE_READY":
            print(green(f"  {aid:<8}  {state}{detail_str}"))
        elif state == "NODE_UNKNOWN":
            print(red(f"  {aid:<8}  {state}{detail_str}"))
            if sync != "SS_LEVEL_DRAINED":
                issues.append(f"{aid} is NODE_UNKNOWN but still {sync} in dhash")
        elif state == "NODE_NOT_FOUND":
            print(red(f"  {aid:<8}  {state}{detail_str}"))
            if sync != "SS_LEVEL_DRAINED":
                issues.append(f"{aid} is NODE_NOT_FOUND (decommissioned?) but still {sync} in dhash")
        elif state == "NODE_NOT_READY":
            print(yellow(f"  {aid:<8}  {state}{detail_str}"))
            warnings.append(f"{aid} is NODE_NOT_READY")
        else:
            print(yellow(f"  {aid:<8}  {state}{detail_str}"))

    # ── 7. Etag coverage (kubectl exec, read-only find) ──────────────────────
    print(f"\n{bold(f'[ 7 ] Etag coverage (last {retention}d)')}")
    for a in archivers:
        aid   = a.get("id")
        disk  = a.get("disk_label")
        apod  = a.get("p") or pod
        sync  = a.get("sync_status", "?")
        state = archiver_states.get(aid, "?")

        if sync != "SS_LEVEL_SYNCED":
            print(f"\n  {aid}  — skipping ({sync})")
            continue
        if state in ("NODE_UNKNOWN", "NODE_NOT_FOUND"):
            print(f"\n  {aid}  — skipping (node is {state}, no pod to exec into)")
            continue
        if not disk:
            print(f"\n  {aid}  — skipping (no disk_label)")
            continue

        pod_name, is_sfio = kubectl_archiver_pod(aid, apod)
        sfio_tag  = "  [SFIO]" if is_sfio else ""
        print(f"\n  {aid}  disk={disk}  pod={apod}{sfio_tag}")
        if not pod_name:
            print(red(f"    ✗ No archiver pod found on node"))
            warnings.append(f"{aid}: no archiver pod found, cannot check etags")
            continue

        paths, err = kubectl_etag_list(pod_name, apod, disk, esn, timeout=90)
        if err or paths is None:
            print(yellow(f"    ⚠ Could not list etags: {err}"))
            warnings.append(f"{aid}: etag find failed — {err}")
            continue

        if not paths:
            if new_camera:
                print(yellow(f"    ⚠ No etag files yet — camera only {int(cam_age_h)}h old, expected"))
            else:
                print(red(f"    ✗ No etag files found — history missing on this archiver"))
                issues.append(f"{aid}: no etag files found for {esn}")
            continue

        rows, gaps = analyse_etags(paths, retention)
        covered   = len(rows)
        total_hours  = sum(h for _, h in rows) if rows else 0
        expected_hrs = retention * 24
        first_day    = rows[0][0] if rows else "?"
        last_day     = rows[-1][0] if rows else "?"

        # Coverage based on actual hour slots vs expected — penalises incomplete days
        coverage_pct = min(total_hours / expected_hrs, 1.0) if expected_hrs else 0
        bar_filled   = int(round(coverage_pct * 20))
        bar          = '█' * bar_filled + '░' * (20 - bar_filled)
        pct_str = f"{int(coverage_pct*100)}%"
        hr_str  = f"{total_hours}/{expected_hrs}h"
        if new_camera:
            cov_str = yellow(f"{hr_str} ({pct_str}) — camera {int(cam_age_h)}h old")
        elif coverage_pct < 0.25:
            cov_str = red(f"{hr_str} ({pct_str}) SEVERELY INCOMPLETE")
            issues.append(f"{aid}: only {total_hours}h of {expected_hrs}h covered ({pct_str}) — severely incomplete")
        elif coverage_pct < 0.85:
            cov_str = yellow(f"{hr_str} ({pct_str})")
            warnings.append(f"{aid}: only {total_hours}h of {expected_hrs}h covered ({pct_str}) — history may be incomplete")
        else:
            cov_str = green(f"{hr_str} ({pct_str})")

        print(f"    {bar}  {cov_str}  ({first_day} → {last_day})")

        for gap in gaps:
            print(yellow(f"    ⚠ {gap}"))
            warnings.append(f"{aid} etag gaps: {gap}")

        archiver_etag[aid] = {
            "covered":      covered,
            "coverage_pct": int(coverage_pct * 100),
            "gaps":         len(gaps),
            "first_day":    first_day,
            "last_day":     last_day,
        }

        if not gaps and coverage_pct >= 0.85:
            print(green(f"    ✓ No gaps detected"))

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{bold('='*62)}")
    print(bold("SUMMARY"))
    print(bold('='*62))

    synced   = [a for a in archivers if a.get("sync_status") == "SS_LEVEL_SYNCED"]
    drained  = [a for a in archivers if a.get("sync_status") == "SS_LEVEL_DRAINED"]
    unsynced = [a for a in archivers if a.get("sync_status") == "SS_LEVEL_UNSYNCED"]
    healthy  = [a for a in synced if archiver_states.get(a["id"]) == "NODE_READY"]
    dead     = [a for a in synced if archiver_states.get(a["id"]) in ("NODE_UNKNOWN", "NODE_NOT_FOUND")]

    print(f"  Total archivers   : {len(archivers)}")
    print(f"  NODE_READY+synced : {green(str(len(healthy)))}")
    if dead:
        for a in dead:
            state = archiver_states.get(a["id"], "?")
            print(red(f"  {a['id']:<10} : SS_LEVEL_SYNCED but {state}  ← needs fix_drained_mismatch.py"))
    print(f"  Drained           : {len(drained)}")
    print(f"  Unsynced          : {yellow(str(len(unsynced))) if unsynced else '0'}")
    print(f"  Cloud retention   : {retention}d")

    if issues:
        print(f"\n{red('ISSUES')} ({len(issues)}):")
        for i in issues:
            print(red(f"  ✗ {i}"))

    if warnings:
        print(f"\n{yellow('WARNINGS')} ({len(warnings)}):")
        for w in warnings:
            print(yellow(f"  ⚠ {w}"))

    if not issues and not warnings:
        print(green("\n  ✓ No issues found"))

    print(f"\n{bold('RECOMMENDED NEXT STEPS')}:")
    has_action = False
    if dead:
        for a in dead:
            msg = f"{a['id']} is {archiver_states[a['id']]} but SS_LEVEL_SYNCED — run fix_drained_mismatch.py {esn}:{a['id']}"
            print(red(f"  • {msg}"))
            next_steps.append({"severity": "error", "text": msg})
            has_action = True
    if unsynced:
        for a in unsynced:
            msg = f"{a['id']} is SS_LEVEL_UNSYNCED — may need probe_sync_etags.py --esn {esn} --archiver {a['id']} --retention {retention}"
            print(yellow(f"  • {msg}"))
            next_steps.append({"severity": "warning", "text": msg})
            has_action = True
    for i in issues:
        if "severely incomplete" in i:
            aid = i.split(":")[0]
            msg = f"{aid} has severely incomplete etag history — needs probe_sync_etags.py --esn {esn} --archiver {aid} --retention {retention}"
            print(red(f"  • {msg}"))
            next_steps.append({"severity": "error", "text": msg})
            has_action = True
    for w in warnings:
        if "history may be incomplete" in w:
            aid = w.split(":")[0]
            msg = f"{aid} has partial etag history — consider probe_sync_etags.py --esn {esn} --archiver {aid} --retention {retention}"
            print(yellow(f"  • {msg}"))
            next_steps.append({"severity": "warning", "text": msg})
            has_action = True
        elif "missing calendar days" in w:
            aid = w.split(" ")[0]
            msg = f"{aid} has calendar gaps in etag history — investigate or run probe_sync_etags.py"
            print(yellow(f"  • {msg}"))
            next_steps.append({"severity": "warning", "text": msg})
            has_action = True
    if not has_action and not issues and not warnings:
        print(green("  • Camera looks healthy — no action needed"))
        next_steps.append({"severity": "ok", "text": "Camera looks healthy — no action needed"})
    elif not has_action and not issues:
        print(green("  • No critical actions needed — review warnings above"))
        next_steps.append({"severity": "ok", "text": "No critical actions needed — review warnings above"})
    print()

    # ── JSON summary for dashboard ───────────────────────────────────────────
    etag_summary = {}
    for a in archivers:
        aid  = a.get("id")
        etag_summary[aid] = archiver_etag.get(aid, {})

    summary = {
        "esn":              esn,
        "pod":              pod,
        "cluster":          cluster,
        "type":             cam_type,
        "retention":        retention,
        "cloud_status":     cloud_status,
        "edge_status":      edge_status,
        "apiv3_status":     apiv3_status,
        "archiver_connect": archiver_connect,
        "archivers": [
            {
                "id":         a.get("id"),
                "sync":       a.get("sync_status"),
                "ip":         a.get("ip_address"),
                "disk":       a.get("disk_label"),
                "pod":        a.get("p") or pod,
                "cluster":    POD_TO_CLUSTER.get(a.get("p") or pod, "?"),
                "node_state": archiver_states.get(a.get("id"), "?"),
                "score":      archiver_scores.get(a.get("id")),
                **etag_summary.get(a.get("id"), {}),
            }
            for a in archivers
        ],
        "issues":     issues,
        "warnings":   warnings,
        "next_steps": next_steps,
    }
    print(f"__JSON__:{json.dumps(summary)}")


if __name__ == "__main__":
    main()
