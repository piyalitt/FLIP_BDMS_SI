#!/bin/bash
# Copyright (c) Guy's and St Thomas' NHS Foundation Trust & King's College London
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
#
# forward-trust-all.sh
#
# Opens SSM port forwards for all Trust web UIs and API swagger docs in parallel.
# Prints the URLs to paste into a browser. Ctrl+C stops all forwards.

set -e

INSTANCE_ID=$(terraform output -raw TrustEc2InstanceId)
if [ -z "$INSTANCE_ID" ]; then
  echo "❌ Could not read TrustEc2InstanceId from terraform output"
  exit 1
fi

declare -a PIDS=()

forward() {
  local remote=$1
  local local_port=$2
  local name=$3
  local url_hint=$4
  aws ssm start-session --target "$INSTANCE_ID" \
    --document-name AWS-StartPortForwardingSession \
    --parameters "portNumber=${remote},localPortNumber=${local_port}" \
    >/dev/null 2>&1 &
  PIDS+=($!)
  printf "  %-18s %s\n" "$name" "$url_hint"
}

cleanup() {
  echo ""
  echo "🛑 Stopping all port forwards..."
  kill "${PIDS[@]}" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}
trap cleanup EXIT INT TERM

echo "🔀 Opening SSM port forwards to Trust EC2 ($INSTANCE_ID)..."
echo ""
forward 8104 8104 "XNAT"            "http://localhost:8104"
forward 8042 8042 "Orthanc"         "http://localhost:8042"
forward 8020 8020 "trust-api"       "http://localhost:8020/docs"
forward 8001 8001 "imaging-api"     "http://localhost:8001/docs"
forward 8010 8010 "data-access-api" "http://localhost:8010/docs"
forward 3000 3000 "Grafana"         "http://localhost:3000"
echo ""
echo "⏳ Sessions starting up (takes ~5s)..."
sleep 5
echo "✅ All forwards ready. Ctrl+C to stop."
wait
