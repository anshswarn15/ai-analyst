"""Generate the sample datasets in data/sample/ (deterministic, seed=42).

Planted on purpose so the app has something to find:
  * a handful of extreme quantities / revenues      -> statistical outliers
  * one negative revenue (a refund)                 -> data-quality flag
  * duplicated order rows, missing regions          -> data-quality flags
  * 'north ' / 'NORTH' spelling variants            -> inconsistent categories
  * 3 products with very low demand                 -> "underperforming products"
"""
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
out = Path(__file__).resolve().parent.parent / "data" / "sample"
out.mkdir(parents=True, exist_ok=True)

# ---- products -----------------------------------------------------------------------------
catalog = [
    ("Laptop Pro 14", "Electronics", 1299, 0.8), ("Wireless Mouse", "Electronics", 29, 1.6),
    ("Mechanical Keyboard", "Electronics", 99, 1.1), ("4K Monitor", "Electronics", 399, 0.9),
    ("Noise-Cancel Headphones", "Electronics", 249, 1.0), ("USB-C Hub", "Electronics", 45, 1.3),
    ("Ergonomic Chair", "Furniture", 349, 0.7), ("Standing Desk", "Furniture", 549, 0.6),
    ("Bookshelf", "Furniture", 129, 0.5), ("Desk Lamp", "Furniture", 39, 1.2),
    ("Notebook 3-pack", "Stationery", 12, 1.8), ("Gel Pens 12-pack", "Stationery", 9, 1.7),
    ("Planner 2025", "Stationery", 19, 0.9), ("Whiteboard", "Stationery", 59, 0.4),
    ("Coffee Beans 1kg", "Grocery", 24, 1.5), ("Green Tea Box", "Grocery", 14, 1.0),
    ("Protein Bars 24", "Grocery", 32, 0.9),
    ("Fax Machine", "Electronics", 189, 0.08), ("CD Organizer", "Furniture", 25, 0.07),
    ("Floppy Disks 10-pack", "Electronics", 15, 0.05),
]
products = pd.DataFrame({
    "product_id": [f"P{100 + i}" for i in range(len(catalog))],
    "product_name": [c[0] for c in catalog], "category": [c[1] for c in catalog],
    "unit_price": [c[2] for c in catalog],
    "unit_cost": [round(c[2] * rng.uniform(0.55, 0.75), 2) for c in catalog],
})
weights = np.array([c[3] for c in catalog]); weights = weights / weights.sum()

# ---- customers ----------------------------------------------------------------------------
first = ["Aarav", "Priya", "Liam", "Emma", "Noah", "Olivia", "Mateo", "Sofia", "Yuki", "Chen", "Fatima", "Omar",
         "Hannah", "Lucas", "Isha", "Rohan", "Zara", "Ethan", "Mia", "Arjun"]
last = ["Sharma", "Patel", "Smith", "Johnson", "Garcia", "Kim", "Tanaka", "Khan", "Müller", "Brown", "Singh", "Lopez"]
n_cust = 120
customers = pd.DataFrame({
    "customer_id": [f"C{1000 + i}" for i in range(n_cust)],
    "customer_name": [f"{rng.choice(first)} {rng.choice(last)}" for _ in range(n_cust)],
    "segment": rng.choice(["Consumer", "Corporate", "Small Business"], n_cust, p=[0.5, 0.2, 0.3]),
    "country": rng.choice(["India", "UK", "USA", "Germany"], n_cust, p=[0.3, 0.25, 0.3, 0.15]),
    "signup_date": pd.to_datetime("2023-01-01") + pd.to_timedelta(rng.integers(0, 700, n_cust), unit="D"),
})
customers["signup_date"] = customers["signup_date"].dt.strftime("%Y-%m-%d")
region_of = {"India": "South", "UK": "North", "USA": "West", "Germany": "East"}
cust_weight = rng.pareto(1.6, n_cust) + 0.3; cust_weight /= cust_weight.sum()

# ---- sales (one row per order line) --------------------------------------------------------
n = 2400
months = pd.date_range("2024-01-01", "2025-12-01", freq="MS")
m_w = np.array([1 + 0.025 * i + (0.35 if m.month in (11, 12) else 0) for i, m in enumerate(months)]); m_w /= m_w.sum()
month = rng.choice(len(months), n, p=m_w)
dates = [months[m] + pd.Timedelta(days=int(rng.integers(0, 28))) for m in month]
cust_idx = rng.choice(n_cust, n, p=cust_weight)
prod_idx = rng.choice(len(catalog), n, p=weights)
qty = rng.choice([1, 2, 3, 4, 5], n, p=[0.45, 0.28, 0.15, 0.08, 0.04])
disc = rng.choice([0, 0, 0, 0.05, 0.1, 0.2], n)
unit_price = products["unit_price"].to_numpy()[prod_idx]
region = [region_of[customers.loc[i, "country"]] for i in cust_idx]
sales = pd.DataFrame({
    "order_id": [f"O{50000 + i}" for i in range(n)],
    "order_date": [d.strftime("%Y-%m-%d") for d in dates],
    "customer_id": customers["customer_id"].to_numpy()[cust_idx],
    "product_id": products["product_id"].to_numpy()[prod_idx],
    "region": region, "quantity": qty, "unit_price": unit_price, "discount": disc,
})
sales["revenue"] = (sales.quantity * sales.unit_price * (1 - sales.discount)).round(2)
sales = sales.sort_values("order_date").reset_index(drop=True)

# ---- planted problems ---------------------------------------------------------------------
cheap = sales.index[sales.unit_price <= 20].to_numpy()      # cheap items keep monthly trends readable
for i, q in zip(cheap[[5, 150, 300]], [600, 900, 450]):      # absurd quantities
    sales.loc[i, "quantity"] = q
    sales.loc[i, "revenue"] = round(q * sales.loc[i, "unit_price"] * (1 - sales.loc[i, "discount"]), 2)
sales.loc[cheap[200], "revenue"] = 9500.0                      # typo-sized revenue
sales.loc[300, "revenue"] = -89.0                             # refund
sales.loc[[10, 11, 12, 600, 1900], "region"] = np.nan          # missing region
sales.loc[[20, 21], "region"] = "north "                       # spelling variants
sales.loc[[22, 23], "region"] = "NORTH"
sales = pd.concat([sales, sales.iloc[[5, 6, 7]]], ignore_index=True)  # duplicate rows

sales.to_csv(out / "sales.csv", index=False)
customers.to_csv(out / "customers.csv", index=False)
products.to_csv(out / "products.csv", index=False)
print("wrote", [p.name for p in out.glob("*.csv")], "sales rows:", len(sales))
