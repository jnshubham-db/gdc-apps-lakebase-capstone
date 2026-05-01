# Databricks notebook source
# MAGIC %md
# MAGIC # Capstone 05 — Create the Genie Space
# MAGIC
# MAGIC Creates (or updates) a Genie space scoped to the 5 capstone gold tables:
# MAGIC `customers`, `transactions`, `products`, `support_tickets`, `customer_segments`.
# MAGIC
# MAGIC **Output:** prints `GENIE_SPACE_ID=<id>` — copy into `app/.env`.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
import uuid

dbutils.widgets.text("catalog", "capstone", "UC catalog with gold tables")
dbutils.widgets.text("schema", "gold", "Gold schema name")
dbutils.widgets.text("warehouse_id", "", "SQL Warehouse ID (Serverless recommended)")
dbutils.widgets.text("space_title", "Customer 360 — Capstone Genie", "Genie space title")
dbutils.widgets.text("parent_path", "/Workspace/Shared/capstone", "Workspace folder for the space")

CAT          = dbutils.widgets.get("catalog")
SCH          = dbutils.widgets.get("schema")
WAREHOUSE_ID = dbutils.widgets.get("warehouse_id").strip()
TITLE        = dbutils.widgets.get("space_title")
PARENT       = dbutils.widgets.get("parent_path")

assert WAREHOUSE_ID, "Set the warehouse_id widget — use any running Serverless SQL Warehouse"

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# COMMAND ----------

# MAGIC %md ## Build the serialized_space payload

# COMMAND ----------

def _hex_id() -> str:
    """32-char lowercase hex ID (no hyphens) required by the Genie API."""
    return uuid.uuid4().hex

# Tables must be sorted alphabetically by identifier
TABLES = sorted([
    f"{CAT}.{SCH}.customer_segments",
    f"{CAT}.{SCH}.customers",
    f"{CAT}.{SCH}.products",
    f"{CAT}.{SCH}.support_tickets",
    f"{CAT}.{SCH}.transactions",
])

space_obj = {
    "version": 2,
    "data_sources": {
        "tables": [
            {"identifier": t}
            for t in TABLES
        ]
    },
    "instructions": {
        "text_instructions": [
            {
                "id": _hex_id(),
                "content": [
                    "# Customer 360 Analytics Assistant\n",
                    "\n",
                    "You analyze Acme Retail customer data across 5 tables.\n",
                    "\n",
                    "## Key relationships\n",
                    "- `customers.segment_id` → `customer_segments.segment_id` for human-readable segment names\n",
                    "- `transactions.customer_id` → `customers.customer_id`\n",
                    "- `transactions.product_id` → `products.product_id`\n",
                    "- `support_tickets.customer_id` → `customers.customer_id`\n",
                    "\n",
                    "## Business rules\n",
                    "- Only `transactions.status = 'completed'` counts as realised revenue\n",
                    "- `customers.lifetime_value` is the authoritative LTV figure\n",
                    "- `customers.churn_score` ranges 0–1; scores > 0.7 are high-risk\n",
                    "- 'Recent activity' means `transactions.transaction_date` in the last 30 days\n",
                    "\n",
                    "## Response format\n",
                    "1. Run a SQL query against the relevant table(s)\n",
                    "2. Summarise the result in 2–3 plain-English sentences\n",
                    "3. Suggest one follow-up question the user might find valuable\n",
                ]
            }
        ]
    },
    "config": {
        "sample_questions": [
            {"id": _hex_id(), "question": ["Which segment has the highest average lifetime value?"]},
            {"id": _hex_id(), "question": ["Top 10 products by revenue in the last 30 days"]},
            {"id": _hex_id(), "question": ["How many open support tickets are there per category?"]},
            {"id": _hex_id(), "question": ["List customers in the EU region with churn score above 0.7"]},
            {"id": _hex_id(), "question": ["Weekly transaction trend for the Champions segment"]},
        ]
    },
}

serialized = json.dumps(space_obj)
print("serialized_space built — tables:", [t["identifier"] for t in space_obj["data_sources"]["tables"]])

# COMMAND ----------

# MAGIC %md ## Create or update the Genie space

# COMMAND ----------

# Check if a space with this title already exists
existing_space_id = None
try:
    resp = w.genie.list_spaces()
    for space in (resp.spaces or []):
        if space.title == TITLE:
            existing_space_id = space.space_id
            print(f"Found existing space: {existing_space_id} ('{space.title}')")
            break
except Exception as e:
    print(f"Warning: could not list spaces — {e}")

# COMMAND ----------

if existing_space_id:
    print(f"Updating space {existing_space_id}...")
    w.genie.update_space(
        space_id=existing_space_id,
        title=TITLE,
        warehouse_id=WAREHOUSE_ID,
        serialized_space=serialized,
    )
    space_id = existing_space_id
    print(f"Updated.")
else:
    print("Creating new Genie space...")
    # Ensure parent folder exists
    try:
        w.workspace.mkdirs(PARENT)
    except Exception:
        pass

    space = w.genie.create_space(
        warehouse_id=WAREHOUSE_ID,
        serialized_space=serialized,
        title=TITLE,
        description="Natural-language analytics over the Acme Retail Customer 360 gold tables.",
        parent_path=PARENT,
    )
    space_id = space.space_id
    print(f"Created.")

# COMMAND ----------

print(f"\nGENIE_SPACE_ID={space_id}")
print(f"GENIE_URL=/genie/rooms/{space_id}")

# COMMAND ----------

# Structured output for the curl-installer (parsed via jobs.get_run_output)
import json
dbutils.notebook.exit(json.dumps({
    "GENIE_SPACE_ID": space_id,
    "GENIE_URL": f"/genie/rooms/{space_id}",
}))
