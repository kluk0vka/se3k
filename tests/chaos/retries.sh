#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

USERS=${USERS:-25}
WARMUP_S=${WARMUP_S:-45}
FAULT_S=${FAULT_S:-120}
RECOVERY_S=${RECOVERY_S:-45}
ERROR_RATE=${ERROR_RATE:-0.5}
OUT=${OUT:-tests/chaos/results/retries-$(date +%Y%m%d-%H%M%S)}
VIP=${VIP:-http://192.168.58.100}
CLUSTER='outbound|8000||inventory-service.staybook.svc.cluster.local'
mkdir -p "$OUT"

ts() { date +%H:%M:%S; }

catalog_stats() {
  kubectl -n staybook exec deploy/catalog-service -c istio-proxy -- pilot-agent request GET stats 2>/dev/null |
    grep -F "cluster.${CLUSTER};." |
    grep -E "upstream_rq_retry(_success|_limit_exceeded)?:|outlier_detection\.ejections_active" |
    sed "s/^cluster\.[^;]*;\.//" | tr '\n' ' '
}

set_fault() {
  kubectl -n staybook exec deploy/inventory-service -c app -- python -c "
import json, urllib.request
req = urllib.request.Request('http://localhost:8000/admin/fault', method='PUT',
    data=json.dumps({'error_rate': $1, 'status_code': 503}).encode(), headers={'content-type': 'application/json'})
print(urllib.request.urlopen(req).read().decode())"
}

docker rm -f locust-retries >/dev/null 2>&1 || true
docker run -d --name locust-retries --network staybook -v "$PWD/tests/load:/mnt/locust:ro" -v "$PWD/$OUT:/out" \
  locustio/locust -f /mnt/locust/locustfile.py --headless -u "$USERS" -r 10 \
  -t "$((WARMUP_S + FAULT_S + RECOVERY_S))s" -H "$VIP" --csv /out/locust --html /out/locust.html Guest >/dev/null

phase() {
  local name=$1 seconds=$2
  local end=$((SECONDS + seconds))
  while [ "$SECONDS" -lt "$end" ]; do
    echo "$(ts) [$name] $(catalog_stats)" >> "$OUT/catalog-envoy.log"
    sleep 5
  done
}

echo "$(ts) warmup ${WARMUP_S}s" | tee "$OUT/timeline.log"
phase warmup "$WARMUP_S"
echo "$(ts) inject fault: inventory-service returns 503 for ${ERROR_RATE} of requests" | tee -a "$OUT/timeline.log"
set_fault "$ERROR_RATE" | tee -a "$OUT/timeline.log"
phase fault "$FAULT_S"
echo "$(ts) remove fault" | tee -a "$OUT/timeline.log"
set_fault 0.0 | tee -a "$OUT/timeline.log"
phase recovery "$RECOVERY_S"

docker wait locust-retries >/dev/null
docker logs locust-retries > "$OUT/locust-stdout.log" 2>&1
docker rm locust-retries >/dev/null
echo "$(ts) done, results in $OUT" | tee -a "$OUT/timeline.log"
echo "--- catalog -> inventory Envoy counters (first and last sample of each phase)"
for p in warmup fault recovery; do grep "\[$p\]" "$OUT/catalog-envoy.log" | sed -n '1p;$p'; done
