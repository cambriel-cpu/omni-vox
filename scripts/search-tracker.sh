#!/bin/bash
# Search Quota Tracker
# Logs web_search usage to track Brave API consumption
# Called by: cron jobs, or manually
# Data: telemetry/search-usage.jsonl

TELEMETRY_DIR="/root/.openclaw/workspace/telemetry"
LOGFILE="$TELEMETRY_DIR/search-usage.jsonl"
mkdir -p "$TELEMETRY_DIR"

ACTION="${1:-query}"  # "query" or "summary"

if [ "$ACTION" = "summary" ]; then
    if [ ! -f "$LOGFILE" ]; then
        echo '{"total":0,"today":0,"this_month":0}'
        exit 0
    fi
    TODAY=$(date -u +%Y-%m-%d)
    MONTH=$(date -u +%Y-%m)
    TOTAL=$(wc -l < "$LOGFILE")
    TODAY_COUNT=$(grep "\"date\":\"$TODAY\"" "$LOGFILE" | wc -l)
    MONTH_COUNT=$(grep "\"month\":\"$MONTH\"" "$LOGFILE" | wc -l)
    echo "{\"total\":$TOTAL,\"today\":$TODAY_COUNT,\"this_month\":$MONTH_COUNT}"
else
    SOURCE="${2:-unknown}"
    QUERIES="${3:-1}"
    TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    DATE=$(date -u +%Y-%m-%d)
    MONTH=$(date -u +%Y-%m)
    echo "{\"ts\":\"$TS\",\"date\":\"$DATE\",\"month\":\"$MONTH\",\"source\":\"$SOURCE\",\"queries\":$QUERIES}" >> "$LOGFILE"
fi
