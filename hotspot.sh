#!/usr/bin/env bash
# Wi-Fi hotspot for the phone via NetworkManager. Usage: hotspot.sh [up|down|status]
# Env overrides: IFACE, SSID, PASS. Laptop gets 10.42.0.1; phone streams to rtmp://10.42.0.1:1935/live/bow
set -euo pipefail

CON=delaycam-hotspot
SSID=${SSID:-DelayCam}
PASS=${PASS:-delaycam123}
IFACE=${IFACE:-$(nmcli -t -f DEVICE,TYPE device | awk -F: '$2=="wifi"{print $1; exit}')}

case "${1:-up}" in
  up)
    [[ -n "$IFACE" ]] || { echo "no Wi-Fi device found (set IFACE=...)" >&2; exit 1; }
    # note: this takes over the Wi-Fi adapter, dropping any existing Wi-Fi connection on it
    nmcli connection delete "$CON" >/dev/null 2>&1 || true
    nmcli device wifi hotspot ifname "$IFACE" con-name "$CON" ssid "$SSID" password "$PASS"
    ip=$(nmcli -g IP4.ADDRESS device show "$IFACE" | head -1 | cut -d/ -f1)
    echo "hotspot up: SSID=$SSID password=$PASS"
    echo "phone stream URL: rtmp://${ip:-10.42.0.1}:1935/live/bow"
    if command -v ufw >/dev/null && sudo -n ufw status 2>/dev/null | grep -q "Status: active"; then
      echo "ufw is active: run 'sudo ufw allow 1935/tcp' if the phone can't connect" >&2
    fi
    ;;
  down)
    nmcli connection down "$CON"
    ;;
  status)
    nmcli -f GENERAL.STATE,IP4.ADDRESS connection show "$CON"
    ;;
  *)
    echo "usage: $0 [up|down|status]" >&2; exit 1
    ;;
esac
