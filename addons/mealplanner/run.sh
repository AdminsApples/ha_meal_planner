#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "Starting Meal Planner add-on..."

export MEALPLANNER_DB_PATH="/data/mealplanner.db"
export MEALPLANNER_INGRESS_PATH="${INGRESS_PATH:-/}"

python -m uvicorn server:app --host 0.0.0.0 --port 8099