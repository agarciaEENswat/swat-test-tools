# Eagle Eye Networks - Master Technical Reference Guide

**Last Updated:** 2026-09-21
**Compiled from:** ACG Support Documentation, SWAT Procedures, Diagnostic Tools, Customer Impact Runbooks, "ACG (Swat)" and "ACG Cheat Sheet (support)" (Google Drive)

---

## Table of Contents

1. [Bridge Operations & Management](#1-bridge-operations--management)
   - [Connecting to Bridges](#connecting-to-bridges)
   - [Platform Detection & Version Management](#platform-detection--version-management)
   - [Container Management](#container-management)
   - [Health Monitoring & Diagnostics](#health-monitoring--diagnostics)
   - [Certificate & Credential Management](#certificate--credential-management)

2. [Camera Operations](#2-camera-operations)
   - [Camera Discovery](#camera-discovery)
   - [Camera Configuration](#camera-configuration)
   - [Firmware Updates](#firmware-updates)
   - [Camera Status Troubleshooting](#camera-status-troubleshooting)
   - [GUID Management](#guid-management)

3. [Network & Connectivity](#3-network--connectivity)
   - [Interface Management](#interface-management)
   - [Network Diagnostics](#network-diagnostics)
   - [DNS & DHCP](#dns--dhcp)
   - [Firewall Testing](#firewall-testing)
   - [Switch Management](#switch-management)

4. [Storage & RAID](#4-storage--raid)
   - [RAID Diagnostics](#raid-diagnostics)
   - [Disk Health Monitoring](#disk-health-monitoring)
   - [Filesystem Operations](#filesystem-operations)
   - [Storage Management](#storage-management)

5. [Video & Footage Operations](#5-video--footage-operations)
   - [Download Procedures](#download-procedures)
   - [Footage Verification](#footage-verification)
   - [Archiver Management](#archiver-management)
   - [Stream Testing](#stream-testing)

6. [System Diagnostics & Logs](#6-system-diagnostics--logs)
   - [Log Analysis](#log-analysis)
   - [Kernel Debugging](#kernel-debugging)
   - [Performance Monitoring](#performance-monitoring)
   - [Error Tracking](#error-tracking)

7. [Update & Upgrade Procedures](#7-update--upgrade-procedures)
   - [Platform 1 (CentOS/Yum-based)](#platform-1-centosyum-based)
   - [Platform 2 (Fedora/DNF-based)](#platform-2-fedoradnf-based)
   - [Container Upgrades](#container-upgrades)
   - [Troubleshooting Failed Upgrades](#troubleshooting-failed-upgrades)

8. [Advanced Infrastructure](#8-advanced-infrastructure)
   - [Kubernetes Operations](#kubernetes-operations)
   - [New Pod Testing & Validation](#new-pod-testing--validation)
   - [Microservices Monitoring](#microservices-monitoring)
   - [Event & Notification Pipeline](#event--notification-pipeline)
   - [Jobs API Tracking](#jobs-api-tracking)

9. [Specialized Features](#9-specialized-features)
   - [LPR (License Plate Recognition)](#lpr-license-plate-recognition)
   - [Analytics Configuration](#analytics-configuration)
   - [Local Display (LocalX)](#local-display-localx)
   - [Display Stations (Ionodes)](#display-stations-ionodes)
   - [InHand Networks Device Manager](#inhand-networks-device-manager)
   - [TalkDown Audio](#talkdown-audio)

10. [Customer Support Runbook](#10-customer-support-runbook)
    - [Quick Resolution Patterns](#quick-resolution-patterns)
    - [Common Issues by Category](#common-issues-by-category)
    - [Escalation Procedures](#escalation-procedures)
    - [JIRA Ticket Guidelines](#jira-ticket-guidelines)
    - [Support Templates](#support-templates)

11. [Quick Reference](#11-quick-reference)
    - [Most-Used Commands](#most-used-commands)
    - [Conversions & Utilities](#conversions--utilities)
    - [API Endpoints](#api-endpoints)
    - [Camera Tool Status Codes](#camera-tool-status-codes)
    - [Emergency Procedures](#emergency-procedures)

---

# 1. Bridge Operations & Management

## Connecting to Bridges

### SSH Access Methods

**Standard SSH Access (Port 33022):**
```bash
# Direct SSH to bridge
ssh root@<bridge_IP> -p 33022

# From another bridge on same network
ssh root@<IP>

# SSH from within bridge to host
ssh root@localhost -p 33022

# MFG account access
ssh mfg@localhost -p [port#]
# Password: eagle23soaring OR een
```

**Finding Bridges on Network:**
```bash
# Platform 1 bridges (port 33022)
nmap -oG - -p 33022 $(ip route | grep -v default | grep -E 'wan|eth1' | awk -F ' +' '{ print $1}') | grep open

# Or with specific CIDR
nmap -oG - -p 33022 {IP/CIDR} | grep open
```

**Exec Access (Without Unlocking Sub-Account):**
```bash
# Access execute.html directly
http://<ESN>.a.plumv.com:28080/execute.html?c=<ESN>

# Example:
http://100b213b.a.plumv.com:28080/execute.html?c=100b213b
```

**Exec Command Template:**
```bash
# Use for running commands via exec (replace " with \")
Bridge_ESN=""
command=""
base64_command=$(echo -n "${command}" | base64 | tr -d "\n")
curl -s "http://${Bridge_ESN}.a.plumv.com:28080/camera/command?c=${Bridge_ESN};t=execute;r=json;a=${base64_command}" | jq -r '.body' | sed "s@+@ @g;s@%@\\x@g" | xargs -0 printf "%b"
unset Bridge_ESN; unset command; unset base64_command
```

**Emergency Tunnel (EmTun) Setup:**
```bash
# From exec only
curl -O https://mfg.int.eencloud.com/emergency-tunnel.sh -k
bash emergency-tunnel.sh --keep --noexec
/setup/emergency-tunnel
# Then log into MFG and paste the SSH output from exec
```

**Trojan Horse to Camera/Switch:**
```bash
# SSH tunnel to access camera web interface
ssh root@<bridge_IP> -o UserKnownHostsFile=/dev/null -p<bridge_port> -L8088:<camera_IP>:80

# Example:
ssh root@192.40.5.251 -o UserKnownHostsFile=/dev/null -p54300 -L8088:10.143.52.240:80

# Then open browser: localhost:8088
```

**Password Reset (if root password doesn't work):**
```bash
# Simple fix (until reboot)
echo 'root:<root_pass_from_dashboard>' | chpasswd && echo Yes

# Permanent fix - update personality.json
grep root /etc/shadow  # Get new password hash
# Edit /personality.json and change rootPassword to new hash
personalityctl commit
```

**Reinstall SSH (if handshake fails):**
```bash
# In exec or host
yum install -y openssh openssh-server

# Or full reinstall
yum --disablerepo=* --enablerepo=een clean all && yum reinstall --disablerepo=* --enablerepo=een -y openssh-clients openssh openssh-server
```

---

## Platform Detection & Version Management

### Check Platform Version

```bash
# Get host OS version
ipccli --get_host_os

# Check if Platform 1 or Platform 2
cat /var/log/earlyboot.txt

# Bridge diagnostic (shows platform info)
bridge-diag
bridge-diag --long

# Check current versions
ipccli --list_containers

# Get ESN and basic info
strings /opt/een/var/bridge/bridge/*/bridge_service_status | head -1
```

### Determine Update Path

**Important:** Update host first if before 2022-03-01, otherwise do container first.

**Check if J1900 CPU (prone to random reboots):**
```bash
echo -n "CPU: "; echo `grep "model name" /proc/cpuinfo | head -1 | sed 's/^model name\s*:\s*//'`" ("`egrep ^processor /proc/cpuinfo | wc -l`" cores)"
```

**Check Governor (CPU scaling):**
```bash
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Set to performance (if needed)
for i in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
  echo "Before: $i"; cat $i
  echo 'performance' > $i
  echo "After: "; cat $i
done
```

**Governor Configuration by Model:**
- Default: ondemand
- 504p/524p: powersave with max_perf_pct=75
- 501/310/330/401/420/410/430/520/620/820: performance
- 403: powersave

---

## Container Management

### Docker Container Operations

**List Running Containers:**
```bash
docker ps
docker ps --format '{{.Names}}'

# Enter bridge container
docker exec -it bridge_bridge_1 /bin/bash

# Or dynamically find bridge container
docker exec -it $(docker ps --format '{{.Names}}' | grep -E 'bridge.bridge') /bin/bash
```

**Container Status & Logs:**
```bash
# Check container status
ipccli --list_containers
ipccli --get_container
ipccli --get_container --container=bridge

# View container logs
docker logs bridge_bridge_1
docker logs bridge_bridge_1 --tail 100 -f

# Supervisor logs (from within container)
supervisorctl logs
cat /var/log/supervisor/supervisord.log
```

**Restart Containers:**
```bash
# Restart bridge application
systemctl restart docker-compose@bridge

# Or restart all containers
systemctl stop run-all-containers
systemctl start run-all-containers

# Restart specific service (in container)
docker exec -it bridge_bridge_1 supervisorctl restart bridge
```

**Add/Remove Containers:**
```bash
# Add RTSP container
ipccli --add_container --container=bridge-rtsp-app --version=1.5.0 --url=$(cat /opt/een/etc/bridge/bridge.cluster).bridge.eencloud.com/bridge/bridge-rtsp-app

# Add LPR container
ipccli --add_container --container=ee-lpr-application-init --url=c000.bridge.eencloud.com/bridge/ee-lpr-application-init:2.0.0

# Add TalkDown container
ipccli --add_container --container=talkdown --version=1.15.0 --url=$(cat /opt/een/etc/bridge/bridge.cluster).bridge.eencloud.com/bridge/talkdown-client

# Add Zero-Reboot container
ipccli --add_container --container=zero-reboot --version=1.6.1-20250821 --url=c000.bridge.eencloud.com/bridge/zero-reboot

# Remove container
ipccli --remove_container --container=smokeping
ipccli --remove_container --container=ee-lpr-application-init
```

**Manual Container Pull Test:**
```bash
# Test if we can pull container image
docker pull $(cat /opt/een/etc/bridge/bridge.cluster).bridge.eencloud.com/bridge/bridge-guest:3.18.3

docker pull $(cat /opt/een/etc/bridge/bridge.cluster).bridge.eencloud.com/bridge/camera-support:v20231101

docker pull c014.bridge.eencloud.com/bridge/ee-lpr-application-init:1.6.0
```

**Clean Up Docker MEI Files (if containers won't start):**
```bash
cd /tmp && for i in *; do rm -rf $i | grep "_MEI"; done
```

---

## Health Monitoring & Diagnostics

### Bridge Health Checks

**Quick Health Check:**
```bash
# Bridge diagnostic (comprehensive)
bridge-diag
bridge-diag --long

# Bridge status
ipccli --bridge_status

# Health JSON
python -m json.tool /opt/een/var/log/bridge/health.json

# System status
systemctl status
```

**Check Reboots:**
```bash
# Recent reboots
last -x | less
last reboot | less

# Number of reboots in past 3 days
journalctl -x -S "3 days ago" | grep -c "-- Reboot --"

# Reboot logs with context
journalctl -x -S "3 days ago" | grep -v "List of devices attached" | grep -B15 -A5 "-- Reboot --"

# Check if power button was pressed
journalctl -x | grep 'Power key pressed.' -A10
```

**Memory Checks:**
```bash
# Basic memory info
free
head -n 5 /proc/meminfo
head -n 5 /proc/meminfo | egrep 'MemFree|MemAvailable'

# Memory usage by process
ps -eo rss,pid,user,command | sort -rn | head -$1 | awk '{ hr[1024**2]="GB"; hr[1024]="MB";
  for (x=1024**3; x>=1024; x/=1024) {
    if ($1>=x) { printf ("%-6.2f %s ", $1/x, hr[x]); break }
  }
} { printf ("%-6s %-10s ", $2, $3) } { for ( x=4 ; x<=NF ; x++ ) { printf ("%s ",$x) } print ("\n") }'
```

**Disk Space:**
```bash
# Overall disk usage
df -h
df -h /opt/een/data

# Bridge can see RAID
docker exec -it bridge_bridge_1 df -h /opt/een/data

# Storage by camera
cd /opt/een/data/bridge/assets && ls */*/*
cd /opt/een/data/bridge/assets; df -h .; du -sh $(ls) | sort --human-numeric-sort
```

**CPU & Performance:**
```bash
# CPU usage (live)
top
htop

# Advanced performance monitoring
atop
atop | grep avio

# Bandwidth monitoring
bmon -b
# Press 'd' for more info

# Temperature sensors
sensors
```

**USB Device Check:**
```bash
dmesg | grep -vE 'iptables|usb usb|hub hub|usb 2-1|hub 2-1|usb 1-2'
cat /proc/bus/input/devices/*/manufacturer
```

**Network Interface Status:**
```bash
# Check interfaces
ifconfig
ip addr

# Specific interface info
nmcli con show
nmcli dev show | grep 'IP4.DNS'

# Check negotiated port speeds
ethtool <wan0/camlan0/camlan1>
```

**Bridge Uptime & Load:**
```bash
uptime

# Detailed uptime check
echo -n "Uptime: "; uptime | awk '{$1=$1;print}'

# Check uptime from /proc
cat /proc/uptime
```

**GPU Hang Detection (for LPR/Analytics Issues):**
```bash
# Check for GPU hang messages (i915 driver)
dmesg | tail -100 | grep -i "gpu hang"

# Example output indicating GPU hang:
# [2339835.276735] i915 0000:00:02.0: [drm] anpr_detector[1530821] context reset due to GPU hang
# [2339835.284359] i915 0000:00:02.0: [drm] GPU HANG: ecode 11:1:8ed9fff3, in anpr_detector [1530821]

# Check dmesg for all GPU-related errors
dmesg | grep -i "i915\|gpu\|drm"

# If GPU hangs are detected, this can cause bridge crashes/reboots
# Resolution: Restart LPR container or update to newer version
```

---

## Certificate & Credential Management

### Camera Credentials

```bash
# View all camera credentials
cat /opt/een/var/bridge/security/credentials.js

# Download latest credentials file
SERVER=secure
if openssl x509 -noout -text -in /etc/pki/tls/certs/server-ca.pem | grep -q sha256WithRSAEncryption; then
  SERVER=secure2
  echo "---NEW CERTS"
fi

curl -vLsSfk -X GET --key "/etc/pki/tls/private/server-key.pem" --cert "/etc/pki/tls/certs/server.pem" "https://$SERVER.eagleeyenetworks.com/g/bridge_transfer?file=credentials.js" -o "/opt/een/var/bridge/security/credentials.js"
```

### Bridge Certificate Fixes

```bash
# Python cert fix script (from "The Box" or supportctl)
python3 fix_bridge_certs.py <ESN> <cluster>~<cookie>

# Example:
python3 fix_bridge_certs.py 100b5cad c001~53c7fe292568e321a776d2652a6bb3f7
```

### SSH Restart (for tunnel connectivity)

```bash
# From exec in EEN Admin
/usr/bin/ipccli --command --command='/bin/systemctl restart sshd.service'
```

### Custom Support Files

```bash
cat <guid>/configure/settings

# Example:
cat 39ade894-2df3-50b2-a205-58677f4790ec/configure/settings
```

---

# 2. Camera Operations

## Camera Discovery

### ONVIF Discovery

**Multicast Discovery (all interfaces):**
```bash
# From host
for i in $(ifconfig | grep -E -A1 'wan0|camlan' | grep inet | awk -F ' +' '{print $3}'); do
  python -m camdriver.discovery -a $i
done

# From container (specific interface)
python -m camdriver.discovery -a <interface_IP>

# Default camera discovery
python -m camdriver.onvif.broadcast
```

**Unicast Discovery (specific destination):**
```bash
# When using discovery with destination address
python -m camdriver.discovery -a <interface_IP> -d <camera_IP>
```

**Check DHCP Server on Network:**
```bash
nmap --script broadcast-dhcp-discover
nmap -sP -n 192.168.17.1/24
```

### Camera Detection on Network

**Nmap for All Cameras:**
```bash
# Quick scan for cameras
nmap -n -sP <ip_of_wan_or_camlan_subnet>

# Example for 10.143.x.x subnet
for i in $(arp -an | awk -F'[()]' '{print $2}' | head -100 | grep 10.143); do
  nmap -n -sP $i
done | grep -v "Starting"

# Scan specific camera ports
nmap -sT -sU -T25 -p 80,443,773,8081,8082,50000,60000 <camera_IP>
```

**Check ARP Table:**
```bash
# View ARP entries
arp -n | awk '{print $3}' | sort | uniq -c

# Better ARP (using nmap)
nmap -n -sP {NIC IP/CIDR}

# Check for IP conflicts
arping -I {NIC} -c {Number of Packets} {IP Address}
```

**Find Camera if MAC is Offline:**
```bash
cat /proc/net/arp
```

**Camera Not Showing in ARP:**
```bash
# Listen for traffic from camera
tcpdump -nni <interface> ether src <camera_mac>
```

---

## Camera Configuration

### ONVIF Configuration with oshell

**Factory Reset Camera:**
```bash
oshell -u <user> -p <password> <IP> -c 'print onvif.device.service.SetSystemFactoryDefault("Soft")'

# Example:
oshell -u admin -p 123456 10.143.118.122 -c 'print onvif.device.service.SetSystemFactoryDefault("Soft")'
```

**Get ONVIF Scopes:**
```bash
oshell -u admin -p 123456 10.143.118.122 -c 'print onvif.device.service.GetScopes()'
```

**Reboot Camera:**
```bash
oshell -u {user} -p '{pass}' {IP_Address} -c 'print onvif.device.service.SystemReboot()'
```

### Camera Settings via API

**Get Camera Timezone:**
```bash
curl -s "http://<ESN>.a.plumv.com:28080/camera/command?t=settings_get;c=<ESN>" | jq .user_settings.settings.timezone

# Or using clipboard:
curl -s "http://{{clipboard}}.a.plumv.com:28080/camera/command?t=settings_get;c={{clipboard}}" | jq .user_settings.settings.timezone
```

**Get Camera Time:**
```bash
curl "http://<ESN>.a.plumv.com:28080/camera/command?t=gettime;c=<ESN>"
```

**Set/Fix Camera Timezone:**
```bash
curl -s -X POST "http://<ESN>.a.plumv.com:28080/camera/command?t=settings_set;c=<ESN>" -d "timezone=US/Eastern" | jq .

# Example:
curl -s -X POST "http://100e6ef2.a.plumv.com:28080/camera/command?t=settings_set;c=100e6ef2" -d "timezone=US/Eastern" | jq .
```

### Stream Configuration

**View Stream Info:**
```bash
# Check stream_info.json
cd /opt/een/var/bridge/cameras/<GUID>
python -m json.tool stream_info.json

# Check what streams are set to
for i in $(cd /opt/een/var/bridge/esns; for i in */camera_service_status; do
  echo -n "$i: "; strings $i | head -2 | tail -1
done | awk -F'[/:]' '{print $1 $3}' | awk -F ' +' '{print $2}'); do
  python -m json.tool /opt/een/var/bridge/cameras/$i/stream_info.json | grep -E "width|height" | tr "\n" " "
  echo
done | sort | uniq -c
```

**Test Camera Stream with ffprobe:**
```bash
# Basic ffprobe
ffprobe "rtsp://<user>:<password>@<IP>:554/<stream_path>"

# With verbose debug
ffprobe -rtsp_transport tcp -loglevel repeat+level+verbose -v debug "rtsp://<user>:<Password>@<IP Address>/url"

# Example:
ffprobe "rtsp://ovcloudadmin:4611224730@10.143.151.74:554/snl/live/1/1"

# Variables method
user="onvif"
pass="onvif"
IP="10.143.32.210"
streamURL="/profile1"
ffprobe -rtsp_transport tcp -loglevel repeat+level+verbose -v debug "rtsp://${user}:${pass}@${IP}:9008${streamURL}"
```

**Play Video from Camera:**
```bash
ffplay rtsp://<user>:<password>@<bridge_ip_address>:8554/

# Example:
ffplay rtsp://jbutts+test1@een.com:O6gV3Jyc9LmpnzxZ5xklUvsnVd4=@10.100.8.149:8554/
```

### Camera Retention Settings

```bash
# Check camera retention settings
for i in /opt/een/var/bridge/esns/*/settings; do
  echo $i | awk -F/ '{print $7}'
  python -m json.tool $i | grep -iE 'bridge|reten' | sort
done

# Check purge status
python -m json.tool /opt/een/var/log/bridge/purge.json

# ZMQ retention settings
python3 ./getSettings.py -e <ESN> | grep -E -A 3 "retention|target|purge" | jq '.. | objects | select(has("retention") or has("purge") or has("target"))'
```

### Real-time Preview Monitoring (Websocket)

**Websocket polling for live previews:**
```bash
# Access websocket polling interface
http://100fb653.a.plumv.com:28080/ws_poll3.html

# Payload to monitor camera events and images:
{ "cameras": { "100fb653": { "resource" : [ "event","image"] }}}

# This allows real-time monitoring of:
# - Preview image generation
# - Event generation
# - Camera connection status
```

---

## Firmware Updates

### Mstar/Novatec Camera Firmware

**Upload Firmware File to Bridge:**
```bash
# From your computer (before connecting to bridge)
supportctl connect <ESN> --put ~<FILE_LOCATION_ON_COMPUTER> --target <LOCATION_ON_BRIDGE>

# Example:
./supportctl connect <ESN> --put /Users/user/mstar/v3.6.1303.1004.88.1.8.2.5_20240130 --target /opt/een/data/v3.6.1303.1004.88.1.8.2.5_20240130
```

**Identify Mstar Cameras:**
```bash
# Script to find and categorize Mstar cameras
s=$(cd /opt/een/var/bridge/cameras; cat */device_config | strings | grep EN\-....\-...\-2 -A2 | grep '\-001c' -c)
a=$(cd /opt/een/var/bridge/esns; for i in */camera_service_status; do
  echo -n "$i: "; strings $i | head -2 | tail -1
done | awk -F'[/:]' '{print $1 $3}' | grep -cE "$(cat /opt/een/var/bridge/cameras/*/device_config | strings | grep EN\-....\-...\-2 -A2 | grep '\-001c' | tr '\n' ' '| tr ' ' '|' | sed 's/.$//')")
d=$(($s-$a))

echo -e "\nThe amount of MSTAR camera GUIDs seen: \t\t\t$s"
echo -e "How many MSTAR cameras that are attached: \t\t$a"
echo -e "Differential of seen vs attached (seen - attached): \t$d\n"
```

**Upgrade Mstar Cameras:**
```bash
# In container - upgrade attached cameras
for i in $(cd /opt/een/var/bridge/cameras; cat */device_config | strings | grep EN\-....\-...\-2 -A2 | grep '\-001c'); do
  echo -e "screen -d -m python -m camdriver.onvif.sunell -a $(cat /opt/een/var/bridge/cameras/$i/last_address | grep -v 169.254. | awk -F/ '{print $3}') -u admin -p $(cat /opt/een/var/bridge/security/credentials.js | grep $i -A8 | grep -v ovcloud | grep admin -A1 | tail -1 | awk -F '\"' '{print $2}') -f /opt/een/data/v3.6.1303.1004.88.1.8.2.5_20240130"
done | bash
```

### Nova4MP Camera Firmware

```bash
# Similar process as Mstar but with Nova4MP firmware files
# Check firmware version format: v3.6.1602.x.x.x

# Upload firmware to bridge
supportctl connect 100c9a3c --put ~/NOVA4MP/v3.6.1602.1006.88.1.18.6.11.D03_20240508 --target /opt/een/data/v3.6.1602.1006.88.1.18.6.11.D03_20240508

# Update specific camera, must be in container
python -m camdriver.onvif.sunell -a 10.143.194.32 -u admin -p 9953929376 -f /opt/een/data/v3.6.1603.1006.88.1.18.20.5.D01_20240521
```

### Camera Model Detection

```bash
# Find attached camera models
cd /opt/een/var/bridge/cameras
for i in */last_match; do
  echo -n "$i: "; strings $i | head -1
done | awk -F '/last_match' '{ print $1 $2}' | awk -F ' +' '{print $3}' | sort | uniq -c | sort -hr
```

### Hikvision Specific

**Important:** Don't downgrade Hikvision cameras (ours or customer's).

**Common Settings:**
- Username/password should be same (unlike Axis)
- Enable control compression in video profile for motion box issues

**HTML/XML error (ONVIF config):**
- Make sure ONVIF user is the same as the admin username/password, and the ONVIF user is also an administrator
- Time must be accurate
- RTSP authentication is either Digest or off
- Illegal login lock is not enabled
- Change ONVIF to WS-Token

---

## Camera Status Troubleshooting

### Camera Tool Status Codes

**Status Values:**
- **STRM** = Streaming (working correctly)
- **PEND** = Pending - driver is built, waiting for user to add camera
- **HOLD** = Did not match a driver, need to build driver
- **NONE** = Need password or could not find driver
- **PASS** = Password required
- **CONF** = In ONVIF configuration state machine
- **CERR** = Configuration Error
- **ERR** = Camera in error state, check username/password, firmware, connection
- **FOND** = Ask Jeff about camera IP
- **COFF** = Camera Off
- **NSIG** = Analog camera

### Check Camera Status in Bridge Logs

```bash
# Follow bridge log for specific camera
tail -F /opt/een/var/log/bridge/bridge.log | grep -iE '{CAM_ESN}|{CAM_GUID}'
tail -F /opt/een/var/log/bridge/bridge.log | grep -iE '{Cam ESN}'

# Check for specific issues
tail -F /opt/een/var/log/bridge/bridge.log | grep -iE 'curl|route|direct control'

# Stream and camera script logs
tail -F /opt/een/var/log/bridge/bridge.log | grep -iE '{CAM_ESN}' | grep -E 'streammng|camscript|camera.c:|onvif2.c:|settings.c:|streams/'

# Both bridge and streamer logs
tail -F /opt/een/var/log/bridge/bridge.log /opt/een/var/log/bridge/streamer.log | grep -iE '<IP>|<GUID>'
```

### Camera Showing Offline (Wrong Status)

**From Customer Impact Runbook (EENS-133087, EEPD-95638):**

1. **Check etag sync status:**
```bash
# Initiate full etag sync in Nexus for the camera
# Check if etags are in sync
```

2. **Verify camera connectivity:**
```bash
# Check if camera is actually accessible
ping <camera_IP>

# Verify network connectivity
# Check bridge connection if applicable
```

3. **Review camera history:**
```bash
# After etag sync completes, check if history reports correctly
# Look for timestamp inconsistencies
```

### Camera Preview Freezing

**From Customer Impact Runbook (EEPD-103382):**

1. **Check network configuration:**
```bash
# Verify VLAN settings (ensure camera is on correct VLAN)
# Check for mixed VLAN configurations on switches
# Verify CamLan VLAN separation
```

2. **Check cabling:**
```bash
# Verify physical network connections
# Look for cable issues between camera and switch
```

3. **Review bandwidth:**
```bash
# Check network saturation
# Verify PoE power delivery
```

### Camera Dropping Packets

```bash
# Which camera IPs are dropping packets in Stream logs
grep "dropped: " <ESN_archiver>_stream.log | awk -F"[ @]" '{if ($0 ~ /dropped: [1-9][0-9]*/) print $6}' | awk -F":" '{print $1}' | sort -u

# Example:
grep "dropped: " 1001d971.a2611_bridge.log | awk -F"[ @]" '{if ($0 ~ /dropped: [1-9][0-9]*/) print $6}' | awk -F":" '{print $1}' | sort -u
```

### Low Uptime Logs

```bash
# Looking for low Uptime logs in stream logs
grep "Uptime :0.0" <ESN_archiver>_stream.log | awk -F'@|/' '{print $2}' | sort | uniq

# More comprehensive check
grep -E "Uptime\s*:[0-9.]+e-[0-9]+" <ESN_archiver>_stream.log | grep -oP '@\K[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | sort -u
```

---

## GUID Management

### Find Camera GUIDs

```bash
# List all attached GUIDs with their ESNs
cd /opt/een/var/bridge/esns
for i in */camera_service_status; do
  echo -n "$i: "; strings $i | head -2 | tail -1
done | awk -F'[/:]' '{ print $1 $3}'

# Find IPs of each GUID
cd /opt/een/var/bridge/cameras
for i in */last_address; do
  echo -n "$i: "; strings "$i" | grep -v 169.254 | head -1
done | awk -F'/last_address' '{print $1 $2}'
```

### Check Number of GUIDs

```bash
# In camera directory
cd /opt/een/var/bridge/cameras
ls | wc -l

# Watch it live
watch "ls | wc -l"
```

### Delete Duplicate/Unattached GUIDs

**⚠️ BE CAREFUL WITH THIS!**

```bash
# Step 1: Create list of attached camera GUIDs
cd /opt/een/var/bridge/esns
for i in */camera_service_status; do
  echo -n "$i: "; strings $i | head -2 | tail -1
done | awk -F'[/:]' '{print $3}' | awk -F' +' '{print $2"|"}' > /rmgtest

cat /rmgtest

# Step 2: Delete unattached GUIDs from cameras directory
cd /opt/een/var/bridge/cameras
shopt -s extglob
for i in $(ls | grep -vE "$(cat /rmgtest | tr -d '[:space:]' | sed 's/.$/')"); do
  rm -rf $i
done
```

### GUID File Structure

Important files in `/opt/een/var/bridge/cameras/<GUID>/`:
- **last_port** - Port of Eagle Eye Switch that the camera was plugged into
- **last_address** - Last known IP address the camera was seen at
- **last_match** - Type of camera that Bridge recognized it as
- **last_config** - Type of camera and firmware
- **stream_info.json** - The RTSP Stream information of the camera
- **driver_script.out** - Driver information and resolution details
- **device_config** - Camera device configuration

### Create GUID for Offline Managed Switch Camera

```bash
# Get GUID from unicast discovery and edit last_address
echo "http://10.100.10.166/onvif/device_service" > last_address
```

---

# 3. Network & Connectivity

## Interface Management

### Check Network Interfaces

```bash
# View all interfaces
ifconfig
ip addr

# Show specific interface config
nmcli con show
nmcli dev show

# Get DNS settings (host)
nmcli dev show | grep 'IP4.DNS'

# Get DNS settings (container)
cat /etc/resolv.conf
```

### Bring Interfaces Up/Down

```bash
# Bring up camlan0
nmcli con up camlan0

# Bring down interface
nmcli con down <interface>

# Check connection status
nmcli con show
```

### Create "Brick" IP (Temporary IP Assignment)

```bash
# Add brick to camlan0
ifconfig camlan0:brick 192.168.1.1

# With netmask
ifconfig camlan0:brick 192.168.1.1 netmask 255.255.0.0

# Add brick to wan0
ifconfig wan0:brick 10.61.120.20 netmask 255.255.255.0

# Remove brick when done
ifconfig camlan0:brick down
ifconfig wan0:brick down
```

### Turn Off NTP on Bridge

```bash
dnf -y remove chrony
```

---

## Network Diagnostics

### Basic Connectivity Tests

```bash
# Test internet connectivity
dig example.com

# Ping specific host
ping -c <number_of_packets> <IP>

# Ping all IPs in range with 50 packets
for ip in $(arp -an | awk '/10.143./ {print $2}' | tr -d '()'); do
  ping -c 50 $ip
done
```

### Network Diagnostics Tool

```bash
# Run comprehensive network diagnostics (in host)
netdiag
```

### Check WAN/CamLan Interconnectivity

**Requires two tunnels:**

```bash
# First tunnel - send ARP request
arping -I wan0 10.143.0.1

# Second tunnel - listen for response
tcpdump -ni camlan0 arp dst 10.143.0.1
```

### MTR (Network Path Analysis)

```bash
# Basic MTR
mtr <IP>

# MTR with specific port
mtr <bridge_archiver_IP> -rbz -T -P <port#>
```

### Fping Tests

**Install fping:**
```bash
yum install fping -y
```

**Test all cameras:**
```bash
# Create list of camera IPs
cd /opt/een/var/bridge/cameras
for i in */last_address; do
  echo -n "$i: "; strings $i | head -1
done | awk -F '/last_address' '{print $1 $2}' | awk -F '/' '{print $3}' > /test

cat /test

# Run fping test
fping -c 100 -p 500 -f /test

# Or one-liner:
yum install fping -y; cd /opt/een/var/bridge/cameras; for i in */last_address; do
  echo -n "$i: "; strings $i | head -1
done | awk -F '/last_address' '{print $1 $2}' | awk -F '/' '{print $3}' > /test; fping -c 100 -p 500 -f /test
```

**Ping all ARP table:**
```bash
nping -c 4 $(arp -n | awk '{print $1}' | grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}')

# Just camlan
nping -c 4 $(arp -n | grep camlan0 | awk '{print $1}' | grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}')

# Ping all IPs in range
fping -g {IP/CIDR}
```

### Bandwidth Monitoring

```bash
# Real-time bandwidth monitoring
bmon -b
# Press 'd' for detailed stats

# Interface traffic
iftop

# Network load
nload
```

---

## DNS & DHCP

### DNS Configuration

```bash
# Check DNS servers (host)
nmcli dev show | grep 'IP4.DNS'

# Check DNS config (container)
cat /etc/resolv.conf

# Add nameserver
echo 'nameserver 172.16.150.1' >> /etc/resolv.conf

# Add rotate option
options rotate /etc/resolv.conf
```

### DHCP Discovery

```bash
# Check for DHCP server
nmap --script broadcast-dhcp-discover

# Check DHCP pool
nmap -sP -n 192.168.17.1/24

# Check DHCP lease time (on bridge)
cat /etc/dnsmasq.d/camlan0.conf
```

### Check for Webfilter

```bash
curl http://repo.plumv.com/repo/een/6/x86_64/repodata/repomd.xml -o repomd.xml -vvv
```

---

## Firewall Testing

### Port Scanning

```bash
# Scan camera for open ports
nmap -sT -sU -T25 -p 80,443,773,8081,8082,50000,60000 <camera_IP>

# Filter out expected open ports
nmap -sT -sU -T25 -p 80,443,773,8081,8082,50000,60000 <IP> | grep -ivE '80/u|443/u|773/u|8081/u|8082/t|50000/u|60000/u'

# Check archiver connectivity
nmap -sT -sU -T25 -p 80,443,773,8081,8082,50000,60000 {Archiver_IP}
```

### Netcat Connection Tests

```bash
# Check if port is open
nc -vz {IP_Address} {Port}

# Example checking specific archiver ports
for port in 80 443 773 8080 8081 8082 50000 60000; do
  nc -vz ${archiver_IP} ${port}
done
```

### Netstat Connection Analysis

```bash
# View all connections
netstat -ant

# Filter for SYN/FIN (connection issues)
netstat -ant | egrep 'SYN|FIN'
```

### Traceroute with Port

```bash
# Curl to check connectivity
curl -v http://$(cat /opt/een/etc/bridge/bridge.cluster).bridge.eencloud.com/
```

### Check Archiver Connections

**Simple version (without netcat):**
```bash
for esn in $(ls /opt/een/var/bridge/esns); do
  echo -e "Testing connections for ${esn}"
  echo -e "\tTesting connection to Archivers: "
  for IP in $(dig ${esn}.a.plumv.com | grep $esn | awk -F' +' '{print$1}' | xargs -n 1 | egrep '[[:digit:]]{1,3}\.[[:digit:]]{1,3}\.[[:digit:]]{1,3}\.[[:digit:]]{1,3}'); do
    echo -e "\t\tArchiver ${IP}"
    echo
  done
  echo
done
```

**With netcat test:**
```bash
for esn in $(ls /opt/een/var/bridge/esns); do
  echo -e "Testing connections for ${esn}"
  echo -e "\tTesting connection to Archivers: "
  for IP in $(dig ${esn}.a.plumv.com | grep $esn | awk -F' +' '{print$1}' | xargs -n 1 | egrep '[[:digit:]]{1,3}\.[[:digit:]]{1,3}\.[[:digit:]]{1,3}\.[[:digit:]]{1,3}'); do
    echo -e "\t\tArchiver ${IP}"
    for port in 80 443 773 8080 8081 8082 50000 60000; do
      nc -vz ${IP} ${port}
    done
    echo
  done
  echo
done
```

### Check Transport Connectivity

```bash
# Check archiver connectivity from bridge
ipccli --get_transports
```

---

## Switch Management

### Find Switches

**From host:**
```bash
docker exec -it bridge_bridge_1 python -m camdriver.eenswitch -dmi
```

**From container:**
```bash
python -m camdriver.eenswitch -dmi

# With specific search
python -m camdriver.eenswitch -d
```

**Switch Logs:**
```bash
journalctl -S "1 hour ago" -u een-ipc | grep switch
```

### LLDP (Link Layer Discovery Protocol)

```bash
# Install LLDP
yum install lldpd

# Check LLDP info
lldpctl
```

### Switch Configuration Notes

- MAC address starting with **38:73** is always an Eagle Eye switch
- 305 ports are installed backwards - check opposite port!

---

# 4. Storage & RAID

## RAID Diagnostics

### Check RAID Status

```bash
# View RAID status
cat /proc/mdstat

# Detailed RAID information
mdadm -D /dev/md127
mdadm --detail /dev/md127

# Check RAID array state
cat /sys/block/md127/md/array_state
```

### Check RAID Mount

```bash
# Verify RAID is mounted
findmnt /opt/een/data
# Must say: /opt/een/data /dev/md127

# Check if container can see RAID
docker exec -it bridge_bridge_1 df -h /opt/een/data
```

### RAID Speed Settings

```bash
# Check RAID speed limits
sysctl -a | grep raid

# Fix if speed limit is too low
sysctl -w dev.raid.speed_limit_max=65000

# Remove cron check (if present)
rm -f /etc/cron.d/raid-check
```

### Check Physical Disks

```bash
# List physical disks
cat /proc/mdstat
echo ""
echo "Number of DISKs: $(fdisk -l | grep -c /dev/sd)"
fdisk -l | grep /dev/sd

# Disk identifiers
ls -lF /dev/disk/by-id/
```

---

## Disk Health Monitoring

### SMART Tests

```bash
# Check single disk
smartctl -a /dev/<DISKNAME>

# Check all disks
for i in /dev/sd?; do smartctl -a $i; done

# Get Model, Serial, Capacity
for i in /dev/sd?; do
  echo $i:
  smartctl -a $i | egrep '(Model|Serial|Capacity)'
done

# Check serial numbers of all disks
for i in /dev/sd?; do
  echo $i:
  smartctl -a $i | egrep '(Model|Serial|Capacity)'
done
```

### Health Check Logs

```bash
# Disk health logs
journalctl -u smartd --no-pager

# RAID health logs
journalctl -u een-raid --no-pager
```

---

## Filesystem Operations

### ⚠️ CRITICAL WARNINGS

**DO NOT ATTEMPT FSCK ON MOUNTED RAID!!!**

**Filesystem check is running = DO NOT STOP RAID**

**md127 is running = DON'T STOP THE RAID**

### RAID Filesystem Check

**ONLY run when RAID is UNMOUNTED:**

```bash
# Verify integrity of RAID (remove 'p' option if you receive error)
# CAN TAKE LONG TIME
fsck -Cfvr /dev/<RAIDNAME>

# Common options:
# -C = Show progress bar
# -p = Automatically repair (careful!)
# -f = Force check even if filesystem seems clean
# -v = Verbose
# -r = Interactive repair

# For ext2/3/4 filesystems:
e2fsck -y /dev/md127           # Answer yes to non-destructive questions
e2fsck -fy /dev/md127          # Force full check
```

**For f2fs (Platform 2 SSDs):**
```bash
fsck.f2fs /dev/nvme0n1p4
```

---

## Storage Management

### RAID Recovery Procedures

**⚠️ ONLY FOLLOW THESE STEPS IF YOU KNOW WHAT YOU'RE DOING!**

**Full RAID Recovery Process:**

1. **Stop RAID:**
```bash
mdadm -S /dev/md127
```

2. **Start RAID (Automatic):**
```bash
mdadm --assemble --scan --verbose --force
```

3. **Start RAID (Manual - using specific disks):**
```bash
mdadm --assemble --run --force --verbose /dev/md127 /dev/sda /dev/sdb /dev/sdc /dev/sdd /dev/sde /dev/sdf /dev/sdg /dev/sdh /dev/sdi /dev/sdj
```

4. **Add Disks Back to Array:**

Try re-add first:
```bash
# Re-add single disk
mdadm --re-add /dev/md127 /dev/<DISKNAME>

# Re-add all disks
for i in /dev/sd?; do mdadm --re-add /dev/md127 $i; done
```

If re-add fails, try add:
```bash
# Add single disk
mdadm --add /dev/md127 /dev/<DISKNAME>

# Add all disks
for i in /dev/sd?; do mdadm --add /dev/md127 $i; done
```

**Important:** Don't add faulty device to the raid array!

5. **Bring RAID Online:**
```bash
fsck -y /dev/md127
mkdir /raid
mount /dev/md127 /raid
```

6. **Sync Data to RAID (3 times):**
```bash
for i in {1..3}; do rsync -auv /opt/een/data/ /raid/; done
```

7. **Stop Processes Using /opt/een/data:**
```bash
# Turn off Container WatchDog
systemctl stop critical-service-health.timer

# Turn off Containers
systemctl stop run-all-containers

# Verify bridge app is not running
docker ps
```

8. **Final Data Sync:**
```bash
rsync -auv /opt/een/data/ /raid/

# Verify /opt/een/data is bigger
df -h /opt/een/data/
```

9. **Bind Mount and Restart:**
```bash
# Bind mount
mount --bind /raid/ /opt/een/data/

# Wait
sleep 5

# Restart containers
systemctl start run-all-containers
systemctl start critical-service-health.timer

# Wait
sleep 5

# Restart IPC
systemctl restart een-ipc

# Verify containers are running
docker ps

# Verify RAID is in use
docker exec -it bridge_bridge_1 df -h /opt/een/data
```

### Check if Filesystem Check is Running

If you see "Filesystem check is running" - the RAID is automatically repairing itself. **DO NOT STOP IT!**

### RAID Monitoring During Rebuild

If disk shows up as **spare**, it is most likely rebuilding the raid. If stuck as spare device, reboot after a day or two.

### Multiple RAID Systems (Old Bridges)

Some old bridges have:
- `/opt/een/data` on md127
- NVME partition on md126

Check both with:
```bash
cat /proc/mdstat
findmnt | grep md
```

### Data Movement Between Bridges

See **Section 11 - Emergency Procedures** for brain swap / data migration procedures.

---

# 5. Video & Footage Operations

## Download Procedures

### Video Download URLs

**Direct Download via Login Domain:**
```bash
# MP4 format
https://login.eagleeyenetworks.com/asset/play/video.mp4?id=<ESN>&start_timestamp=<YYYYMMDDHHMMSS.sss>&end_timestamp=<YYYYMMDDHHMMSS.sss>&a=<AUTH_KEY>

# FLV format (with UTC timestamps)
https://login.eagleeyenetworks.com/asset/play/video.flv?id=<ESN>&start_timestamp=<YYYYMMDDHHMMSS.sss>&end_timestamp=<YYYYMMDDHHMMSS.sss>&a=<AUTH_KEY>
```

**Archiver Direct Download:**
```bash
# Direct from archiver (port 28080) - FLV with coalesce
http://{archiver}.eagleeyenetworks.com:28080/asset/play/video.flv?id={esn}&start_timestamp={start}&end_timestamp={end}&options=coalesce

# Manual timestamp review (video.html)
http://{archiver}.eagleeyenetworks.com:28080/video.html?c={esn}

# Download with OSD timestamps (On-Screen Display with timezone)
https://login.eagleeyenetworks.com/asset/play/video.flv?id=<camera_ESN>&start_timestamp=<start_time_UTC>&end_timestamp=<end_time_UTC>&osd=<timezone>

# Timestamp format examples:
# start: 20250424103400.000
# end: 20250424103700.000
# timezone: America/New_York, UTC, etc.
```

**V3 WebApp Downloads:**
```bash
# After logging in
https://webapp.eagleeyenetworks.com
```

### Download Status Checking

**Check download task:**
```bash
# In Debug Mode (Ctrl+Alt), check uinotification for task ID
# Track download progress via task ID
```

---

## Footage Verification

### Check Video Availability

**Verify footage exists:**
```bash
# Check retention period
# Confirm recording was active during timeframe

# Check storage on bridge
cd /opt/een/data/bridge/assets
ls */*/*/

# Check if specific ESN has footage
ls -la */<ESN>/*
```

### Cloud vs Archiver Storage

**Check if footage is in the cloud:**
```bash
# Use video.html to verify footage in cloud
http://<esn>.a.plumv.com:28080/video.html?c=<esn>

# With specific timestamp and count
http://1001f32f.a.plumv.com:28080/video.html?c=1001f32f&t=20250912120642.898&count=-5

# This will show you if footage is available in cloud storage
# If you can see video playback, footage is in the cloud
```

**Check which archivers are being used:**
```bash
# From bridge - check transports to archivers
ipccli --get_transports

# DNS lookup to see which archivers ESN is using
dig <ESN>.a.plumv.com

# Example:
dig 100b213b.a.plumv.com
```

### Check for Video Gaps

**From Customer Impact Runbook (EEPD-102531):**

1. Check recording status during gap
2. Verify camera was online
3. Check for bridge connectivity issues
4. Review event generation
5. Check for system maintenance or cluster issues during timeframe

---

## Archiver Management

### Etag Sync

**Initiate full etag sync (from Nexus):**
```bash
# For specific camera - initiate in Nexus interface
# Wait for sync completion
# Verify etags are in sync between systems
# Re-check video history after sync completes
```

### Check Archiver Connectivity

**See "Cloud vs Archiver Storage" section above for:**
- `ipccli --get_transports` - Check bridge transports to archivers
- `dig <ESN>.a.plumv.com` - DNS lookup for archiver assignment

### Archiver Health Check

```bash
http://dproxy.test.eencloud.com/api/v2/dhash/node/v2/com.eencloud.dhash.esn:<esn>:archiver/health

# Example:
http://dproxy.test.eencloud.com/api/v2/dhash/node/v2/com.eencloud.dhash.esn:10098d23:archiver/health
```

### Data Disparity Between Archivers

If data on each archiver is not the same:
1. Run full etag sync first and let it finish
2. Run "Sync Media" on each archiver, one at a time (lowest first)
3. Run "Do Command" on each archiver

### Direct Archiver Filesystem Access (Jason Commands)

**Access archiver node directly via kubectl:**
```bash
# SSH into archiver node
kubectl node-shell a3205 --context lon1p1

# Navigate to archiver asset storage
cd /srv/archiver/var/lib/assets/100fdb20/a

# Check etag synchronization between archivers
ls | grep ".etag" | wc -l

# View footage files for specific date
cd /srv/archiver/var/lib/assets/100eb59a/a/2025/08/24
ls -lh | grep -v "etag"
ls -lh
```

**Find archiver pod by name or IP:**
```bash
# Find archiver by name
kubectl get pods --all-namespaces -o wide | grep [archiver_name]
kubectl get pods --all-namespaces -o wide | grep a1514 | grep archiver

# Find archiver by IP
kubectl get pods -n default -o wide | grep "136.242.84.32"
```

**Get archiver logs:**
```bash
# Get archiver pod name
kubectl get pods --all-namespaces | grep archiver | grep [archiver_name]

# Example: archiver-pxwv6
kubectl cp archiver-pxwv6:/opt/een/var/log/archiver/base/archiver.log ~/Archiver_Logs/a3495.log

# Search logs
cat ~/Archiver_logs/a3495.log | grep [search_term]
cat ~/Archiver_logs/a3495.log | grep 1002ed35
```

### FLV File Corruption Detection

**Check for corrupt FLV files:**
```bash
# Hexdump first 50 lines to check FLV header
hexdump -c 20251004130211.984_h264_high_p0_EVENT.flv | head -50

# Check if valid FLV file (should see 'FLV' tag in white in first 5 characters)
# Use vim to inspect: vim [filename.flv]
# Look for 'flv' in white within first five characters

# Grep for FLV tags in file
grep FLV 20251201143742.000_h264_high.flv
# Expected output: binary file matches (if valid FLV)
```

---

## Stream Testing

### RTSP Stream Testing

```bash
# Basic stream test
ffprobe "rtsp://<user>:<password>@<IP>:554/<stream_path>"

# Verbose debug
ffprobe -rtsp_transport tcp -loglevel repeat+level+verbose -v debug "rtsp://<user>:<password>@<IP>/<url>"

# Count frames
ffmpeg -i "rtsp://<user>:<password>@<IP>:554/<stream>" -vframes 1 -f null -
```

### Check Camera Stream Info

```bash
# View stream_info.json
cd /opt/een/var/bridge/cameras/<GUID>
python -m json.tool stream_info.json | grep -E "width|height"

# Or driver_script.out (faster)
cat driver_script.out | grep -E "width|height"
```

### Play Live Preview

```bash
ffplay rtsp://<user>:<password>@<bridge_ip>:8554/
```

---

# 6. System Diagnostics & Logs

## Log Analysis

### Bridge Application Logs

```bash
# Tail bridge log
tail -f /opt/een/var/log/bridge/bridge.log

# Follow specific camera/ESN
tail -F /opt/een/var/log/bridge/bridge.log | grep -iE '{CAM_ESN}|{CAM_GUID}'

# Follow route/curl/direct control
tail -F /opt/een/var/log/bridge/bridge.log | grep -iE 'curl|route|direct control|direct fail'

# Follow bridge log (in box/host)
followbridgelog
followfire
```

### System Logs (journalctl)

```bash
# View logs since specific time
journalctl --since="YYYY-MM-DD HH:MM:SS" --until="YYYY-MM-DD HH:MM:SS"

# Recent journal entries
journalctl -S "3 days ago"
journalctl -S "yesterday"
journalctl -S today | grep wan0

# Show errors only
journalctl -p err -b -o short-precise --no-pager

# Specific service logs
journalctl -u NetworkManager --no-pager
journalctl -u een-ipc --no-pager
journalctl -u systemd | grep een-ipc

# Check for blocked tasks
journalctl | grep "blocked for more than"

# Filter out noise
journalctl -x | grep -vE "Plugin:|Parent monitoring|Dispatching|Hash|activationCode|[0-9] Start"
```

### Upgrade History

```bash
# Check for upgrades/updates
journalctl -x | grep -vE "Plugin:|Parent monitoring|Dispatching|Hash|activationCode|[0-9] Start" | grep -E upgrade

# Check boot image history
cat /var/log/earlyboot.txt

# Container upgrade logs
journalctl -x | grep -vE "Plugin:|Parent monitoring|Dispatching|Hash|activationCode|[0-9] Start" | grep -E upgrade
```

### Platform Upgrader Logs

```bash
# View upgrade log
cat /var/log/platform-upgrader.log

# Check for errors
cat /var/log/platform-upgrader.log | grep -i error | tail-50

# Check for 400 errors (cert issues)
cat /var/log/platform-upgrader.log | grep 400

# Get specific command errors
grep command /opt/een/var/log/bridge/bridge.log
```

### Docker Container Logs

```bash
# View container logs
docker logs bridge_bridge_1
docker logs bridge_bridge_1 --tail 100 -f

# With timestamps (time-filtered logs)
docker logs --since="2024-01-01T00:00:00" --until="2024-01-02T00:00:00" bridge_bridge_1

# Time-bounded log extraction (specific time window)
sudo docker logs bridge-bridge-1 --since "2025-12-22T11:00:00" --until "2025-12-22T11:30:00"
```

### Listener Log (ONVIF)

```bash
cat /opt/een/var/log/bridge/listener/listener.log
```

### Boot Logs

```bash
# Current boot
dmesg

# With timestamps
dmesg -T

# Errors only
dmesg -T --level=emerg,alert,crit,err,warn

# Check for specific errors
dmesg | grep DRDY
dmesg | grep FIFO
dmesg | grep bridge
dmesg -T | grep FIFO

# Boot log files
cat /var/log/boot.log*
zless /var/log/messages*.gz
zgrep kernel /var/log/messages*
```

---

## Kernel Debugging

### Check for Kernel Panics

```bash
# Kernel panic logs
journalctl -k | grep -i "error\|fail\|panic"

# Check dmesg for critical issues
tail -n 20 /var/log/dmesg
dmesg -T --level=emerg,alert,crit,err,warn
```

### Core Dumps

**List core dumps:**
```bash
coredumpctl --no-pager
```

**Analyze core dump:**
```bash
# Get corefile name
cd /cores && ls *PIDNUMBER*

# Enter bridge container
docker exec -it bridge_bridge_1 /bin/bash

# Change to cores directory
cd /opt/een/data/cores

# Decompress the core
lz4cat core.bridge.0.231ecc57b4484e8dab50afd9903a67ae.1680242.1667148631000000.lz4 > core.bridge.0.231ecc57b4484e8dab50afd9903a67ae.1680242.1667148631000000

# Use gdb to get backtrace
gdb /opt/een/bin/bridge core.bridge.0.231ecc57b4484e8dab50afd9903a67ae.1680242.1667148631000000

# In gdb:
bt              # Backtrace
bt full         # Full backtrace
frame #         # Jump to frame
print *mux      # Print variable
```

**Reading crash dumps:**
```bash
# Decompress
lz4 -d {coredump}

# Analyze with gdb
gdb /opt/een/bin/bridge {coredump}
# Then use 'bt' for backtrace
```

### Kernel Crash Logs

```bash
ls -l /var/crash
# Check file path, then ls -l the new path
```

### Machine Check Errors

```bash
zgrep --binary-files=text 'Machine check' /var/log/messages*
```

### Check for Hardware Errors

```bash
# Check for DRDY errors
dmesg | grep DRDY

# Check for analog errors
dmesg -T | grep FIFO

# AVIO (disk I/O issues)
atop | grep avio
```

---

## Performance Monitoring

### CPU Monitoring

```bash
# Real-time CPU usage
top
htop

# Check CPU model and cores
grep "model name" /proc/cpuinfo | head -1
egrep ^processor /proc/cpuinfo | wc -l
```

### Memory Monitoring

```bash
# Basic memory info
free
head -n 5 /proc/meminfo

# Memory usage by process (formatted)
ps -eo rss,pid,user,command | sort -rn | head -20 | awk '{
  hr[1024**2]="GB"; hr[1024]="MB";
  for (x=1024**3; x>=1024; x/=1024) {
    if ($1>=x) { printf ("%-6.2f %s ", $1/x, hr[x]); break }
  }
} { printf ("%-6s %-10s ", $2, $3) } { for ( x=4 ; x<=NF ; x++ ) { printf ("%s ",$x) } print ("\n") }'
```

### Disk I/O Monitoring

```bash
# Advanced top with disk I/O
atop
atop | grep avio
```

### Network Bandwidth

```bash
# Real-time bandwidth
bmon -b
# Press 'd' for detailed stats

# Interface statistics
iftop
nload
```

### Temperature

```bash
sensors
```

---

## Error Tracking

### Common Error Patterns

**Bridge SIGKILL check:**
```bash
journalctl -xS "3 days ago" | grep bridge_1 | grep -v reaped | egrep "bridge|waiting|SIGKILL|SIGHUP"
```

**OOM (Out of Memory) check:**
```bash
journalctl --dmesg --no-pager | grep -v iptables
```

**Check for system issues:**
```bash
zgrep tw686 /var/log/messages*
```

---

# 7. Update & Upgrade Procedures

## Platform 1 (CentOS/Yum-based)

### Check Current Version

```bash
bridge-diag
cat /var/log/earlyboot.txt
ipccli --get_host_os
```

### Repository Fixes (CentOS Mirror Issues)

**⚠️ Common issue: "No URLs in metadata for failed update"**

```bash
# Fix CentOS mirrors (one line)
cd /etc/yum.repos.d/ && sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-* && sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' /etc/yum.repos.d/CentOS-* && yum install -y upgrader ipc python-diag
```

### Upgrade to Specific Version (Platform 1)

```bash
# Update to 2.3.8
yum update-to bridge-product-2.3.8

# Update to 2.5.6
yum update-to bridge-product-2.5.6

# Update to 2.4.4
yum upgrade-to bridge-product-2.4.4 -y
```

### Update Host and Tools

```bash
# Reinstall tools
yum reinstall --disablerepo=* --enablerepo=een -y upgrader ipc python-diag

# Update everything
yum install -y upgrader ipc python-diag && upgrader --train=prod --everything
```

---

## Platform 2 (Fedora/DNF-based)

### Check Platform 2 Version

```bash
ipccli --get_host_os && ipccli --list_containers
```

### Platform 1 to Platform 2 Migration

**⚠️ Make sure sub-account is unlocked if receiving errors**

```bash
# Install upgrader
yum install upgrader -y

# Upgrade with bandwidth limit and specific OS version
upgrader --bps=10000000000 --osver=2022-07-19

# Commit the upgrade
upgrader --commit
```

### Platform 2 Updates

**Using DNF (not yum):**
```bash
# Clean and install
dnf clean all && dnf install -y upgrader ipc python-diag && upgrader train=prod --everything

# Alternative
yum clean all && yum install upgrader && upgrader train=prod --everything
```

### Add Repository to HostOS 2022-02-01 and Above

```bash
dnf config-manager --add-repo http://repo.almalinux.org/almalinux/8/AppStream/x86_64/os/
```

### Add Repository to Bridge Container

```bash
yum install -y epel-release
```

### Install EPEL Repository

**For RHEL/CentOS 7:**
```bash
sudo yum install https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
```

**For RHEL/CentOS 8:**
```bash
sudo dnf install https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm
sudo dnf config-manager --set-enabled epel
```

**Install tools from EPEL:**
```bash
sudo dnf install nload  # For CentOS 8 or newer
sudo yum install nload  # For CentOS 7
```

---

## Container Upgrades

### Upgrade Bridge Container

```bash
# Upgrade to specific version (version history, oldest to newest seen)
ipccli --upgrade_container --container=bridge --version=3.16.1
ipccli --upgrade_container --container=bridge --version=3.17.3
ipccli --upgrade_container --container=bridge --version=3.18.3
ipccli --upgrade_container --container=bridge --version=3.19.3
ipccli --upgrade_container --container=bridge --version=3.22.3
ipccli --upgrade_container --container=bridge --version=3.24.1
ipccli --upgrade_container --container=bridge --version=3.25.3
ipccli --upgrade_container --container=bridge --version=3.26.1
ipccli --upgrade_container --container=bridge --version=3.27.10
ipccli --upgrade_container --container=bridge --version=3.30.0

# Watch upgrade progress
watch "ipccli --get_container"
watch "ipccli --get_container --container=bridge"
```

### Upgrade Camera Support

```bash
ipccli --upgrade_container --container=camera-support --version=v20230801
ipccli --upgrade_container --container=camera-support --version=v20231101
ipccli --upgrade_container --container=camera-support --version=v20260821
```

### Upgrade Smokeping

```bash
ipccli --upgrade_container --container=smokeping --version=2.7.3-10
```

### Upgrade LPR

```bash
# Check current version
docker pull c014.bridge.eencloud.com/bridge/ee-lpr-application-init:1.6.0

# Upgrade to latest seen version
yum install -y ipc python-diag && ipccli --upgrade_container --container=ee-lpr-application-init --version=2.2.0
```

### Upgrade RTSP App

```bash
ipccli --upgrade_container --container=bridge-rtsp-app --version=1.5.0
```

### Upgrade TalkDown

```bash
ipccli --upgrade_container --container=talkdown --version=1.15.0
```

### Upgrade Zero-Reboot

```bash
ipccli --upgrade_container --container=zero-reboot --version=1.6.1-20250821
```

### Kernel Management

```bash
# List current/available kernels
ipccli --get_host_kernel
ipccli --get_available_kernels

# Upgrade kernel
upgrader --kernver=5.15.74
```

### Install MTR (2022-03-01 or newer)

```bash
dnf --enablerepo=baseos install mtr -y
```

---

## Troubleshooting Failed Upgrades

### Check Upgrade Errors

```bash
# View upgrade log
cat /var/log/platform-upgrader.log

# Check for errors
cat /var/log/platform-upgrader.log | grep -i error | tail-50
getuperr  # Alias in some environments

# Check for certificate errors (400)
cat /var/log/platform-upgrader.log | grep 400
```

### Clear Upgrader

```bash
upgrader --clear
yum clean all
```

### Certificate Errors

**Check for cert issues:**
```bash
cat /var/log/platform-upgrader.log | grep 400
```

**Fix:**
```bash
# Re-install bridge-system
yum reinstall bridge-system -y
```

### No Container Available or Cluster Missing

**Check cluster configuration:**
```bash
cat /opt/een/etc/bridge/bridge.cluster
cat /opt/een/data/docker-compose/bridge/docker-compose.yml
nmap -p 443 c021.bridge.eencloud.com
curl https://c.bridge.eencloud.com/v2/_catalog
```

### Container Won't Start After Upgrade

**Check een-ipc:**
```bash
# Check if een-ipc is running
ps ax | grep een-ipc
systemctl status een-ipc

# Restart een-ipc
systemctl restart een-ipc --ignore_dependencies

# Check for docker files
ls -l /opt/een/data/docker-compose/bridge
```

**Check containers:**
```bash
docker ps

# If no containers, check:
systemctl status run-all-containers
systemctl start run-all-containers
```

**Delete MEI files (docker issues):**
```bash
cd /tmp && for i in *; do rm -rf $i | grep "_MEI"; done
```

### RPM Database Corruption

**Fix "rpmdb: Thread died in Berkeley DB library":**
```bash
mkdir /var/lib/rpm/backup
cp -a /var/lib/rpm/__db* /var/lib/rpm/backup/
rm -f /var/lib/rpm/__db.[0-9][0-9]*
rpm --quiet -qa
rpm --rebuilddb
yum clean all
```

### Downgrade Platform 2 to Platform 1

**⚠️ Only if absolutely necessary:**

```bash
# Downgrade
upgrader --downgrade

# Once downgraded and you can log back in, remove V3 files:
rm -rf /personality.json /opt/een/data/platform2 /opt/een/data/docker /opt/een/data/ipc.sock
```

### IPC Issues

```bash
# Check if IPC is installed
dnf list | grep ipc
rpm -qa | grep ipc

# Reinstall IPC
yum reinstall ipc
dnf install -y ipc

# Restart IPC
systemctl restart een-ipc --ignore_dependencies
```

---

# 8. Advanced Infrastructure

## Kubernetes Operations

### Kubectl Basics

**Access Kubernetes cluster:**
```bash
# Example: Connect to node
kubectl node-shell a2311

# If you don't see prompt, press enter
```

### Fetcher Logs

```bash
# Access fetcher node
kubectl node-shell a2311
cd /fetcher/logs
cat fetcher.log | grep <ESN>

# Example output interpretation:
# "failed getting ctrans for registry send" = fetcher not connected to any archiver at that moment
# "no ctrans for esn - bailing on it" = no valid archiver for the esn, unregister from fetcher
# "stuck in opening" = couldn't connect to archiver, will attempt another
```

---

## New Pod Testing & Validation

### When to Check New Pod

**Scenarios requiring new pod validation:**
- New pod/cluster has been deployed
- Account migration/move to different pod
- After infrastructure changes or upgrades
- Troubleshooting pod-specific issues
- Verifying service availability in new regions

### What Happens When Account is Moved

**When an account is moved to a new pod:**
- Account data migrated to new cluster
- Device registrations need validation
- Service endpoints may change
- Archiver assignments may update
- Bridge connections may need re-establishment
- Need to verify all services operational

### New Pod Testing Documentation

**Complete procedures and validation steps:**

- **New Pod Testing Guide:**
  https://eagleeyenetworks.atlassian.net/wiki/spaces/ENG/pages/2702147795/New+Pod+Testing

- **Performing New Pod Validations (WIP):**
  https://eagleeyenetworks.atlassian.net/wiki/spaces/ENG/pages/3555885110/Performing+New+Pod+Validations+-+WIP

**Key validation areas:**
- Service health checks (status-server, registry, gateway)
- Archiver connectivity and assignment
- Video recording and playback
- Event generation and notification delivery
- API endpoint functionality
- Authentication and authorization
- Bridge connectivity to new pod
- Camera streaming and preview generation

**Quick validation commands:**
```bash
# Check status-server for new pod
http://status-server.[new_pod].eencloud.com:5001/api/v2/Status?Account_in=[account]&Device_in=[device]

# Check registry for new pod
https://registry.[new_pod].eencloud.com/api/v2/Search?Include=czts&Device_in=[device]

# Verify archiver assignment
dig [esn].a.plumv.com

# Check bridge connectivity
ipccli --get_transports
```

---

## Microservices Monitoring

### VictoriaLogs Queries

**General VLogs URL structure:**
```bash
https://vlogs.eencloud.com/select/vmui/#/?query=[query]

# Search for specific container logs
https://vlogs.eencloud.com/select/vmui/#/?query=kubernetes.container_name%3A"vms-core-api"+AND+"[cameraId]"&g0.range_input=15m

# Search for error messages
https://vlogs.eencloud.com/select/vmui/#/?query=_msg%3A"error"

# Search by cluster and keywords
https://vlogs.eencloud.com/select/vmui/#/?query=((cluster%3A+[cluster])+AND+[keyword])
```

**Tips for vlogs:**
- Use `g0.range_input` for time range (e.g., 15m, 1h, 24h)
- Use `g0.end_input` for specific end time
- Use `displayFields` to show specific log fields

**Common Container Names:**
- media-service
- media-transcoder
- status-server
- alertid / alertd
- operator
- gateway
- vms-core-api
- bridge
- camera-direct
- cameraendpoint
- events3ingress / eventsv3ingress
- herald / herald-consumer
- registry
- videosearchworkers-inference
- webui-log-collector
- frontend-gui
- vms-core-pulsar-consumer
- vmswebapp
- event-normalizer
- ambrose (vehicle lists)
- oyez-consumer
- cm-auth
- virtualdevices-api
- cm-basurl-v3
- drivefs-notifier
- eventsv3alerts
- eventsv3api
- events3subscriptions
- jobs-api
- b2d2-pulsar-init
- pos-ingester / pos
- reports-api
- user-details
- videosearch-apis

### Jaeger Traces

```bash
# Query by trace ID
log.extra.trace_id: "bf38661978ac7e830343f0fa7730828e"

# Query media-service HLS segment duration/latency issues
kubernetes.container_name: "media-service" log.extra.path:~ "/media/recordings/main/hls/.*m4s" log.extra.duration:> 2000 log.extra.code: 200
```

### VMetrics

**For account VBS logs:**
```bash
kubernetes.node_labels.pod: "lon1p1" AND kubernetes.container_name:="gateway" AND "00050145"
kubernetes.pod_labels.app:alertd
```

### Webhook Event Tracking

**Track webhook delivery:**
```bash
# Query for successful webhook deliveries
kubernetes.pod_labels.app.kubernetes.io/instance:="oyez-consumer" AND log.extra.success:="true" AND log.extra.action_type:="webhook" AND account_id:"00181761"

# Search for failed webhooks
kubernetes.pod_labels.app.kubernetes.io/instance:="oyez-consumer" AND log.extra.success:="false" AND log.extra.action_type:="webhook"
```

### Media Transcoder Job Tracking

**Track transcoding jobs:**
```bash
# VictoriaLogs query for specific job
kubernetes.container_name: "media-transcoder" AND (log.extra.jobId: "9e1905bb-8231-4c57-8116-bc81d618407c" OR 9e1905bb-8231-4c57-8116-bc81d618407c)

# Check job status via API
https://api.c026.eagleeyenetworks.com/api/v3.0/jobs/18a45944-6c63-4004-b33e-9616797bb86a
```

### Permdocs/Dproxy Access

**Access backend cluster data:**
```bash
# Log in via VMS and get authkey (F12 > Application > authkey)
# Then access permdocs:
https://dproxy.test.eencloud.com/api/v2/dhash/node/v1/com.eencloud.dhash.cluster:<cluster>:/auth/<authkey>

# Example:
https://dproxy.test.eencloud.com/api/v2/dhash/node/v1/com.eencloud.dhash.cluster:c007:/auth/d2d5e419bae6bf680016156553b7df2d

# Note: Account number is hexadecimal, Dproxy is decimal
```

### Status Checks

**Status server:**
```bash
# Check device status
http://status-server.lon1p1.eencloud.com:5001/api/v2/Status?Account_in=00164224&Device_in=100096b1
```

**Registry check:**
```bash
https://registry.lon1p1.eencloud.com/api/v2/Search?Include=czts&Device_in=100096b1
```

**Dhash check:**
```bash
https://dproxy.test.eencloud.com/api/v2/dhash/node/v1/com.eencloud.dhash.pod::accounts

# Provisioning for an ESN:
https://dproxy.test.eencloud.com/api/v2/dhash/node/v1/com.eencloud.dhash.esn:100383c0:provisioning
```

### Update Dhash for Missing ESNs

**When ESNs are missing from dhash (VBS status-server pipeline failures):**

**Problem:** ESNs missing from dhash, causing this pipeline to fail:
```
https://concourse.eencloud.com/teams/main/pipelines/status-server-qa/jobs/vbs-ss-esn-sync/builds/65
```

**Solution using Claude Skills:**

**Prerequisites:**
- Access to Kubernetes
- Access to status-server repository

**Steps:**
```bash
# 1. Clone the repository
git clone https://github.com/EENCloud/status-server
cd status-server

# 2. Start Claude session in the directory
# (Use Claude Code CLI)

# 3. Use the Claude skill to update dhash
# Format: "update dhash for <pod> and esn <ESN>"
# Example:
"update dhash for aus1p1 and esn 10000678"

# The skill will automatically update dhash with the ESN
```

**Pod names (clusters):**
- aus1p1, fra1p2, lon1p1, etc.

**Reference:**
- Skill documentation: https://github.com/EENCloud/status-server/blob/master/.claude/skills/update-dhash-keys/SKILL.md
- Repository: https://github.com/EENCloud/status-server/tree/master

**Note:** This is an automated fix using Claude skills. The skill handles the dhash update operations via Kubernetes.

**Manual/legacy method (direct kubectl + python), if the skill isn't available:**
```bash
./kubectl config use-context yyz1p1
./kubectl get pods --selector app=gateway | head -5
./kubectl exec -it gateway-76d858f844-25l6n -- make shell

# In the shell:
import videobank.vms.models as vm
vm.Account._update_account_list_dhash_key('c025')
vm.Device._update_device_list_dhash_key('00194490')
```

---

## Event & Notification Pipeline

### Motion Alert Not Generating (bridge-log tag flow)

**Troubleshooting flow:**
1. HB for event
2. If there, check archiver for ALRS (Motion Alert) tag (`lqservices.html`)
3. If there, check VMLogs for alerts & accounts/ESN
4. If there, if API doesn't then no AEDN → escalate to OBC

```bash
# Check API
https://api.<cluster>.eagleeyenetworks.com/api/v3.0/accounts/<account>/notifications
# Check LUA
http://<esn>.a.plumv.com:28080/lqservices.html
```

**Watch bridge log for the relevant tags** (`ROME`, `ROMS`, `ALRS`, `ALRE`):
```bash
watch "grep ALRS bridge.log"
# Example output (every 2s):
# 20260226213707.066:10072b79 - sending ALRS(motion_3850992788) metric
```

### Notifications API

```bash
# Get notifications for account
https://api.[cluster].eagleeyenetworks.com/api/v3.0/accounts/[account_id]/notifications

# With filters:
https://api.c012.eagleeyenetworks.com/api/v3.0/accounts/00028077/notifications?alertId=&alertType=&actorId=&actorType=&actorAccountId=&category=&userId=ca0781a6&read=&status=&groupId=&timestamp__lte=&timestamp__gte=&creatorId=&serviceRuleId=&notificationActions__contains=

# Example:
https://api.c014.eagleeyenetworks.com/api/v3.0/accounts/00058171/notifications
```

### Event Subscriptions

```bash
# Review event subscriptions
curl -X GET "https://[domain]/api/v3.0/eventSubscriptions" \
  -H "Authorization: Bearer [token]"
```

### Check Push Notifications

```bash
https://api.[cluster].eagleeyenetworks.com/api/v3.0/accounts/[account]/notifications?userId=<user_id>
```

---

## Jobs API Tracking

### Job Service

**Check Jobs:**
```bash
# Jobs API endpoint
https://api.[cluster].eagleeyenetworks.com/api/v3.0/jobs/[jobId]

# Example:
https://api.c026.eagleeyenetworks.com/api/v3.0/jobs/18a45944-6c63-4004-b33e-9616797bb86a
```

### Query Sub-Jobs for Exports

**Find all sub-jobs for a parent export job:**
```bash
# Using internal API key
curl -s "https://api.c001.eagleeyenetworks.com/api/v3.0/jobs?userId=ca0603b4&pageSize=500&rootId=e1ba5d29-544b-4389-bf84-6586be85b93d" \
  -H "X-EEN-Internal-API-Key: 127fbee9-0220-4ef4-88e9-a49057321a0c" | jq

# Parameters:
# - userId: User who created the job
# - pageSize: Number of results (default 100, max 500)
# - rootId: Parent job ID to find all related sub-jobs
```

### Delete Download Job

**Manually delete stuck download jobs:**
```bash
# Step 1: Get the download job from browser
# - In browser, click on the download
# - Open Developer Tools (F12) > Network tab
# - Copy the request as cURL

# Step 2: Extract the job ID from endpoint
# Endpoint format: /api/v3.0/downloads/<jobID>:download
# Example: /api/v3.0/downloads/0b02ee17-ef47-4fd1-8632-33bd383ad32a:download

# Step 3: Use Postman or curl to DELETE the job
# - Paste cURL into Postman as new request
# - Change method from GET to DELETE
# - Remove ":download" from the end of the URL
# - Keep the auth token and base URL
# - Send the DELETE request

# Example curl:
curl -X DELETE "https://api.c001.eagleeyenetworks.com/api/v3.0/downloads/0b02ee17-ef47-4fd1-8632-33bd383ad32a" \
  -H "Authorization: Bearer [token]"
```

---

# 9. Specialized Features

## LPR (License Plate Recognition)

### Check LPR Status

```bash
# Check if LPR events are being generated at camera level
# Check if events are reaching VSP
# Verify cloud LPR vs camera-direct LPR configuration

# LPR services diagnostic page
http://[bridgeId].eagleeyenetworks.com:28080/lqservices.html

# Access camera LPR settings page
http://[cameraId].a.plumv.com:28080/settings?id=[cameraId]
```

### Install LPR Container

```bash
# Add LPR container
ipccli --add_container --container=ee-lpr-application-init --url=c000.bridge.eencloud.com/bridge/ee-lpr-application-init:2.0.0

# Remove LPR container
ipccli --remove_container --container=ee-lpr-application-init
```

### LPR Troubleshooting

**From Customer Impact Runbook:**

1. **Unauthorized Vehicle Access (EEPD-105713):**
   - Check vehicle credentials list
   - Verify expiration dates are enforced
   - Review LPR event logs
   - Check for pattern in unauthorized access
   - Verify access control rules and check for conflicts

2. **LPR Events Not Displaying (EEPD-105893):**
   - Verify cloudLPR events are being ingested
   - Check for ingestion errors
   - Confirm events are within expected timeframe
   - Check for date/timezone issues
   - Force event reingestion if needed

3. **Unable to Disable Cloud LPR (EEPD-106093):**
   - Make API call to disable LPR and review response
   - Check vlogs for errors in LPR configuration calls
   - Verify interface parity (Classic vs Enhanced)
   - Try disabling from alternate interface

### LPR Logs

```bash
# In bridge
tail -f anpr/instance1/ffmpeg.log
cd /opt/een/data/uncanny/
```

---

## Analytics Configuration

### Check Analytics

```bash
# Check number of analytics enabled
ps aux | grep -e 'analog.*analytics' | grep -v grep | wc -l

# Get ESN of camera in analytic search
ps aux | grep -e 'analog.*analytics' | grep -v grep
```

### Analytics FPS Requirements

- **4 FPS** for intrusion detection
- **8/12 FPS** for line crossing
- **16 FPS** for counting

### Camera Analytics Settings

```bash
# Get camera analytics settings via API
curl "https://api.[cluster].eagleeyenetworks.com/api/v3.0/cameras/[cameraId]" \
  -H "Authorization: Bearer [token]"

# Bulk update camera analytics
curl "https://api.[cluster].eagleeyenetworks.com/api/v3.0/cameras/[cameraId]/analyticsSettings:bulkUpdate?include=newRegions" \
  -X POST \
  -H "accept: application/json" \
  -H "Authorization: Bearer [token]" \
  -d '[analytics settings JSON]'
```

---

## Local Display (LocalX)

### Check LocalX Status

**Verify from host that process is running:**
```bash
# Comprehensive check
for i in /sys/class/drm/*/status; do
  echo "$i: " `cat $i`
done
ps ax | grep awesome
docker exec -it bridge_bridge_1 grep 'initial mode' /var/log/Xorg.0.log
ps ax | grep xplayer
docker exec -it bridge_bridge_1 status localx

# Or shorter version:
for i in /sys/class/drm/*/status; do
  cat $i
done | grep -wc 'connected' && ps ax | grep awesome && docker exec -it bridge_bridge_1 grep 'initial mode' /var/log/Xorg.0.log && ps ax | grep xplayer && docker exec -it bridge_bridge_1 status localx
```

**Processes:**
- **Xorg** - The overarching Display Process
- **LocalX** - Process for the Local Display via Monitor feature
- **Awesome** - Process to display the Cameras within LocalX
- **Xplayer** - Process of each camera playing

### LocalX Troubleshooting

**If X is running but Awesome is not:**
```bash
# Kill the Xorg process
ps ax | grep X
# Find PID resembling: /usr/libexec/Xorg :0 -nocursor -configdir /opt/een/etc/X11/xorg.conf.d

kill -9 [PID]

# Then restart localx (in container)
docker exec -it bridge_bridge_1 start localx
# Or:
start localx
```

**Check HDMI port connectivity:**
```bash
for i in /sys/class/drm/*/status; do
  echo "$i: "`cat $i`
done
```

**Check if X knows monitor resolution:**
```bash
ps ax | grep xplayer
docker exec -it bridge_bridge_1 grep 'initial mode' /var/log/Xorg.0.log
```

**LocalX count:**
```bash
ps -A | grep xplayer | wc -l
```

### Local Display Logs

```bash
# Log locations
cat /opt/een/var/log/nginx-error.log | tail
cat /var/log/Xorg.0.log
```

### Local Display Screenshot

**Platform 2:**
```bash
DISPLAY=":0" import -window root /local.png
cd / && ls -l | grep local.png
# Check filesize
```

**Platform 1:**
```bash
imlib2_grab /local.png
```

### Install/Reinstall LocalX

```bash
# Reinstall LocalX (Platform 1)
yum Re-install localX

# Install EEN-LocalX (Platform 2)
yum clean all; yum install -y een-localx

# Install LocalX
yum clean all; yum install -y localx

# Start LocalX
docker exec -it bridge_bridge_1 supervisorctl status localx
```

### Local Display Layouts

**Check layouts in use:**
```bash
# Layouts are here:
/opt/een/var/lib/local_display/layouts

# The layouts in use are in:
cat layouts_list.json

# Example output:
{
  "layouts": [
    {"id":"0100_a015a245-c8df-4c88-b760-b8cacdb12c3d.lout", "name":"325 test"},
    {"id":"0110_031f4641-1846-4bcb-b4c8-1ccf7d793847.lout", "name":"325 rotate"}
  ]
}

# Default all cameras layout: 1000_default.lout
```

**If looking for names on local display:**
- Choose only ONE desired layout in bridge layouts page
- Make sure names are enabled in layout settings

### Switch to Local Display

**Keyboard shortcut:**
```bash
Alt + P
```

---

## Display Stations (Ionodes)

- Manual: https://www.ionodes.com/wp-content/uploads/2023/02/IONODES-ION-R200-User-Manual.pdf
- MAC prefixes: `1c697aa765f4`, `1c:69:7a:a7:77:49`, `1c697a6abc3e`, `1C:69` or starting with `48:XX`; `00:07` for **DS100**
- Login: `admin` / `@EagleAdmin23` (shareable)

## InHand Networks Device Manager

- Device Manager: http://iot.inhandnetworks.com
- Login email: `agarcia2+solar@een.com`
- Login password: `671522`

---

## TalkDown Audio

### Install TalkDown

```bash
# Add TalkDown container
ipccli --add_container --container=talkdown --version=1.5.0 --url=c000.bridge.eencloud.com/bridge/talkdown-client:
```

### TalkDown Commands

```bash
# Set variables
export username="admin"
export ip_address="10.143.0.3"
export port="5060"

# Execute TalkDown
docker exec -it asterisk-cli asterisk -rx "channel originate PJSIP/anonymous/sip:${username}@${ip_address}:$port extension 100"
```

---

# 10. Customer Support Runbook

## Quick Resolution Patterns

**Based on analysis of 500 customer-impact tickets:**

### Resolution Success Rates

1. **Configuration Fixes** - 53% of resolutions
2. **Network Fixes** - 47% of resolutions
3. **API Debugging** - 22% of resolutions
4. **Permission/Auth Fixes** - 22% of resolutions
5. **Etag Sync Fixes** - 16% of resolutions
6. **Cache/Refresh Fixes** - 12% of resolutions
7. **Backend/Database Fixes** - 10% of resolutions

### Troubleshooting Flowchart

```
START: Customer reports issue
↓
1. Can you reproduce the issue?
   NO → Ask for specific steps, screenshots, timestamps
   YES → Continue
↓
2. Check recent deployments/changes
   Recent change? → Check release notes, known issues
↓
3. Identify issue category
↓
4. Try most common fix for that category:
   - Config issues (53%) → Check settings in both interfaces
   - Network issues (47%) → Verify VLAN, cables, connectivity
   - API issues (22%) → Test API endpoints
   - Auth issues (22%) → Check permissions, SSO
   - Etag sync (16%) → Initiate sync in Nexus
   - Cache (12%) → Clear cache, force refresh
   - Backend (10%) → Check for orphaned records, escalate
↓
5. Issue resolved?
   YES → Document resolution
   NO → Try next most likely fix OR escalate
```

---

## Common Issues by Category

### Top 20 Customer Symptoms

1. **Devices/Cameras Showing Offline** - 60 tickets (12%)
2. **Operation Failures** - 45 tickets (9%)
3. **System Crashes** - 40 tickets (8%)
4. **Loading Issues** - 35 tickets (7%)
5. **Video Playback Issues** - 35 tickets (7%)
6. **Unable to Perform Action** - 30 tickets (6%)
7. **Error Messages** - 30 tickets (6%)
8. **Missing Data/Content** - 20 tickets (4%)
9. **Login Problems** - 15 tickets (3%)
10. **Unplayable Video** - 10 tickets (2%)
11. **Buffering Issues** - 10 tickets (2%)
12. **Performance/Speed Issues** - 10 tickets (2%)
13. **Display Issues** - 10 tickets (2%)
14. **Deletion Issues** - 10 tickets (2%)
15. **Incorrect Data Display** - 5 tickets (1%)
16. **Feature Not Working** - 5 tickets (1%)
17. **Video Gaps/Missing Footage** - 5 tickets (1%)
18. **Loading Failures** - 5 tickets (1%)
19. **Access/Permission Issues** - 5 tickets (1%)
20. **Freezing/Hanging** - 5 tickets (1%)

### Common Error Codes

- **HTTP 422** - 10 occurrences (unprocessable content - often video/playback issues)
- **HTTP 404** - 10 occurrences (device not found, API endpoint issues)
- **HTTP 504** - 5 occurrences (gateway timeout)
- **HTTP 500** - 5 occurrences (internal server error)

### Camera Issues

**Symptoms:**
- Camera showing offline when actually online
- Unable to add camera to layout (404 errors)
- Camera appearing twice in system
- Preview freezing
- Camera status mismatches between Classic/Enhanced interfaces

**Quick fixes:**
1. Check etag sync status - initiate full sync in Nexus
2. Verify network connectivity and VLAN settings
3. Check for orphaned camera references in device list

### Bridge Issues

**Symptoms:**
- Bridge failures in short timeframe
- Unable to delete bridge (404 errors)
- Bridge not appearing in device list

**Quick fixes:**
1. Review bridge logs: `journalctl --since "YYYY-MM-DD"`
2. Check for software issues and recent firmware updates
3. Verify bridge appears in API: `/g/web/list/devices`
4. Look for orphaned database entries

### Network/Connectivity Issues

**Symptoms:**
- Devices showing offline in rollup/dashboard
- "Internet offline" status when device is online
- Unable to tunnel using satellite icon

**Quick fixes:**
1. Check rollup timing: https://graphs.eencloud.com/d/ae6dc5zpyowe8a/noc3a-reseller-rollup-refresh-lag
2. Verify device actual status vs displayed status
3. Test tunneling and check for proxy/firewall issues
4. Verify cluster assignment and cluster health

### Video Playback Issues

**Symptoms:**
- History playback buffers continuously
- Unable to play or download footage
- Playback freezes at specific timestamps
- 422 errors during playback
- Wrong status displayed for footage

**Quick fixes:**
1. Check timestamp errors and 422 errors in logs
2. Review cluster performance and storage health
3. Verify continuous recording and check for gaps
4. Test API calls for footage retrieval

---

## Escalation Procedures

### When to Escalate

1. **Multiple customers affected** - Indicates potential platform issue
2. **Data loss risk** - Footage missing or unrecoverable
3. **Security concerns** - Unauthorized access or authentication issues
4. **Backend data corruption** - Orphaned records, missing devices from API
5. **Unable to resolve with standard troubleshooting** - After exhausting runbook steps

### Escalation Information to Collect

- Account ID (master and sub if applicable)
- Device ESN (camera, bridge)
- Support PIN
- User email
- Exact timestamp of issue (UTC)
- Cluster information
- Steps already taken
- Screenshots/logs
- Related Jira tickets

### Critical Issues

**Report in:**
- `devops:Q&R` channel
- `announce:incidents` channel (for criticals)

**Severity levels:**
- **Critical** - Multiple users/clusters affected, login/settings issues
- **High** - Affects many users/resellers/accounts
- **Medium** - Isolated to specific account or small user group
- **Low** - Single user, workaround available

---

## JIRA Ticket Guidelines

### JIRA Ticket Template

**Summary Field:**
```
Category | Short description of issue
```

**Description Field:**
```
Master account: ${Cases.Master Account ID}
Sub-account: ${Cases.Sub Account ID}
Support PIN and email: ${Cases.Email} / ${Cases.Support PIN}

Bridge information - (One Bridge per Jira. SWAT will link tickets if investigation supports it)
SSN: ${Cases.Bridge Serial Number}
ESN: ${Cases.Bridge ESN}

Camera(s) - (include all affected cameras, can only be ESN if more than 2+)
Manufacturer:
Model:
Firmware:
MAC Address:
IP Address:
ESN:
Bridge:
Camera Credentials: admin / password

Description of issue:
[Provide description of actual issue with timestamps in UTC]

Reproduction steps/Troubleshooting done:
[Provide reproduction and troubleshooting steps done]

Expected result:
[Provide the expected result]

Attachments: Add CLI and/or screenshots to comments with context
```

### JIRA Best Practices

**DO:**
- Put JIRA number, then description in title
- Create topic in `ENG: Swat-Support-Engineering` channel
- Ping proper people (Brad, GMO, Jake, Tom)
- Use structured format from template above
- Include screenshots with explanations
- Document all troubleshooting steps taken
- Use UTC timestamps
- Test reproduction steps
- Include CLI output in code blocks (```)

**DON'T:**
- Put ESNs, accounts, or sensitive info in JIRA title (it's public)
- Comment on Yeva's tickets
- Comment on closed JIRA tickets (clone instead)
- Re-open JIRA (clone it and add new info)
- Skip reproduction steps
- Assume the reader can see what you see in screenshots

### JIRA Workflow

1. **Initial Report** - Capture all information from template
2. **Reproduction** - Document steps to reproduce (must be 1:1)
3. **Investigation** - Add findings and diagnostic output
4. **Resolution** - Document fix and verification
5. **Closure** - Verify with customer, update knowledge base if applicable

## Support Templates

**EEN outage message (customer-facing):**
> Eagle Eye Networks is aware of a service issue that is affecting our customers and is working to get it corrected. During this interruption your data is not being lost. We appreciate your patience as we get this condition addressed.

**Camera Support intake template:**
```
Bridge:
Bridge Serial:
Account:
Requested By:
OUI:
Make:
Model:
IP:
MAC:
Username:
Password:
Email:
Phone:
```

**Reseller/Sub-account template:**
```
Reseller (cluster):
Sub (cluster):
User:
Pin:
Bridge Serial:
Bridge ESN:
```

**RMA return address:**
```
NORTH AMERICA
ATTN: RMA No.
Eagle Eye Networks, Inc.
5321 Industrial Oaks Blvd, Suite 101
Austin, TX 78735 USA
```

---

# 11. Quick Reference

## Most-Used Commands

### Bridge Connection

```bash
# SSH to bridge
ssh root@<IP> -p 33022

# Exec access
http://<ESN>.a.plumv.com:28080/execute.html?c=<ESN>

# Trojan horse tunnel
ssh root@<bridge_IP> -o UserKnownHostsFile=/dev/null -p<port> -L8088:<camera_IP>:80
```

### Platform Check

```bash
# Quick platform/version check
bridge-diag
ipccli --get_host_os
ipccli --list_containers
```

### Camera Discovery

```bash
# ONVIF discovery all interfaces
for i in $(ifconfig | grep -E -A1 'wan0|camlan' | grep inet | awk -F ' +' '{print $3}'); do
  python -m camdriver.discovery -a $i
done
```

### Container Management

```bash
# Enter bridge container
docker exec -it bridge_bridge_1 /bin/bash

# Restart bridge app
systemctl restart docker-compose@bridge
```

### Network Diagnostics

```bash
# Network diagnostic
netdiag

# Quick connectivity test
ping -c 4 <IP>
```

### Logs

```bash
# Follow bridge log
tail -F /opt/een/var/log/bridge/bridge.log | grep -iE '<ESN>'

# Recent system logs
journalctl -S "3 days ago"
```

### RAID Status

```bash
# Check RAID
cat /proc/mdstat
mdadm -D /dev/md127
```

### Storage

```bash
# Disk space
df -h /opt/een/data

# Storage by camera
cd /opt/een/data/bridge/assets && ls */*/*
```

### Conversions & Utilities

```bash
# ESN to int (for camera direct / decimal conversion)
python3 -c 'print(int("<ESN>", 16))'

# Example: Convert ESN 100b213b to decimal
python3 -c 'print(int("100b213b", 16))'
# Output: 269553979

# Hex to Decimal conversion (general)
python3 -c 'print(int("<hex_value>", 16))'

# Decimal to Hex conversion
python3 -c 'print(hex(<decimal_value>))'

# Example: Convert decimal 269553979 to hex
python3 -c 'print(hex(269553979))'
# Output: 0x100b213b
```

**Note:** Account numbers in dproxy are decimal, but account numbers in the system are hexadecimal.

---

## API Endpoints

### Device Management

```bash
# List all devices for account
curl -X GET "https://[domain]/g/web/list/devices" \
  -H "Authorization: Bearer [token]"

# Check specific device
curl -X GET "https://[domain]/g/device/[deviceId]" \
  -H "Authorization: Bearer [token]"

# Delete bridge/device
curl "https://[domain]/g/device?id=[deviceId]&erase=1" \
  -X DELETE \
  -H "Authorization: Bearer [token]"
```

### Camera Management

```bash
# Get camera list with pagination
curl "https://api.[cluster].eagleeyenetworks.com/api/v3.0/cameras?pageToken=&id__in=[cameraIds]" \
  -H "Authorization: Bearer [token]"

# Get camera analytics settings
curl "https://api.[cluster].eagleeyenetworks.com/api/v3.0/cameras/[cameraId]" \
  -H "Authorization: Bearer [token]"
```

### Notifications

```bash
# Get notifications for account
https://api.[cluster].eagleeyenetworks.com/api/v3.0/accounts/[account_id]/notifications

# With user filter
https://api.[cluster].eagleeyenetworks.com/api/v3.0/accounts/[account]/notifications?userId=[user_id]
```

### Event Subscriptions

```bash
# Review event subscriptions
curl -X GET "https://[domain]/api/v3.0/eventSubscriptions" \
  -H "Authorization: Bearer [token]"
```

### Registry & Status

```bash
# Search device registry
curl "https://registry.[cluster].eencloud.com/api/v2/Search?Include=czts&Device_in=[deviceId]"

# Check dhash
curl "https://dproxy.test.eencloud.com/api/v2/dhash/node/v1/com.eencloud.dhash.esn:[accountId]:devices"

# Status server check
http://status-server.[cluster].eencloud.com:5001/api/v2/Status?Account_in=[account]&Device_in=[device]
```

---

## Camera Tool Status Codes

| Code | Meaning |
|------|---------|
| **STRM** | Streaming (working correctly) |
| **PEND** | Pending - driver built, waiting for user to add camera |
| **HOLD** | Did not match driver, need to build driver |
| **NONE** | Need password or could not find driver |
| **PASS** | Password required |
| **CONF** | In ONVIF configuration state machine |
| **CERR** | Configuration Error |
| **ERR** | Camera in error state (check user/pass/firmware/connection) |
| **FOND** | Ask Jeff about camera IP |
| **COFF** | Camera Off |
| **NSIG** | Analog camera |

---

## Emergency Procedures

### Bridge Won't Boot

1. Check if Platform 1 or 2
2. Check boot logs: `cat /var/log/earlyboot.txt`
3. Check for kernel panics: `journalctl -k | grep panic`
4. Check recent reboots: `last -x`
5. If J1900 CPU - known random reboot issue

### Bridge Offline - Cannot Access

1. Try alternative bridge on same network
2. Use nmap to find bridge: `nmap -oG - -p 33022 {IP/CIDR} | grep open`
3. Use emergency tunnel setup from exec
4. Contact NOC if cluster/badger issue

### RAID Failure

**⚠️ DO NOT ATTEMPT FSCK ON MOUNTED RAID!**

1. Check RAID status: `cat /proc/mdstat`
2. Check disk health: `for i in /dev/sd?; do smartctl -a $i; done`
3. If disk failed, try re-add: `mdadm --re-add /dev/md127 /dev/sdX`
4. If stuck rebuilding >48hrs, contact SWAT
5. **Never mess with RAID if unsure - escalate!**

### Camera Stuck Offline

1. Check etag sync status - initiate full sync
2. Verify physical connectivity: `ping <camera_IP>`
3. Check VLAN configuration
4. Check bridge can see camera: `arp -n | grep <camera_IP>`
5. Check camera logs: `tail -F /opt/een/var/log/bridge/bridge.log | grep <ESN>`

### Container Won't Start

1. Check een-ipc: `systemctl status een-ipc`
2. Restart IPC: `systemctl restart een-ipc`
3. Check docker: `docker ps`
4. Delete MEI files: `cd /tmp && for i in *; do rm -rf $i | grep "_MEI"; done`
5. Restart containers: `systemctl restart run-all-containers`

### Update Failed

1. Check logs: `cat /var/log/platform-upgrader.log | grep error`
2. Clear upgrader: `upgrader --clear && yum clean all`
3. Fix repos (if Platform 1): See Section 7
4. Reinstall tools: `yum reinstall --disablerepo=* --enablerepo=een -y upgrader ipc python-diag`
5. Try again with bandwidth limit: `upgrader --train=prod --everything --bps=1G`

### All Cameras Offline

1. Check network interfaces: `nmcli con show`
2. Bring up camlan: `nmcli con up camlan0`
3. Check DHCP: `nmap --script broadcast-dhcp-discover`
4. Check switch connectivity
5. Check bridge can route: `tail -F /opt/een/var/log/bridge/bridge.log | grep -iE 'route|curl|direct control'`

### Customer Cannot Login

1. Check auth status: https://graphs.eencloud.com/d/jFpmPakGk/vms-global-uptime?orgId=1
2. Try test user login (if possible)
3. Check cluster health
4. Check SSO configuration (if applicable)
5. Escalate if widespread issue

### Video Won't Play/Download

1. Check footage exists (retention period)
2. Verify recording was active
3. Check archiver connectivity
4. Test direct archiver download
5. Check for cluster issues
6. Initiate etag sync if status mismatches

---

## Important URLs & Resources

### Admin/Management

- **EEN Admin**: https://eenadmin.eagleeyenetworks.com/eenadmin/account_dashboard/[accountId]/
- **Dealer Portal**: https://dealer.cameramanager.com/
- **Classic Interface**: https://[cluster].eagleeyenetworks.com/
- **V3 WebApp**: https://webapp.eagleeyenetworks.com

### Monitoring & Logs

- **VictoriaLogs**: https://vlogs.eencloud.com/select/vmui/
- **Grafana**: https://graphs.eencloud.com/
- **NOC Dashboard**: https://graphs.eencloud.com/d/ae6dc5zpyowe8a/noc3a-reseller-rollup-refresh-lag
- **VMS Global Uptime**: https://graphs.eencloud.com/d/jFpmPakGk/vms-global-uptime?orgId=1

### Documentation

- **SWAT Ticket Guidelines**: https://eagleeyenetworks.atlassian.net/wiki/spaces/ENG/pages/2691268878/
- **Core Dumps to Backtraces**: https://eagleeyenetworks.atlassian.net/wiki/spaces/ENG/pages/2601713725/
- **Tech Support Tools**: (Reference internal documentation)

### Important Contacts

- **ADT Tech Support**: (866) 494-9120
- **Brivo Contacts**: anthony.mcphail@brivo.com, baudel.reyes@brivo.com

### Domains to Allow (Firewall)

- *.eagleeyenetworks.com
- *.plumv.com
- *.eencloud.com

### Default Camera IPs

- Eagle Eye cameras: 192.168.0.120 or 192.168.0.121 (DHCP-enabled)

### MFG Access

- **MFG Station**: ssh mfg@mfg.int.eencloud.com (use BIOS password)
- **MFG Password Formula**: "een" + last 5 digits of SSN backwards

---

## Special Notes

### Platform Differences

**Platform 1 (CentOS):**
- Uses `yum` package manager
- Port 33022 for SSH
- Older hardware (pre-2022)
- Legacy RAID configurations

**Platform 2 (Fedora/AlmaLinux):**
- Uses `dnf` package manager
- Modern containerization
- F2fs on SSDs
- NVME support

### Hardware Notes

- J1900 CPU bridges have random reboot issues
- 305 model has ports installed backwards
- Modern chassis: blue blinking lights = good, solid blue/red = bad
- Old chassis: amber blinking = good, no lights = bad

### Governor Settings by Model

- **504/524**: powersave, max_perf_pct=75
- **310/330/401/420/410/430/520/620/820**: performance
- **403**: powersave
- **Others**: ondemand (default)

### Warranty Information

- **Bridges**: Lifetime warranty
- **Other hardware**: 2 years

### Power Supply Models

- **EN-RP-003**: Eagle Eye 304/306/224/324 Power Supply (19v)
- **EN-RP-004**: Eagle Eye 305/225/325 Power Supply (19v/48v)
- **EN-RP-005**: Eagle Eye 224+/3x4+/3x6+/4x4+ Power Supply (12v/36w)

### Camera Specific Notes

- **Hikvision**: Don't downgrade firmware (ours or customer's)
- **Hanwha Techwin**: Enable control compression for motion box issues
- **Axis**: Username/password should NOT be same (unlike Hikvision)
- **2N IP Verso**: Cannot be reached via cloud tunnels, requires specific streaming settings

### Analog Camera Support

- We support CVBS or SD analog
- We do NOT support HD or 2MP analog

---

## The Box (Support Ops Server)

**Access Info:**
- Username: supportops
- Password: supportops132
- Last Known IP: 10.100.33.152
- MAC: 00:e0:1d:a:94:21

**Finding The Box:**
```bash
#!/bin/bash
myvar=$(sudo nmap -sP -n 10.100.32.1/22 | grep 94:21 -B2 | awk '/Nmap scan report/ {print $5}')
ssh supportops@$myvar
```

**What's on The Box:**
- supportctl tool
- fix_bridge_certs.py
- get_bridge_logs.py
- frontend playtest utilities
- EEN scripts and tools

**Useful Aliases (run `aliasup` to see all):**
- Various support automation scripts

### Installing SupportCTL Locally

```bash
wsl --install   # Windows only, if needed
# Linux:
curl -Lo supportctl http://asmodeus.aus1hub1.eencloud.com/api/v1/releases/releases/supportctl/linux/x64/latest/supportctl
# Mac:
curl -Lo supportctl http://asmodeus.aus1hub1.eencloud.com/api/v1/releases/releases/supportctl/mac/x64/latest/supportctl
chmod +x supportctl
sudo mv ./supportctl /usr/local/bin
```
Upgrade: `sudo apt update && sudo apt dist-upgrade -y`

---

## Espanso Shortcuts

*(If configured in your environment)*

```bash
colorit         # Make output colorful
getassets       # Go to assets folder and list
pythonbridgelogs # Get bridge logs with Python script
whatistime      # Check time registered to device ESN
whereswitch     # Find switches (host)
wereswitch      # Find switches (container)
shrugsbash      # ¯\_(ツ)_/¯
sunbash         # \[T]/ (Praise the Sun!)
```

---

## Additional Tips

### Search This Document

Use your editor's search function (Ctrl+F / Cmd+F) or grep:
```bash
grep -i "keyword" EEN-Master-Technical-Reference.md
```

### Most Common Workflows

**Camera Offline?**
→ Section 2: Camera Status Troubleshooting → Section 10: Quick Resolution Patterns

**Bridge Issues?**
→ Section 1: Bridge Operations & Management → Section 7: Update & Upgrade Procedures

**Network Problems?**
→ Section 3: Network & Connectivity → Section 10: Common Issues by Category

**RAID Issues?**
→ Section 4: Storage & RAID → Section 11: Emergency Procedures

**Need to Update?**
→ Section 7: Update & Upgrade Procedures

**Video Playback Issues?**
→ Section 5: Video & Footage Operations → Section 10: Common Issues by Category

---

## Disclaimer

This document is compiled from multiple sources and represents best practices and procedures as of the compilation date. Always verify procedures before executing, especially destructive commands (RAID operations, firmware updates, etc.).

**When in doubt, ask before acting!**

---

**End of Master Technical Reference Guide**

*For updates or corrections, contact ACG Support Team*
