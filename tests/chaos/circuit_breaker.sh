#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

USERS=${USERS:-40}
WARMUP_S=${WARMUP_S:-60}
FAULT_S=${FAULT_S:-120}
RECOVERY_S=${RECOVERY_S:-90}
OUT=${OUT:-tests/chaos/results/$(date +%Y%m%d-%H%M%S)}
VIP=${VIP:-http://192.168.58.100}
CLUSTER='outbound|8000||payment-service.staybook.svc.cluster.local'
mkdir -p "$OUT"

ts() { date +%H:%M:%S; }

gateway_stats() {
  kubectl -n edge exec deploy/staybook-gateway-istio -- pilot-agent request GET stats 2>/dev/null |
    grep -F "cluster.${CLUSTER};." |
    grep -E "outlier_detection\.ejections_(active|enforced_total|enforced_consecutive_5xx|enforced_consecutive_gateway_failure)|upstream_rq_retry|upstream_rq_pending_overflow" |
    sed "s/^cluster\.[^;]*;\.//" | tr '\n' ' '
}

served_by() {
  docker run --rm --network staybook curlimages/curl -s -o /dev/null -D - \
    -X POST "$VIP/payments" -H "x-user-id: chaos-probe-$1" -H "content-type: application/json" \
    -d "{\"booking_id\":\"$(uuidgen | tr 'A-Z' 'a-z')\",\"amount_minor\":1000}" |
    awk -v n="$1" 'tolower($1)=="x-served-by:"{h=$2} /^HTTP/{c=$2} END{print n, c, h}' | tr -d '\r'
}

set_fault() {
  kubectl -n staybook exec "$1" -c app -- python -c "
import json, urllib.request
req = urllib.request.Request('http://localhost:8000/admin/fault', method='PUT',
    data=json.dumps({'error_rate': $2, 'delay_ms': 0}).encode(), headers={'content-type': 'application/json'})
print(urllib.request.urlopen(req).read().decode())"
}

PODS=($(kubectl -n staybook get pods -l app=payment-service -o jsonpath='{.items[*].metadata.name}'))
[ "${#PODS[@]}" -ge 2 ] || { echo "need at least 2 payment-service pods" >&2; exit 1; }
VICTIM=${PODS[0]}
echo "payment pods: ${PODS[*]}; victim: $VICTIM" | tee "$OUT/timeline.log"

docker rm -f locust-chaos >/dev/null 2>&1 || true
docker run -d --name locust-chaos --network staybook -v "$PWD/tests/load:/mnt/locust:ro" -v "$PWD/$OUT:/out" \
  locustio/locust -f /mnt/locust/locustfile.py --headless -u "$USERS" -r 10 \
  -t "$((WARMUP_S + FAULT_S + RECOVERY_S))s" -H "$VIP" --csv /out/locust --csv-full-history --html /out/locust.html Guest >/dev/null

phase() {
  local name=$1 seconds=$2
  local end=$((SECONDS + seconds))
  while [ "$SECONDS" -lt "$end" ]; do
    echo "$(ts) [$name] $(gateway_stats)" >> "$OUT/gateway-envoy.log"
    served_by "$name" >> "$OUT/served-by.log"
    sleep 5
  done
}

echo "$(ts) warmup ${WARMUP_S}s" | tee -a "$OUT/timeline.log"
phase warmup "$WARMUP_S"
echo "$(ts) inject fault: $VICTIM returns 503 for 100% of /payments" | tee -a "$OUT/timeline.log"
set_fault "$VICTIM" 1.0 | tee -a "$OUT/timeline.log"
phase fault "$FAULT_S"
echo "$(ts) remove fault on $VICTIM" | tee -a "$OUT/timeline.log"
set_fault "$VICTIM" 0.0 | tee -a "$OUT/timeline.log"
phase recovery "$RECOVERY_S"

docker wait locust-chaos >/dev/null
docker logs locust-chaos > "$OUT/locust-stdout.log" 2>&1
docker rm locust-chaos >/dev/null
echo "$(ts) done, results in $OUT" | tee -a "$OUT/timeline.log"

echo "--- served-by per phase (http code, pod)"
awk '{print $1, $2, $3}' "$OUT/served-by.log" | sort | uniq -c
echo "--- gateway envoy: ejections"
sed -E 's/^([0-9:]+) \[([a-z]+)\].*ejections_active: ([0-9]+).*ejections_enforced_total: ([0-9]+).*/\1 \2 active=\3 enforced_total=\4/' "$OUT/gateway-envoy.log" |
  awk '{k=$2" "$3" "$4; if (k!=prev) print; prev=k}' | head -30
