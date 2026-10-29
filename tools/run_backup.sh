#!/bin/zsh
# The presentation fallback: this checkout, on this machine only, against demo_backup.db -
# the same seeded accounts as the live site (tools/seed_demo.py), never the hosted database.
#   zsh tools/run_backup.sh        then open http://localhost:8661
ROOT="${0:A:h:h}"
cd "$ROOT" || exit 1
[[ -f demo_backup.db ]] || { echo "No demo_backup.db - run: python3 tools/seed_demo.py --db demo_backup.db"; exit 1; }
PY="$ROOT/.venv/bin/python"
[[ -x "$PY" ]] || PY=python3
export TURSO_DATABASE_URL= TURSO_AUTH_TOKEN= MEDVAULT_DB="$ROOT/demo_backup.db"
exec "$PY" -m streamlit run app.py --server.headless true --server.address 127.0.0.1 \
  --server.port 8661 --browser.gatherUsageStats false
