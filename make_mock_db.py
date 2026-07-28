"""
TEST HARNESS ONLY — not a Phase 1 deliverable.
Rebuilds a small nev.db + ground_truth.json matching the schema/truth documented
in PHASE0_audit_log.md, so calibration.py / simulate.py / app.py can be exercised
end-to-end without the real repo. The real pipeline uses generate_data.py.
"""
import numpy as np, pandas as pd, sqlite3, json
from pathlib import Path

RNG = np.random.default_rng(620)
OUT = Path(__file__).resolve().parent.parent
DB  = OUT / "nev.db"

# ── Regions (audit log §I) : cluster index + primary quadrant ───────────
REGIONS = {
    "Hefei":     (0.85, "Q1"), "Shenzhen": (0.70, "Q2"),
    "Changzhou": (0.60, "Q2"), "Shanghai": (0.55, "Q1"),
    "Liuzhou":   (0.50, "Q3"), "Xian":     (0.30, "Q4"),
}
# beta truth by quadrant (§B1)
BETA = {"Q1": -1.3, "Q2": -1.1, "Q3": -1.8, "Q4": -2.4}
THETA = {"Q1": 0.4, "Q2": 0.4, "Q3": 0.25, "Q4": 0.1}
# gamma truth: high cluster -> low cost-transmission rigidity (§B1: 0.35 high, 0.78 low)
def gamma_of(cluster):  # linear map cluster[0.30..0.85] -> gamma[0.78..0.35]
    return round(0.78 + (0.35 - 0.78) * (cluster - 0.30) / (0.85 - 0.30), 4)
GAMMA = {r: gamma_of(c) for r, (c, q) in REGIONS.items()}

DATES = pd.date_range("2023-01-01", periods=1095, freq="D")

# ── macro_shocks_log : lithium AR(1) mean-revert mu=100 phi=0.98 ────────
lith = np.empty(len(DATES)); lith[0] = 100.0
for t in range(1, len(DATES)):
    lith[t] = 100 + 0.98 * (lith[t-1] - 100) + RNG.normal(0, 2.5)
rate = 3.0 + np.cumsum(RNG.normal(0, 0.01, len(DATES)))
carbon = 60 + 0.6*(lith-100) + RNG.normal(0, 3, len(DATES))
macro = pd.DataFrame({"date": DATES, "lithium_price_index": lith,
                      "macro_interest_rate": rate, "carbon_credit_price": carbon})

# ── model_dim : 2-3 models per region-quadrant ─────────────────────────
models, mid = [], 0
for r, (cl, q) in REGIONS.items():
    for k in range(RNG.integers(2, 4)):
        mid += 1
        list_price = {"Q1": 32, "Q2": 30, "Q3": 18, "Q4": 6}[q] * (1 + RNG.normal(0, .08))
        batt = {"Q1": 4, "Q2": 5, "Q3": 9, "Q4": 1}[q] + RNG.normal(0, 1)
        models.append(dict(model_id=mid, model_name=f"{r[:3]}-M{k+1}", region=r, quadrant=q,
                           list_price=round(list_price*1e4, 1),
                           batt_dev=float(np.clip(batt,0,10)),
                           adas_dev=float(np.clip({"Q1":7,"Q2":6,"Q3":4,"Q4":1}[q]+RNG.normal(0,1),0,10)),
                           chip_dev=float(np.clip({"Q1":6,"Q2":5,"Q3":4,"Q4":1}[q]+RNG.normal(0,1),0,10))))
model_dim = pd.DataFrame(models)
model_dim["rd_score_display"] = (0.5*model_dim.batt_dev + 0.3*model_dim.adas_dev
                                 + 0.2*model_dim.chip_dev).round(2)

# ── sales_transactions : ln Q = a + beta*ln P + model_FE + eps ──────────
rows = []
for _, m in model_dim.iterrows():
    q = m.quadrant; b = BETA[q]; fe = RNG.normal(0, 0.15)
    base_lnP = np.log(m.list_price)
    for d in DATES[::3]:                       # every 3rd day -> ~365 obs/model
        promo = RNG.normal(0, 0.06)            # price variation identifies beta
        lnP = base_lnP + promo
        lnQ = 9.5 + b*(lnP - base_lnP) + fe + RNG.normal(0, 0.10)
        rows.append(dict(date=d, region=m.region, quadrant=q, model_id=int(m.model_id),
                         unit_price=round(float(np.exp(lnP)),1),
                         quantity=int(max(1, np.exp(lnQ)))))
sales = pd.DataFrame(rows)

# ── supply_chain_costs : bom = base*(1 + gamma*(lith/100-1)) + eps ──────
sc = []
lith_by_date = dict(zip(macro.date, macro.lithium_price_index))
for r, (cl, q) in REGIONS.items():
    g = GAMMA[r]; base_bom = {"Q1":22,"Q2":21,"Q3":12,"Q4":4.5}[q]*1e4
    for d in DATES[::7]:
        L = lith_by_date[d]
        bom = base_bom*(1 + g*(L/100 - 1)) + RNG.normal(0, base_bom*0.01)
        sc.append(dict(date=d, region=r, quadrant=q, component_type="battery",
                       bom_cost_per_unit=round(bom,1),
                       battery_bom_share=round(float(np.clip(0.45+RNG.normal(0,.03),0,1)),3),
                       lithium_price_index=round(L,2)))
supply = pd.DataFrame(sc)

# ── financial_snapshots : (region,quadrant,period) ─────────────────────
fin = []
for r, (cl, q) in REGIONS.items():
    for period in ["2023", "2024", "2025"]:
        rev = {"Q1":875,"Q2":1123,"Q3":8040,"Q4":300}[q]*1e8*(1+RNG.normal(0,.05))
        nmarg = {"Q1":-0.17,"Q2":0.03,"Q3":0.041,"Q4":0.02}[q]
        ni = rev*nmarg
        eq = {"Q1":66,"Q2":120,"Q3":2621,"Q4":40}[q]*1e8*(1+RNG.normal(0,.05))
        fin.append(dict(region=r, quadrant=q, period=period,
                        automotive_sales_revenue=round(rev,0), net_income=round(ni,0),
                        equity=round(eq,0),
                        invested_capital=round(eq*RNG.uniform(1.2,1.6),0),
                        rd_ratio=round({"Q1":.12,"Q2":.08,"Q3":.079,"Q4":.03}[q],4),
                        selling_expense=round(rev*RNG.uniform(.03,.12),0)))
financial = pd.DataFrame(fin)

# ── regional_infra ─────────────────────────────────────────────────────
infra = pd.DataFrame([dict(region=r, quadrant=q,
                           local_market_size=round(RNG.uniform(2e5,8e5)),
                           local_battery_cluster_index=cl,
                           gov_investment=round(RNG.uniform(.3,.9),2),
                           local_fiscal_capacity=round(RNG.uniform(.3,.9),2),
                           tax_incentive_index=round(RNG.uniform(.2,.8),2))
                      for r,(cl,q) in REGIONS.items()])

# ── write db ───────────────────────────────────────────────────────────
if DB.exists(): DB.unlink()
con = sqlite3.connect(DB)
sales.to_sql("sales_transactions", con, index=False)
macro.assign(date=macro.date.astype(str)).to_sql("macro_shocks_log", con, index=False)
supply.assign(date=supply.date.astype(str)).to_sql("supply_chain_costs", con, index=False)
financial.to_sql("financial_snapshots", con, index=False)
model_dim.to_sql("model_dim", con, index=False)
infra.to_sql("regional_infra", con, index=False)
con.execute("CREATE INDEX ix_sales_rq ON sales_transactions(region,quadrant)")
con.commit(); con.close()

json.dump({"beta_demand": BETA, "gamma_cost": GAMMA, "theta_q": THETA,
           "regions": {r: {"cluster": c, "quadrant": q} for r,(c,q) in REGIONS.items()}},
          open(OUT/"ground_truth.json","w"), indent=2, ensure_ascii=False)

print("mock nev.db written:", {t: len(df) for t,df in
      [("sales",sales),("macro",macro),("supply",supply),
       ("financial",financial),("model_dim",model_dim),("infra",infra)]})
print("gamma truth:", GAMMA)
