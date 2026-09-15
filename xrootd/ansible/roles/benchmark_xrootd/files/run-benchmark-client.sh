#!/usr/bin/env bash
#
# run-benchmark-client.sh
#
# Client-side benchmark for the UKSRC XRootD 100Gb WCDC-DIRAC link.
# Companion to the server-side 'benchmark_xrootd' ansible role
# (xrootd/ansible/roles/benchmark_xrootd).
#
# Run from any machine that can reach the server's 100Gb IP. Best results come
# from a host attached to the WCDC-DIRAC-791 network (192.84.5.0/27); running
# from the public internet measures the end-to-end path, which may be capped
# by the client's own uplink.
#
# Prerequisites: iperf3, curl
#
# Usage:
#   ./run-benchmark-client.sh [options]
#
# Options:
#   -s IP        server 100Gb IP              (default: 192.84.5.20)
#   -p PORT      iperf3 server port           (default: 5201)
#   -n STREAMS   parallel iperf3 TCP streams  (default: 32)
#   -t SECONDS   iperf3 test duration         (default: 30)
#   -f PATH      XRootD file path to download (default: /benchmark/bench-1.bin)
#   -r           also run the reverse direction (client uploads to server)
#   -u           also run a UDP line-rate test
#   -j           use 8900-byte packets for the UDP test (9000 MTU path)
#   -T TOKEN     WLCG/SKA-IAM bearer token for the XRootD download test
#                (no token = connectivity check only, reads may be denied)
#   -q           quiet output (only the summary)
#   -h           show this help and exit
#
# Environment (optional):
#   BENCH_NET_PASS_GBPS     pass mark for the network (iperf3) test, default 90
#   BENCH_XROOTD_PASS_GBPS  pass mark for the XRootD (HTTP) test, default 10
#
# Exit status: 0 all tests passed, 1 at least one test failed, 2 usage error
set -uo pipefail

SERVER="192.84.5.20"
IPERF_PORT=5201
XROOTD_PORT=1094
STREAMS=32
DURATION=30
DOWNLOAD_MAX_TIME=60
FILE="/benchmark/bench-1.bin"
TOKEN=""
DO_REVERSE=0
DO_UDP=0
DO_JUMBO=0
QUIET=0
NET_PASS="${BENCH_NET_PASS_GBPS:-90}"
XROOTD_PASS="${BENCH_XROOTD_PASS_GBPS:-10}"
LAST_GBPS="0.00"
RC=0

usage() {
    cat <<'USAGE'
Usage: ./run-benchmark-client.sh [options]

  -s IP        server 100Gb IP              (default: 192.84.5.20)
  -p PORT      iperf3 server port           (default: 5201)
  -n STREAMS   parallel iperf3 TCP streams  (default: 32)
  -t SECONDS   iperf3 test duration         (default: 30)
  -f PATH      XRootD file path to download (default: /benchmark/bench-1.bin)
  -r           also run the reverse direction (client uploads to server)
  -u           also run a UDP line-rate test
  -j           use 8900-byte packets for the UDP test (9000 MTU path)
  -T TOKEN     WLCG/SKA-IAM bearer token for the XRootD download test
  -q           quiet output (only the summary)
  -h           show this help and exit
USAGE
    exit 2
}

while getopts "s:p:n:t:f:T:rujqh" opt; do
    case "$opt" in
        s) SERVER="$OPTARG" ;;
        p) IPERF_PORT="$OPTARG" ;;
        n) STREAMS="$OPTARG" ;;
        t) DURATION="$OPTARG" ;;
        f) FILE="$OPTARG" ;;
        T) TOKEN="$OPTARG" ;;
        r) DO_REVERSE=1 ;;
        u) DO_UDP=1 ;;
        j) DO_JUMBO=1 ;;
        q) QUIET=1 ;;
        h) usage ;;
        *) usage ;;
    esac
done

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing required tool: $1"; exit 2; }; }
need iperf3
need curl

# --- iperf3 JSON parsers (no jq needed) -------------------------------------

# Print the last aggregate "sum_received" bits_per_second in Gbps.
iperf_gbps() {
    awk '
        /"sum_received"/ { in_sum = 1 }
        in_sum && /"bits_per_second"/ {
            v = $2; gsub(/[^0-9.]/, "", v); out = v / 1e9
        }
        END { if (out > 0) printf "%.2f", out; else print "0.00" }
    ' "$1"
}

iperf_retransmits() {
    awk '
        /"sum_sent"/ { in_sum = 1 }
        in_sum && /"retransmits"/ { v = $2; gsub(/[^0-9]/, "", v); out = v }
        END { if (out > 0) print out; else print "0" }
    ' "$1"
}

# Print "<Gbps> <loss %>" from the final UDP summary block ("sum": {...}).
iperf_udp() {
    awk '
        /"sum":/ { in_sum = 1 }
        in_sum && /"bits_per_second"/ { v = $2; gsub(/[^0-9.]/, "", v); bps = v }
        in_sum && /"lost_percent"/ {
            v = $2; gsub(/[^0-9.]/, "", v)
            printf "%.2f %s\n", (bps / 1e9), v
            exit
        }
    ' "$1"
}

# Run iperf3 -J and print the aggregated result. Sets LAST_GBPS.
run_iperf() {
    local label="$1"; shift
    local json gbps retrans
    json="$(mktemp /tmp/bench.XXXXXX)" || return 1
    if [ "$QUIET" -eq 0 ]; then
        echo "  - $label"
        echo "      iperf3 -J -c $SERVER -p $IPERF_PORT $*"
    fi
    iperf3 -J -c "$SERVER" -p "$IPERF_PORT" "$@" >"$json" 2>/dev/null || true
    gbps="$(iperf_gbps "$json")"
    retrans="$(iperf_retransmits "$json")"
    rm -f "$json"
    LAST_GBPS="$gbps"
    echo "      $gbps Gbps   (retransmits: $retrans)"
}

AUTH=()
[ -n "$TOKEN" ] && AUTH=( -H "Authorization: Bearer $TOKEN" )

# --- preflight ---------------------------------------------------------------

if [ "$QUIET" -eq 0 ]; then
    echo "== XRootD 100Gb link benchmark ($(date '+%F %T')) =="
    echo "Server: $SERVER  iperf3 port: $IPERF_PORT  streams: $STREAMS  duration: ${DURATION}s"
    echo
    echo "== Preflight =="
fi
HTTP_CODE="$(curl -k -s -o /dev/null -w '%{http_code}' --max-time 10 "https://${SERVER}:${XROOTD_PORT}/robots.txt" 2>/dev/null || echo 000)"
if [ "$HTTP_CODE" = "000" ]; then
    echo "  ERROR: $SERVER:$XROOTD_PORT not reachable from here (HTTP code 000)."
    echo "  Check routing/firewall - see README 'Benchmarking the 100 Gb link'."
    RC=1
else
    echo "  Reachability OK: HTTPS $SERVER:$XROOTD_PORT answered HTTP $HTTP_CODE (a 401/403 just means auth is required)."
fi

# --- network path (iperf3) ---------------------------------------------------

echo
echo "== Network path (iperf3) =="

run_iperf "TCP single stream ($DURATION s)" -t "$DURATION"
SINGLE="$LAST_GBPS"

run_iperf "TCP $STREAMS parallel streams ($DURATION s)" -t "$DURATION" -P "$STREAMS"
PARALLEL="$LAST_GBPS"

if [ "$DO_REVERSE" -eq 1 ]; then
    run_iperf "TCP reverse, $STREAMS streams ($DURATION s)" -t "$DURATION" -P "$STREAMS" -R
    REVERSE="$LAST_GBPS"
fi

if [ "$DO_UDP" -eq 1 ]; then
    LEN=1460
    [ "$DO_JUMBO" -eq 1 ] && LEN=8900
    echo "  - UDP line-rate test ($LEN-byte packets, 20 s)"
    json="$(mktemp /tmp/bench.XXXXXX)" || exit 1
    iperf3 -J -u -c "$SERVER" -p "$IPERF_PORT" -t 20 -b 100G -l "$LEN" >"$json" 2>/dev/null || true
    read -r UDP_GBPS UDP_LOSS <<<"$(iperf_udp "$json")"
    rm -f "$json"
    echo "      $UDP_GBPS Gbps, loss $UDP_LOSS%"
fi

# --- XRootD end-to-end (HTTP GET) --------------------------------------------

echo
echo "== XRootD end-to-end (HTTP GET) =="
URL="https://${SERVER}:${XROOTD_PORT}${FILE}"

if [ "$HTTP_CODE" = "000" ]; then
    echo "  Skipped - server not reachable."
    XROOTD_GBPS="0.00"
elif [ -z "$TOKEN" ]; then
    echo "  No bearer token given (-T TOKEN); only checking connectivity."
    echo "  Reads from '$FILE' may be denied by the SciTokens authz."
    echo "  Download test skipped."
    XROOTD_GBPS="0.00"
else
    echo "  Testing: $URL  (${STREAMS} parallel downloads, max ${DOWNLOAD_MAX_TIME}s each)"
    ddir="$(mktemp -d /tmp/benchd.XXXXXX)" || exit 1
    i=0
    while [ "$i" -lt "$STREAMS" ]; do
        curl -k -s -o /dev/null "${AUTH[@]}" --max-time "$DOWNLOAD_MAX_TIME" -w '%{speed_download}\n' "$URL" >"$ddir/$i" &
        i=$((i + 1))
    done
    wait
    TOTAL_SPEED="$(awk '{s += $1} END {print s}' "$ddir"/* 2>/dev/null || echo 0)"
    XROOTD_GBPS="$(awk -v b="$TOTAL_SPEED" 'BEGIN { printf "%.2f", b * 8 / 1e9 }')"
    rm -rf "$ddir"
    echo "      aggregate download: $XROOTD_GBPS Gbps"
fi

# --- summary -----------------------------------------------------------------

echo
echo "== Summary =="
printf '  %-52s %10s\n' "iperf3 single stream (TCP)"                "${SINGLE} Gbps"
printf '  %-52s %10s\n' "iperf3 $STREAMS parallel streams (TCP)"    "${PARALLEL} Gbps"
if [ "$DO_REVERSE" -eq 1 ]; then
    printf '  %-52s %10s\n' "iperf3 reverse $STREAMS streams (TCP)" "${REVERSE} Gbps"
fi
if [ "$DO_UDP" -eq 1 ]; then
    printf '  %-52s %10s\n' "iperf3 UDP line-rate"                   "$UDP_GBPS Gbps ($UDP_LOSS% loss)"
fi
if [ -n "${XROOTD_GBPS:-}" ] && [ "$XROOTD_GBPS" != "0.00" ]; then
    printf '  %-52s %10s\n' "XRootD HTTP ($STREAMS parallel GETs)"   "${XROOTD_GBPS} Gbps"
fi
echo

if awk "BEGIN { exit !($PARALLEL >= $NET_PASS) }"; then
    echo "  [PASS] Network path: ${PARALLEL} Gbps >= ${NET_PASS} Gbps - the 100Gb link is saturated."
else
    echo "  [FAIL] Network path: ${PARALLEL} Gbps < ${NET_PASS} Gbps - the 100Gb link is NOT saturated."
    echo "         For a true link test run from a host on the WCDC-DIRAC subnet (192.84.5.0/27)"
    echo "         with the highest available MTU; a public-internet client is often the bottleneck."
    RC=1
fi

if [ -n "${XROOTD_GBPS:-}" ]; then
    if [ "$XROOTD_GBPS" = "0.00" ]; then
        echo "  [INFO] XRootD throughput not measured (no token / server unreachable)."
    elif awk "BEGIN { exit !($XROOTD_GBPS >= $XROOTD_PASS) }"; then
        echo "  [PASS] XRootD serving: ${XROOTD_GBPS} Gbps >= ${XROOTD_PASS} Gbps."
        echo "         The gap to the network number (${PARALLEL} Gbps) is normally the storage backend"
        echo "         (single CephFS mount), not the 100Gb link."
    else
        echo "  [FAIL] XRootD serving: ${XROOTD_GBPS} Gbps < ${XROOTD_PASS} Gbps."
        echo "         Check the storage/read path first; compare against the iperf3 result."
        RC=1
    fi
fi

echo
if [ "$RC" -eq 0 ]; then
    echo "  OVERALL: PASS"
else
    echo "  OVERALL: FAIL"
fi
exit "$RC"