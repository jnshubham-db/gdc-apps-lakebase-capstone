#!/usr/bin/env sh
# Regenerate requirements.txt (runtime deps only) from the uv lockfile.
# The Databricks Apps runtime installs from requirements.txt; keep it in sync
# with pyproject.toml/uv.lock by running this — never hand-edit requirements.txt.
set -eu
cd "$(dirname "$0")/.."
uv export --no-dev --no-emit-project --no-hashes --output-file requirements.txt
echo "requirements.txt regenerated from uv.lock"
