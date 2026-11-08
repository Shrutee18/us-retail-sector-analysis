import pandas as pd

w = pd.read_csv("data/clean/retail_financials_wide.csv")
w["gross_margin"] = (w.revenue - w.cost_of_revenue) / w.revenue
w["op_margin"] = w.operating_income / w.revenue
w["net_margin"] = w.net_income / w.revenue
w["inv_turnover"] = w.cost_of_revenue / w.inventory
w["capex_pct"] = w.capex / w.revenue

for col, label in [("gross_margin", "Gross margin (Kroger not comparable)"), ("op_margin", "Operating margin"),
                   ("net_margin", "Net margin"), ("inv_turnover", "Inventory turnover (times a year, year-end inventory)"),
                   ("capex_pct", "Capex as share of revenue")]:
    t = w.pivot(index="calendar_year", columns="ticker", values=col)
    print(f"\n{label}")
    print((t * (100 if col in ("gross_margin", "op_margin", "net_margin", "capex_pct") else 1)).round(1).to_string())
