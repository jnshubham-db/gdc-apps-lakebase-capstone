# Capstone app — project instructions

## Python formatting & linting (ruff)

All Python in this project MUST be formatted and lint-clean with **ruff**
before every commit. Ruff config lives in `app/pyproject.toml`
(`line-length = 100`, `target-version = "py311"`).

Run both, from the repo root, on the paths you touched:

```bash
uvx ruff format app/ lakebase/     # format
uvx ruff check --fix app/ lakebase/  # lint (autofix what it can)
```

- Both must pass (format clean, `All checks passed!`) before you commit.
- Prefer fixing the code over adding `# noqa`; when a suppression is genuinely
  warranted, scope it to the specific rule with a reason
  (e.g. `# noqa: BLE001 — …`).

## Tests

Run pytest **from `app/`** so `[tool.pytest.ini_options]` and the `live`
marker load:

```bash
cd app && uv run --with "psycopg[binary,pool]" --with databricks-sdk \
    --with python-dotenv --with pytest pytest -q
```

`live`-marked tests hit the `fevm-test-jg` workspace / Lakebase and skip
automatically when Databricks auth isn't available.
