#!/usr/bin/env bash
# Post the sample tickets T-1 … T-7, re-post T-1 to show the duplicate response, approve
# the T-2 refund, then print the final state of every ticket.
#
# Requires curl and jq. Usage: scripts/demo.sh   (API_URL defaults to http://localhost:8000)
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
SAMPLES="${SAMPLES:-$(cd "$(dirname "$0")/.." && pwd)/samples/tickets.json}"
WAIT_SECONDS="${WAIT_SECONDS:-60}"

say() { printf '\n== %s\n' "$*"; }

request() { # method path [json-body] -> prints "<status> <body>"
  local method=$1 path=$2 body=${3:-}
  local args=(-sS -X "$method" -o /tmp/demo-response.$$ -w '%{http_code}' "$API_URL$path")
  [ -n "$body" ] && args+=(-H 'Content-Type: application/json' -d "$body")
  local status
  status=$(curl "${args[@]}")
  printf '%s %s\n' "$status" "$(cat /tmp/demo-response.$$)"
  rm -f /tmp/demo-response.$$
}

step_of() { curl -sS "$API_URL/tickets/$1" | jq -r '.step // empty'; }

wait_for_step() { # ticket-id step-regex
  local deadline=$((SECONDS + WAIT_SECONDS)) step=""
  while [ $SECONDS -lt $deadline ]; do
    step=$(step_of "$1")
    [[ "$step" =~ ^($2)$ ]] && return 0
    sleep 1
  done
  echo "timed out waiting for $1 to reach '$2' (last step: '${step:-unknown}')" >&2
  return 1
}

say "Waiting for the API at $API_URL"
for _ in $(seq "$WAIT_SECONDS"); do
  curl -fsS "$API_URL/openapi.json" >/dev/null 2>&1 && break
  sleep 1
done

say "POST /tickets for every sample ticket"
jq -c '.[]' "$SAMPLES" | while read -r ticket; do
  id=$(jq -r '.ticket_id' <<<"$ticket")
  printf 'POST %-4s -> %s\n' "$id" "$(request POST /tickets "$ticket")"
done

say "POST T-1 again (duplicate: same workflow, nothing processed twice)"
printf 'POST T-1  -> %s\n' "$(request POST /tickets "$(jq -c '.[0]' "$SAMPLES")")"

say "Approving the T-2 refund"
wait_for_step T-2 awaiting_approval
approval='{"approved": true, "reviewer": "demo-reviewer", "comment": "Duplicate charge confirmed."}'
printf 'POST T-2/approval -> %s\n' "$(request POST /tickets/T-2/approval "$approval")"

say "Final state of every ticket"
for id in $(jq -r '.[].ticket_id' "$SAMPLES"); do
  wait_for_step "$id" 'completed|failed'
  curl -sS "$API_URL/tickets/$id" | jq -c '{
    ticket_id, step,
    proposed: (.proposed_decision.action.kind // null),
    action: .decision.action.kind,
    detail: (.decision.action.reason // .decision.action.invoice_id // (.decision.action.article_ids | tostring)),
    result: (.result.outcome_message // .failure_reason)
  }'
done
