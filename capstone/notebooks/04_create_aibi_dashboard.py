# Databricks notebook source
# MAGIC %md
# MAGIC # Capstone 04 — Create the AI/BI (Lakeview) Dashboard
# MAGIC
# MAGIC Builds a Lakeview dashboard that the app embeds via iframe. The dashboard
# MAGIC exposes 4 datasets and 5 widgets:
# MAGIC
# MAGIC | Widget | Data | Anomaly visible |
# MAGIC |---|---|---|
# MAGIC | Segment LTV bar | `gold.customers` grouped by segment | Champions LTV far above others |
# MAGIC | Top products | `gold.transactions` joined `gold.products` | Electronics spike |
# MAGIC | Tickets timeseries | `gold.support_tickets` by week + category | Billing outage spike |
# MAGIC | Churn-risk histogram | `gold.customers.churn_score` | High-risk cluster at 0.8+ |
# MAGIC | Segment churn avg | `gold.customers` churn by segment | "About to Churn" segment outlier |
# MAGIC
# MAGIC **Output:** prints `DASHBOARD_ID` — copy into `app/.env`.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade databricks-sdk

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "capstone", "UC catalog with gold tables")
dbutils.widgets.text("schema", "gold", "Schema with gold tables")
dbutils.widgets.text("warehouse_id", "", "SQL Warehouse ID (Serverless recommended)")
dbutils.widgets.text("dashboard_name", "Customer 360 — Capstone", "Dashboard display name")
dbutils.widgets.text("parent_path", "/Workspace/Shared/capstone", "Workspace folder for dashboard")

CAT          = dbutils.widgets.get("catalog")
SCH          = dbutils.widgets.get("schema")
WAREHOUSE_ID = dbutils.widgets.get("warehouse_id").strip()
NAME         = dbutils.widgets.get("dashboard_name")
PARENT       = dbutils.widgets.get("parent_path")

assert WAREHOUSE_ID, "Set warehouse_id widget — pick any Serverless SQL Warehouse"

# COMMAND ----------

import json
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import Dashboard

w = WorkspaceClient()
w.workspace.mkdirs(PARENT)

# COMMAND ----------

# MAGIC %md ## Build the dashboard JSON
# MAGIC
# MAGIC Key wiring rules for Lakeview:
# MAGIC - `datasets[*].name` must match `queries[*].query.datasetName`
# MAGIC - `fields[*].name` must exactly match `encodings.*.fieldName`
# MAGIC - Every encoding axis needs `scale.type`: `categorical`, `quantitative`, or `temporal`

# COMMAND ----------

def sql(q):
    return q.format(cat=CAT, sch=SCH)

datasets = [
    {
        "name": "ds_segments",
        "displayName": "Customers by Segment",
        "queryLines": [sql(
            "SELECT s.segment_name, COUNT(*) AS customers, "
            "ROUND(AVG(c.lifetime_value), 2) AS avg_ltv, "
            "ROUND(AVG(c.churn_score), 3) AS avg_churn "
            "FROM {cat}.{sch}.customers c "
            "JOIN {cat}.{sch}.customer_segments s ON c.segment_id = s.segment_id "
            "GROUP BY s.segment_name ORDER BY avg_ltv DESC"
        )],
    },
    {
        "name": "ds_top_products",
        "displayName": "Top products by revenue",
        "queryLines": [sql(
            "SELECT p.name AS product_name, p.category, "
            "ROUND(SUM(t.amount), 2) AS revenue, COUNT(*) AS units "
            "FROM {cat}.{sch}.transactions t "
            "JOIN {cat}.{sch}.products p ON t.product_id = p.product_id "
            "WHERE t.status = 'completed' "
            "GROUP BY p.name, p.category "
            "ORDER BY revenue DESC LIMIT 15"
        )],
    },
    {
        "name": "ds_tickets_weekly",
        "displayName": "Support tickets by week",
        "queryLines": [sql(
            "SELECT DATE_TRUNC('week', opened_at) AS week, "
            "category, COUNT(*) AS tickets "
            "FROM {cat}.{sch}.support_tickets "
            "GROUP BY DATE_TRUNC('week', opened_at), category "
            "ORDER BY week"
        )],
    },
    {
        "name": "ds_churn",
        "displayName": "Churn-risk distribution",
        "queryLines": [sql(
            "SELECT ROUND(FLOOR(churn_score * 10) / 10, 1) AS bucket, "
            "COUNT(*) AS customers "
            "FROM {cat}.{sch}.customers "
            "GROUP BY ROUND(FLOOR(churn_score * 10) / 10, 1) "
            "ORDER BY bucket"
        )],
    },
]


def bar_widget(name, title, dataset, x_field, y_field,
               x_type="categorical", y_type="quantitative",
               color_field=None, color_type="categorical"):
    # x and color are dimensions (GROUP BY keys); y is the measure — use MAX() so
    # pre-aggregated datasets (one row per group) pass through correctly with
    # disaggregated=false, which is required for Lakeview to render bar charts.
    y_expr = f"MAX(`{y_field}`)"
    fields = [
        {"name": x_field,  "expression": f"`{x_field}`"},
        {"name": y_field,  "expression": y_expr},
    ]
    encodings = {
        "x": {"fieldName": x_field, "scale": {"type": x_type},  "displayName": x_field},
        "y": {"fieldName": y_field, "scale": {"type": y_type},   "displayName": y_field},
        "label": {"show": False},
    }
    if color_field:
        fields.append({"name": color_field, "expression": f"`{color_field}`"})
        encodings["color"] = {"fieldName": color_field, "scale": {"type": color_type}, "displayName": color_field}

    return {
        "name": name,
        "queries": [{
            "name": "main_query",
            "query": {
                "datasetName": dataset,
                "fields": fields,
                "disaggregated": False,
            },
        }],
        "spec": {
            "version": 3,
            "widgetType": "bar",
            "encodings": encodings,
            "frame": {"showTitle": True, "title": title},
        },
    }


def line_widget(name, title, dataset, x_field, y_field,
                color_field=None, color_type="categorical"):
    y_expr = f"SUM(`{y_field}`)"
    fields = [
        {"name": x_field, "expression": f"`{x_field}`"},
        {"name": y_field, "expression": y_expr},
    ]
    encodings = {
        "x": {"fieldName": x_field, "scale": {"type": "temporal"}, "displayName": x_field},
        "y": {"fieldName": y_field, "scale": {"type": "quantitative"}, "displayName": y_field},
    }
    if color_field:
        fields.append({"name": color_field, "expression": f"`{color_field}`"})
        encodings["color"] = {"fieldName": color_field, "scale": {"type": color_type}, "displayName": color_field}

    return {
        "name": name,
        "queries": [{
            "name": "main_query",
            "query": {
                "datasetName": dataset,
                "fields": fields,
                "disaggregated": False,
            },
        }],
        "spec": {
            "version": 3,
            "widgetType": "line",
            "encodings": encodings,
            "frame": {"showTitle": True, "title": title},
        },
    }


layout = [
    # Row 1: Segment LTV (left) + Top Products (right)
    {
        "position": {"x": 0, "y": 0, "width": 3, "height": 5},
        "widget": bar_widget(
            "w_seg", "Average LTV by Segment",
            "ds_segments", "segment_name", "avg_ltv",
        ),
    },
    {
        "position": {"x": 3, "y": 0, "width": 3, "height": 5},
        "widget": bar_widget(
            "w_top", "Top 15 Products by Revenue",
            "ds_top_products", "product_name", "revenue",
            color_field="category",
        ),
    },
    # Row 2: Tickets timeseries (full width) — shows billing spike anomaly
    {
        "position": {"x": 0, "y": 5, "width": 6, "height": 5},
        "widget": line_widget(
            "w_tk", "Weekly Support Tickets by Category (billing spike ~8 wks ago)",
            "ds_tickets_weekly", "week", "tickets",
            color_field="category",
        ),
    },
    # Row 3: Churn histogram (left) + Segment churn (right)
    {
        "position": {"x": 0, "y": 10, "width": 3, "height": 5},
        "widget": bar_widget(
            "w_ch", "Churn-Risk Distribution (spike at 0.8+)",
            "ds_churn", "bucket", "customers",
            x_type="quantitative",
        ),
    },
    {
        "position": {"x": 3, "y": 10, "width": 3, "height": 5},
        "widget": bar_widget(
            "w_seg_churn", "Avg Churn Score by Segment",
            "ds_segments", "segment_name", "avg_churn",
        ),
    },
]

dashboard_def = {
    "datasets": datasets,
    "pages": [{
        "name": "page_main",
        "displayName": "Customer 360",
        "pageType": "PAGE_TYPE_CANVAS",
        "layout": layout,
    }],
    "uiSettings": {
        "theme": {"widgetHeaderAlignment": "ALIGNMENT_UNSPECIFIED"},
        "applyModeEnabled": False,
    },
}

serialized = json.dumps(dashboard_def)
print("Dashboard JSON built.")

# COMMAND ----------

# MAGIC %md ## Create / update

# COMMAND ----------

existing = None
for d in w.lakeview.list():
    if d.display_name == NAME:
        existing = d
        break

if existing:
    print(f"Updating dashboard {existing.dashboard_id}")
    dash = w.lakeview.update(
        dashboard_id=existing.dashboard_id,
        dashboard=Dashboard(
            display_name=NAME,
            warehouse_id=WAREHOUSE_ID,
            serialized_dashboard=serialized,
        ),
    )
else:
    print("Creating new dashboard")
    dash = w.lakeview.create(
        dashboard=Dashboard(
            display_name=NAME,
            warehouse_id=WAREHOUSE_ID,
            parent_path=PARENT,
            serialized_dashboard=serialized,
        ),
    )

w.lakeview.publish(dashboard_id=dash.dashboard_id, warehouse_id=WAREHOUSE_ID)
print("Published.")

# COMMAND ----------

print(f"DASHBOARD_ID={dash.dashboard_id}")
print(f"DASHBOARD_URL=/dashboards/{dash.dashboard_id}")
print(f"WAREHOUSE_ID={WAREHOUSE_ID}")

# COMMAND ----------

# Structured output for the curl-installer (parsed via jobs.get_run_output)
import json
dbutils.notebook.exit(json.dumps({
    "DASHBOARD_ID": dash.dashboard_id,
    "DASHBOARD_URL": f"/dashboards/{dash.dashboard_id}",
    "WAREHOUSE_ID": WAREHOUSE_ID,
}))
