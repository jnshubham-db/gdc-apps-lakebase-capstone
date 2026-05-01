# Databricks notebook source
# MAGIC %md
# MAGIC # Capstone 01 — Generate Gold-Layer Customer 360 Data
# MAGIC
# MAGIC Generates 5 synthetic Delta tables with **realistic distributions**:
# MAGIC - `gold.customers` (10k) — weighted segments, age bell-curve, correlated LTV
# MAGIC - `gold.transactions` (100k + anomaly spikes) — seasonal Q4 peak, category-priced amounts
# MAGIC - `gold.products` (200) — real product names, category-appropriate pricing
# MAGIC - `gold.support_tickets` (20k + billing outage spike) — meaningful subjects, correlated CSAT
# MAGIC - `gold.customer_segments` (8)
# MAGIC
# MAGIC All have Change Data Feed enabled (required for synced tables).
# MAGIC
# MAGIC **Run this first.** Idempotent — re-running drops + recreates all tables.
# MAGIC
# MAGIC ## Anomalies baked in (visible on the AI/BI dashboard)
# MAGIC | Anomaly | Dashboard widget |
# MAGIC |---|---|
# MAGIC | Champions LTV 8k–25k; 50 VIP customers at 40k+ | Segment LTV bar |
# MAGIC | S8 "About to Churn" churn_score 0.82–0.97 | Churn histogram spike at 0.8+ |
# MAGIC | 600 extra high-value Electronics txns in last 3 wks | Top Products bar |
# MAGIC | 500 extra urgent billing tickets ~50–55 days ago | Tickets timeseries spike |

# COMMAND ----------

dbutils.widgets.text("catalog", "capstone", "Catalog name")
dbutils.widgets.text("schema", "gold", "Schema name")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA  = dbutils.widgets.get("schema")
print(f"Target: {CATALOG}.{SCHEMA}")

# COMMAND ----------

existing = {r.catalog for r in spark.sql("SHOW CATALOGS").collect()}
if CATALOG not in existing:
    try:
        spark.sql(f"CREATE CATALOG {CATALOG}")
    except Exception as e:
        raise RuntimeError(
            f"Catalog '{CATALOG}' does not exist and could not be created: {e}\n"
            "Ask your workspace admin to create it, or pass an existing catalog in the `catalog` widget."
        )

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# COMMAND ----------

# MAGIC %md ## Customer segments (8 rows)

# COMMAND ----------

segments = [
    ("S1", "Champions",           "High LTV, frequent purchases, very loyal",        "ltv>8000 AND recency<30"),
    ("S2", "Loyal",               "Repeat buyers, above-average LTV",                 "ltv 3000-8000"),
    ("S3", "Potential Loyalists", "Recent + frequent, growing LTV",                   "ltv 1500-3000"),
    ("S4", "New Customers",       "Signed up < 90 days, first few purchases",         "tenure<90"),
    ("S5", "At Risk",             "Was high-value, recency declining",                "ltv>4000 AND recency>90"),
    ("S6", "Hibernating",         "Low recency + frequency, minimal engagement",      "recency>180"),
    ("S7", "Price Sensitive",     "Discount-driven, low-margin purchases",            "discount_ratio>0.5"),
    ("S8", "About to Churn",      "High churn probability, needs immediate attention","churn_score>0.8"),
]
seg_df = spark.createDataFrame(
    segments,
    "segment_id STRING, segment_name STRING, description STRING, criteria STRING"
)
(seg_df.write.mode("overwrite")
    .option("delta.enableChangeDataFeed", "true")
    .saveAsTable("customer_segments"))
print("customer_segments: 8 rows")

# COMMAND ----------

# MAGIC %md ## Products (200 rows) — real names, category-appropriate pricing

# COMMAND ----------

import random
random.seed(42)

# (category, item_base, brand, price_min, price_max, subcategory)
_catalog = []

electronics_items = [
    ("4K Smart TV 55\"", "Electronics", 449, 1299),
    ("4K Smart TV 43\"", "Electronics", 279, 549),
    ("Laptop Pro 14\"",  "Electronics", 899, 1999),
    ("Laptop Air 13\"",  "Electronics", 699, 1299),
    ("Flagship Smartphone", "Electronics", 699, 1199),
    ("Mid-Range Smartphone", "Electronics", 299, 599),
    ("Wireless Headphones", "Electronics", 79, 449),
    ("True Wireless Earbuds", "Electronics", 49, 249),
    ("10\" Tablet",      "Electronics", 199, 649),
    ("Gaming Console",   "Electronics", 299, 599),
    ("Mirrorless Camera", "Electronics", 599, 1799),
    ("Smart Watch",      "Electronics", 149, 499),
]
apparel_items = [
    ("Classic Cotton T-Shirt",  "Apparel", 14, 45),
    ("Slim Fit Jeans",          "Apparel", 39, 119),
    ("Floral Summer Dress",     "Apparel", 29, 99),
    ("Puffer Winter Jacket",    "Apparel", 79, 249),
    ("Running Sneakers",        "Apparel", 59, 179),
    ("Chelsea Leather Boots",   "Apparel", 89, 249),
    ("Merino Wool Sweater",     "Apparel", 49, 149),
    ("Yoga Leggings",           "Apparel", 24, 89),
    ("Business Oxford Shirt",   "Apparel", 34, 99),
    ("Waterproof Raincoat",     "Apparel", 69, 199),
]
home_items = [
    ("Drip Coffee Maker",       "Home", 29, 149),
    ("6qt Air Fryer",           "Home", 59, 199),
    ("High-Speed Blender",      "Home", 49, 179),
    ("Robot Vacuum",            "Home", 149, 599),
    ("Memory Foam Mattress Q",  "Home", 299, 999),
    ("LED Floor Lamp",          "Home", 39, 149),
    ("Non-Stick Cookware Set",  "Home", 59, 249),
    ("Cordless Stick Vacuum",   "Home", 79, 299),
    ("Instant Pot 7-in-1",      "Home", 59, 159),
    ("Smart Thermostat",        "Home", 89, 249),
]
beauty_items = [
    ("Hyaluronic Acid Serum",   "Beauty", 14, 89),
    ("Vitamin C Moisturizer",   "Beauty", 18, 79),
    ("Long-Wear Foundation",    "Beauty", 12, 55),
    ("Mascara Volume",          "Beauty", 9, 35),
    ("Eau de Parfum 50ml",      "Beauty", 39, 149),
    ("Anti-Aging Eye Cream",    "Beauty", 22, 99),
    ("Argan Oil Shampoo",       "Beauty", 14, 45),
    ("Collagen Face Mask Set",  "Beauty", 19, 65),
]
sports_items = [
    ("Trail Running Shoes",     "Sports", 69, 199),
    ("Premium Yoga Mat",        "Sports", 24, 89),
    ("Whey Protein Powder 5lb", "Sports", 39, 89),
    ("Resistance Bands Set",    "Sports", 14, 49),
    ("Adjustable Dumbbell Set", "Sports", 99, 399),
    ("Road Bicycle 21-Speed",   "Sports", 299, 999),
    ("Gym Duffle Bag",          "Sports", 29, 99),
    ("Smart Jump Rope",         "Sports", 19, 69),
]
books_items = [
    ("Python for Data Science", "Books", 29, 59),
    ("Atomic Habits",           "Books", 14, 29),
    ("Clean Code",              "Books", 24, 49),
    ("The Lean Startup",        "Books", 14, 29),
    ("Designing Data Systems",  "Books", 34, 69),
    ("Deep Work",               "Books", 14, 27),
    ("Zero to One",             "Books", 14, 26),
    ("The Pragmatic Programmer","Books", 35, 59),
]
grocery_items = [
    ("Single-Origin Coffee Beans 1kg", "Grocery", 18, 45),
    ("Extra Virgin Olive Oil 500ml",   "Grocery", 12, 35),
    ("Premium Mixed Nuts 500g",        "Grocery", 14, 28),
    ("Artisan Pasta Selection",        "Grocery", 8, 22),
    ("Matcha Green Tea 100g",          "Grocery", 16, 42),
    ("72% Dark Chocolate Box",         "Grocery", 9, 28),
    ("Organic Honey Variety Pack",     "Grocery", 18, 38),
]

brands_by_cat = {
    "Electronics": ["Acme Tech", "Hooli", "Stark Electronics", "Wayne Systems", "Globex"],
    "Apparel":     ["Acme Style", "Globex Fashion", "Umbrella Co.", "Initech Wear"],
    "Home":        ["Hooli Home", "Acme Living", "Stark Appliances", "Pied Piper"],
    "Beauty":      ["Acme Beauty", "Globex Glow", "Umbrella Skin", "Wayne & Co."],
    "Sports":      ["Acme Sport", "Hooli Fit", "Stark Active", "Initech Pro"],
    "Books":       ["O'Acme Press", "Globex Publishing", "Stark Books"],
    "Grocery":     ["Acme Foods", "Globex Organic", "Umbrella Pantry", "Soylent"],
}

all_items = (electronics_items + apparel_items + home_items +
             beauty_items + sports_items + books_items + grocery_items)

pid = 0
for item_name, cat, p_min, p_max in all_items:
    for brand in brands_by_cat[cat]:
        price = round(random.uniform(p_min, p_max), 2)
        _catalog.append((
            f"P{pid:05d}",
            f"{brand} {item_name}",
            cat,
            f"{cat}-{item_name.split()[0]}",
            brand,
            price,
            random.random() > 0.08,
        ))
        pid += 1
        if pid >= 200:
            break
    if pid >= 200:
        break

# Pad to 200 if needed
while pid < 200:
    _catalog.append((f"P{pid:05d}", f"Acme General Item {pid}", "Home", "Home-General", "Acme", round(random.uniform(10, 200), 2), True))
    pid += 1

products_df = spark.createDataFrame(
    _catalog,
    "product_id STRING, name STRING, category STRING, subcategory STRING, brand STRING, price DOUBLE, in_stock BOOLEAN"
)
(products_df.write.mode("overwrite")
    .option("delta.enableChangeDataFeed", "true")
    .saveAsTable("products"))
print(f"products: {products_df.count()} rows")

# COMMAND ----------

# MAGIC %md ## Customers (10k rows) — weighted segments, correlated LTV, bell-curve age

# COMMAND ----------

from pyspark.sql import functions as F

# Larger, more realistic name pools
first_names = [
    "James", "Oliver", "Emma", "Sophia", "Noah", "Liam", "Ava", "Isabella",
    "Ethan", "Lucas", "Mia", "Charlotte", "Aiden", "Mason", "Amelia", "Harper",
    "Raj", "Priya", "Arjun", "Divya", "Wei", "Mei", "Kenji", "Yuki",
    "Carlos", "Maria", "Luis", "Sofia", "Ahmed", "Fatima", "Omar", "Aisha",
    "Thomas", "Anna", "Pierre", "Claire", "Ravi", "Deepa", "Vikram", "Pooja",
    "Daniel", "Emily", "Michael", "Jessica", "David", "Sarah", "Matthew", "Ashley",
]
last_names = [
    "Smith", "Patel", "Garcia", "Chen", "Kumar", "Brown", "Davis", "Wilson",
    "Anderson", "Lee", "Singh", "Khan", "Lopez", "Murphy", "Cohen", "Nguyen",
    "Taylor", "Martin", "Jackson", "White", "Harris", "Thompson", "Moore", "Clark",
    "Rodriguez", "Lewis", "Walker", "Hall", "Allen", "Young", "Scott", "King",
    "Wright", "Torres", "Hill", "Green", "Adams", "Baker", "Nelson", "Carter",
    "Mitchell", "Perez", "Roberts", "Turner", "Phillips", "Campbell", "Parker", "Evans",
]
# Country distribution: US-heavy, then EMEA, APAC
countries_weighted = [
    "US", "US", "US", "US", "US", "US", "US",   # 35%
    "GB", "GB", "GB",                             # 15%
    "IN", "IN", "IN",                             # 15%
    "DE", "DE",                                   # 10%
    "FR", "FR",                                   # 10%
    "CA",                                         # 5%
    "AU",                                         # 5%
    "JP",                                         # 3%
    "BR",                                         # 2%
]
cities_by_country = {
    "US": ["New York", "San Francisco", "Austin", "Chicago", "Seattle", "Boston", "Miami", "Denver"],
    "GB": ["London", "Manchester", "Birmingham", "Edinburgh", "Bristol"],
    "IN": ["Bangalore", "Mumbai", "Delhi", "Hyderabad", "Pune", "Chennai"],
    "DE": ["Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne"],
    "FR": ["Paris", "Lyon", "Marseille", "Toulouse", "Nice"],
    "CA": ["Toronto", "Vancouver", "Montreal", "Calgary"],
    "AU": ["Sydney", "Melbourne", "Brisbane", "Perth"],
    "JP": ["Tokyo", "Osaka", "Kyoto", "Yokohama"],
    "BR": ["São Paulo", "Rio de Janeiro", "Brasília", "Curitiba"],
}
all_cities = [c for cs in cities_by_country.values() for c in cs]

customers_df = (
    spark.range(10000).withColumnRenamed("id", "cid")
    .withColumn("customer_id", F.format_string("C%07d", F.col("cid")))
    .withColumn("first_name", F.element_at(
        F.array(*[F.lit(n) for n in first_names]),
        (F.col("cid") % len(first_names) + 1).cast("int")))
    .withColumn("last_name", F.element_at(
        F.array(*[F.lit(n) for n in last_names]),
        ((F.col("cid") * 7 + 3) % len(last_names) + 1).cast("int")))
    .withColumn("email", F.concat(
        F.lower(F.col("first_name")), F.lit("."),
        F.lower(F.col("last_name")), F.col("cid").cast("string"),
        F.lit("@example.com")))
    .withColumn("country", F.element_at(
        F.array(*[F.lit(c) for c in countries_weighted]),
        (F.col("cid") % len(countries_weighted) + 1).cast("int")))
    .withColumn("city", F.element_at(
        F.array(*[F.lit(c) for c in all_cities]),
        ((F.col("cid") * 11) % len(all_cities) + 1).cast("int")))
    # Age: bell-curve around 35 (base 22, skew toward middle)
    .withColumn("age", (
        F.rand(seed=10) * 20 + F.rand(seed=11) * 20 + 18).cast("int"))
    .withColumn("gender", F.when(F.rand(seed=12) > 0.48, "F")
                          .when(F.rand(seed=12) > 0.02, "M")
                          .otherwise("Non-binary"))
    .withColumn("signup_date", F.date_sub(
        F.current_date(), (F.rand(seed=13) * 1825).cast("int")))  # up to 5 years
    # Weighted segment assignment: Champions 12%, Loyal 18%, Potential 15%,
    # New 8%, At Risk 13%, Hibernating 20%, Price Sensitive 10%, Churn 4%
    .withColumn("r_seg", F.rand(seed=98))
    .withColumn("segment_id",
        F.when(F.col("r_seg") < 0.12, "S1")
        .when(F.col("r_seg") < 0.30, "S2")
        .when(F.col("r_seg") < 0.45, "S3")
        .when(F.col("r_seg") < 0.53, "S4")
        .when(F.col("r_seg") < 0.66, "S5")
        .when(F.col("r_seg") < 0.86, "S6")
        .when(F.col("r_seg") < 0.96, "S7")
        .otherwise("S8"))
    .drop("r_seg")
    # LTV correlated with segment — ANOMALY: Champions boosted, VIP outliers
    .withColumn("lifetime_value", F.round(
        F.when(F.col("cid") % 200 == 0,
               F.rand(seed=90) * 30000 + 40000)            # ~50 VIP outliers: $40k–$70k
        .when(F.col("segment_id") == "S1",
               F.rand(seed=14) * 17000 + 8000)             # Champions: $8k–$25k
        .when(F.col("segment_id") == "S2",
               F.rand(seed=14) * 5000 + 3000)              # Loyal: $3k–$8k
        .when(F.col("segment_id") == "S3",
               F.rand(seed=14) * 1500 + 1000)              # Potential: $1k–$2.5k
        .when(F.col("segment_id") == "S4",
               F.rand(seed=14) * 400 + 50)                 # New: $50–$450
        .when(F.col("segment_id") == "S5",
               F.rand(seed=14) * 6000 + 2000)              # At Risk: $2k–$8k
        .when(F.col("segment_id") == "S6",
               F.rand(seed=14) * 300 + 50)                 # Hibernating: $50–$350
        .when(F.col("segment_id") == "S7",
               F.rand(seed=14) * 1000 + 200)               # Price Sensitive: $200–$1.2k
        .otherwise(F.rand(seed=14) * 500 + 100), 2))       # About to Churn: $100–$600
    .withColumn("last_purchase_date", F.date_sub(
        F.current_date(), (F.rand(seed=15) * 400).cast("int")))
    # Churn score correlated with segment — ANOMALY: S8 cluster at 0.82–0.97
    .withColumn("churn_score", F.round(
        F.when(F.col("segment_id") == "S8",
               F.rand(seed=16) * 0.15 + 0.82)             # About to Churn: 0.82–0.97
        .when(F.col("segment_id") == "S1",
               F.rand(seed=16) * 0.15)                     # Champions: 0.0–0.15
        .when(F.col("segment_id") == "S2",
               F.rand(seed=16) * 0.25 + 0.05)              # Loyal: 0.05–0.30
        .when(F.col("segment_id") == "S5",
               F.rand(seed=16) * 0.30 + 0.45)              # At Risk: 0.45–0.75
        .when(F.col("segment_id") == "S6",
               F.rand(seed=16) * 0.30 + 0.40)              # Hibernating: 0.40–0.70
        .otherwise(F.rand(seed=16) * 0.45 + 0.15), 3))    # Others: 0.15–0.60
    .withColumn("phone", F.concat(
        F.lit("+1-"),
        F.lpad(((F.col("cid") * 31) % 10000).cast("string"), 4, "0"),
        F.lit("-"),
        F.lpad(((F.col("cid") * 17) % 10000).cast("string"), 4, "0")))
    .withColumn("updated_at", F.current_timestamp())
    .drop("cid")
)
(customers_df.write.mode("overwrite")
    .option("delta.enableChangeDataFeed", "true")
    .saveAsTable("customers"))
print("customers: 10,000 rows")

# COMMAND ----------

# MAGIC %md ## Transactions (100k rows) — seasonal distribution, category-priced amounts
# MAGIC
# MAGIC Date distribution: 40% Q4 2025 (holiday peak), 35% Q1 2026, 25% recent 30 days.
# MAGIC Amount = product price ± 20% variation.

# COMMAND ----------

# Build a product price lookup to join — Electronics avg ~$500, Books avg ~$35
products_lookup = spark.table("products").select("product_id", "price", "category")

txns_df = (
    spark.range(100000).withColumnRenamed("id", "tid")
    .withColumn("transaction_id", F.format_string("T%08d", F.col("tid")))
    .withColumn("customer_id", F.format_string("C%07d",
        (F.col("tid") % 10000).cast("long")))
    .withColumn("product_id", F.format_string("P%05d",
        ((F.col("tid") * 13) % 200).cast("long")))
    # Seasonal date distribution
    .withColumn("r_d", F.rand(seed=20))
    .withColumn("transaction_date",
        F.when(F.col("r_d") < 0.40,   # Q4 2025: holiday season peak (Oct–Dec)
               F.date_sub(F.current_date(), (F.rand(seed=41) * 90 + 122).cast("int")))
        .when(F.col("r_d") < 0.75,    # Q1 2026: Jan–Mar
               F.date_sub(F.current_date(), (F.rand(seed=42) * 90 + 32).cast("int")))
        .otherwise(                    # Recent 30 days
               F.date_sub(F.current_date(), (F.rand(seed=43) * 30).cast("int"))))
    .drop("r_d")
    .withColumn("channel", F.element_at(
        F.array(F.lit("web"), F.lit("mobile"), F.lit("store"), F.lit("partner")),
        # web 45%, mobile 30%, store 18%, partner 7%
        F.when(F.rand(seed=25) < 0.45, F.lit(1))
        .when(F.rand(seed=25) < 0.75, F.lit(2))
        .when(F.rand(seed=25) < 0.93, F.lit(3))
        .otherwise(F.lit(4))))
    .withColumn("status",
        F.when(F.rand(seed=26) < 0.03, "refunded")
        .when(F.rand(seed=26) < 0.05, "pending")
        .otherwise("completed"))
    .drop("tid")
)

# Join to product prices so amounts reflect real category pricing
txns_df = (
    txns_df
    .join(products_lookup, "product_id", "left")
    .withColumn("amount", F.round(
        F.col("price") * (F.rand(seed=21) * 0.40 + 0.80), 2))   # price ±20%
    .drop("price", "category")
)

# ANOMALY: 600 extra high-value completed Electronics transactions in last 3 weeks
# Electronics products: pid % 7 == 0 → P00000, P00007, P00014, ... P00196
spike_txns = (
    spark.range(600).withColumnRenamed("id", "sid")
    .withColumn("transaction_id", F.format_string("TS%07d", F.col("sid")))
    .withColumn("customer_id",    F.format_string("C%07d", (F.col("sid") % 10000).cast("long")))
    .withColumn("product_id",     F.format_string("P%05d", ((F.col("sid") % 28) * 7).cast("long")))
    .withColumn("transaction_date", F.date_sub(F.current_date(),
        (F.rand(seed=77) * 21).cast("int")))
    .withColumn("channel",  F.lit("web"))
    .withColumn("status",   F.lit("completed"))
    .drop("sid")
    .join(products_lookup, "product_id", "left")
    .withColumn("amount", F.round(F.col("price") * (F.rand(seed=78) * 0.3 + 1.1), 2))  # 10–40% premium
    .drop("price", "category")
)

(txns_df.union(spike_txns).write.mode("overwrite")
    .option("delta.enableChangeDataFeed", "true")
    .saveAsTable("transactions"))
print("transactions: 100,600 rows")

# COMMAND ----------

# MAGIC %md ## Support tickets (20k rows) — meaningful subjects, CSAT correlated with priority

# COMMAND ----------

ticket_subjects_by_cat = {
    "billing":        ["Payment declined at checkout", "Charged twice for same order",
                       "Incorrect amount billed", "Subscription renewal issue",
                       "Refund not received after 10 days", "Invoice shows wrong address"],
    "shipping":       ["Package not delivered", "Tracking number not updating",
                       "Wrong item delivered", "Delivery to wrong address",
                       "Package arrived damaged", "Missing item from shipment"],
    "product_defect": ["Item stopped working after 2 weeks", "Product arrived broken",
                       "Missing parts in the box", "Quality does not match description",
                       "Battery drains too fast", "Screen has dead pixels"],
    "account":        ["Cannot log into account", "Two-factor auth not working",
                       "Password reset email not received", "Account locked after failed logins",
                       "Profile data not saving", "Email address change not working"],
    "returns":        ["Return label not received", "Refund still pending after return",
                       "Return window expired but item is defective", "Cannot initiate return",
                       "Return tracking shows delivered but no refund", "Wrong item sent back"],
    "technical":      ["App crashes on launch", "Website not loading on mobile",
                       "Checkout page freezing", "Cannot upload profile picture",
                       "Search not returning results", "Notifications not working"],
}
all_subjects = [(cat, subj) for cat, subjs in ticket_subjects_by_cat.items() for subj in subjs]
categories_t = list(ticket_subjects_by_cat.keys())   # 6 categories
priorities    = ["low", "medium", "high", "urgent"]
statuses      = ["open", "in_progress", "resolved", "closed"]

tickets_df = (
    spark.range(20000).withColumnRenamed("id", "tkid")
    .withColumn("ticket_id",   F.format_string("TK%07d", F.col("tkid")))
    .withColumn("customer_id", F.format_string("C%07d",
        (F.col("tkid") % 10000).cast("long")))
    # Tickets span 12 months (not just 90 days)
    .withColumn("opened_at",   F.date_sub(F.current_date(),
        (F.rand(seed=30) * 365).cast("int")))
    .withColumn("category",    F.element_at(
        F.array(*[F.lit(c) for c in categories_t]),
        ((F.col("tkid") * 3 + 1) % len(categories_t) + 1).cast("int")))
    # Priority: low 30%, medium 40%, high 22%, urgent 8%
    .withColumn("r_p", F.rand(seed=31))
    .withColumn("priority",
        F.when(F.col("r_p") < 0.30, "low")
        .when(F.col("r_p") < 0.70, "medium")
        .when(F.col("r_p") < 0.92, "high")
        .otherwise("urgent"))
    .drop("r_p")
    # Status: open 15%, in_progress 10%, resolved 45%, closed 30%
    .withColumn("r_s", F.rand(seed=32))
    .withColumn("status",
        F.when(F.col("r_s") < 0.15, "open")
        .when(F.col("r_s") < 0.25, "in_progress")
        .when(F.col("r_s") < 0.70, "resolved")
        .otherwise("closed"))
    .drop("r_s")
    .withColumn("closed_at",
        F.when(F.col("status").isin("resolved", "closed"),
               F.date_add(F.col("opened_at"),
                   F.when(F.col("priority") == "urgent", (F.rand(seed=33) * 2 + 1).cast("int"))
                    .when(F.col("priority") == "high",   (F.rand(seed=33) * 5 + 1).cast("int"))
                    .when(F.col("priority") == "medium", (F.rand(seed=33) * 10 + 2).cast("int"))
                    .otherwise((F.rand(seed=33) * 20 + 3).cast("int")))))
    .withColumn("channel", F.element_at(
        F.array(F.lit("email"), F.lit("chat"), F.lit("phone"), F.lit("portal")),
        ((F.col("tkid") * 7 + 2) % 4 + 1).cast("int")))
    # CSAT correlated with priority: urgent resolved → low CSAT (1-3); low priority → high (3-5)
    .withColumn("csat_score",
        F.when(F.col("status").isin("resolved", "closed"),
            F.when(F.col("priority") == "urgent", (F.rand(seed=34) * 2 + 1).cast("int"))
            .when(F.col("priority") == "high",   (F.rand(seed=34) * 3 + 2).cast("int"))
            .when(F.col("priority") == "medium", (F.rand(seed=34) * 3 + 2).cast("int"))
            .otherwise((F.rand(seed=34) * 2 + 3).cast("int"))))
    # Meaningful subject based on category index
    .withColumn("subject_idx",  ((F.col("tkid") * 5 + 1) % 6).cast("int"))
    .withColumn("subject", F.concat(
        F.element_at(
            F.array(*[F.lit(s) for _, s in all_subjects]),
            ((F.col("tkid") * 7) % len(all_subjects) + 1).cast("int")),
        F.lit(" ["), F.col("ticket_id"), F.lit("]")))
    .drop("subject_idx", "tkid")
)

# ANOMALY: 500 extra urgent billing tickets 50-55 days ago — billing system outage
spike_tickets = (
    spark.range(500).withColumnRenamed("id", "spid")
    .withColumn("ticket_id",   F.format_string("TKS%06d", F.col("spid")))
    .withColumn("customer_id", F.format_string("C%07d", (F.col("spid") % 10000).cast("long")))
    .withColumn("opened_at",   F.date_sub(F.current_date(),
        (F.rand(seed=55) * 5 + 50).cast("int")))
    .withColumn("category",  F.lit("billing"))
    .withColumn("priority",  F.lit("urgent"))
    .withColumn("status",    F.when(F.rand(seed=56) > 0.40, F.lit("resolved")).otherwise(F.lit("open")))
    .withColumn("closed_at", F.when(F.rand(seed=57) > 0.40,
        F.date_add(F.col("opened_at"), (F.rand(seed=58) * 10 + 1).cast("int"))))
    .withColumn("channel",   F.lit("email"))
    .withColumn("csat_score", F.when(F.rand(seed=59) > 0.15,
        (F.rand(seed=60) * 1.5 + 1.0).cast("int")))    # CSAT 1-2 — very unhappy
    .withColumn("subject",   F.concat(
        F.lit("BILLING OUTAGE: Cannot process payment — order stuck [TKS"),
        F.col("spid").cast("string"), F.lit("]")))
    .drop("spid")
)

(tickets_df.union(spike_tickets).write.mode("overwrite")
    .option("delta.enableChangeDataFeed", "true")
    .saveAsTable("support_tickets"))
print("support_tickets: 20,500 rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Anomalies baked into the data
# MAGIC
# MAGIC | Anomaly | Where visible on dashboard |
# MAGIC |---|---|
# MAGIC | ~50 VIP customers with LTV $40k–$70k | Champions bar towers above others |
# MAGIC | S8 churn_score 0.82–0.97 (others max 0.75) | Histogram spike at 0.8-0.9 bucket |
# MAGIC | Electronics adds 600 high-value txns in last 21 days | Electronics dominates Top Products |
# MAGIC | 500 urgent billing tickets at days 50–55 | Clear spike in billing line on timeseries |

# COMMAND ----------

# MAGIC %md ## Validation

# COMMAND ----------

for tbl in ["customer_segments", "products", "customers", "transactions", "support_tickets"]:
    n = spark.table(tbl).count()
    print(f"{CATALOG}.{SCHEMA}.{tbl}: {n:,} rows")

# Spot-check anomalies
print("\n--- Anomaly spot checks ---")
print("S8 avg churn:", spark.sql(f"SELECT ROUND(AVG(churn_score),3) FROM {CATALOG}.{SCHEMA}.customers WHERE segment_id='S8'").collect()[0][0])
print("S1 avg churn:", spark.sql(f"SELECT ROUND(AVG(churn_score),3) FROM {CATALOG}.{SCHEMA}.customers WHERE segment_id='S1'").collect()[0][0])
print("S1 avg LTV:  ", spark.sql(f"SELECT ROUND(AVG(lifetime_value),0) FROM {CATALOG}.{SCHEMA}.customers WHERE segment_id='S1'").collect()[0][0])
print("VIP count (LTV>40k):", spark.sql(f"SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.customers WHERE lifetime_value>40000").collect()[0][0])
print("Billing spike tickets (50-55d ago):", spark.sql(
    f"SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.support_tickets "
    f"WHERE category='billing' AND opened_at BETWEEN current_date()-56 AND current_date()-49").collect()[0][0])
print("Electronics txn revenue (last 21d):", spark.sql(
    f"SELECT ROUND(SUM(t.amount),0) FROM {CATALOG}.{SCHEMA}.transactions t "
    f"JOIN {CATALOG}.{SCHEMA}.products p ON t.product_id=p.product_id "
    f"WHERE p.category='Electronics' AND t.transaction_date>=current_date()-21 AND t.status='completed'").collect()[0][0])

# COMMAND ----------

print("CAPSTONE_CATALOG=" + CATALOG)
print("CAPSTONE_SCHEMA="  + SCHEMA)

# COMMAND ----------

# Structured output for the curl-installer (parsed via jobs.get_run_output)
import json
dbutils.notebook.exit(json.dumps({
    "CAPSTONE_CATALOG": CATALOG,
    "CAPSTONE_SCHEMA": SCHEMA,
}))
