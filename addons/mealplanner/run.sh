#!/usr/bin/with-contenv bash
set -e

export MEALPLANNER_DB_PATH="/data/mealplanner.db"
# Default to empty. HA ingress will provide headers; this is just a fallback.
export MEALPLANNER_INGRESS_PATH="${INGRESS_PATH:-}"

echo "[mealplanner] Starting..."
echo "[mealplanner] INGRESS_PATH=${MEALPLANNER_INGRESS_PATH}"
echo "[mealplanner] DB=${MEALPLANNER_DB_PATH}"

# IMPORTANT: proxy headers for ingress
exec /opt/venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8099 --proxy-headers