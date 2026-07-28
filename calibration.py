"""
Phase 1 · calibration.py
Offline calibration: read nev.db -> recover behavioural coefficients by regression
-> build the parameter-recovery table (β/γ estimate vs埋入真值) -> write the online
engine's config (simulation_config.json).

This is the project's立身之本: it proves the numbers the engine uses were *recovered
from data*, not typed in. No LLM, no RAG — pure statistics.

SCHEMA ASSUMPTIONS (from PHASE0_audit_log.md — verify against your real nev.db):
  sales_transactions(date, region, quadrant, model_id, unit_price, quantity)
  supply_chain_costs(date, region, quadrant, bom_cost_per_unit, lithium_price_index)
  financial_snapshots(region, quadrant, period, automotive_sales_revenue,
                      net_income, equity, invested_capital, rd_ratio, selling_expense)
  model_dim(model_id, region, quadrant, list_price, ...)
  ground_truth.json = {"beta_demand": {Qk: v}, "gamma_cost": {region: v}, ...}
If a column name differs, change it in the two SQL strings below — nothing else.
"""
from __future__ import annotations
import json, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT       = Path(__file__).resolve().parent
DB_PATH    = ROOT / "nev.db"
TRUTH_PATH = ROOT / "ground_truth.json"
CFG_PATH   = ROOT / "simulation_config.json"


# ── data access ─────────────────────────────────────────────────────────
def _read(sql: str, db: Path = DB_PATH) -> pd.DataFrame:
    with sqlite3.connect(db) as con:
        return pd.read_sql(sql, con)


# ── β recovery :  ln Q = α + β·ln P + model fixed effects ────────────────
def recover_beta(db: Path = DB_PATH) -> pd.DataFrame:
    """One own-price elasticity per quadrant, with model_id fixed effects
    (FE absorb cross-model level differences so β is identified off within-model
    price variation, not the Q1-vs-Q4 price gap). Returns tidy table."""
    df = _read("SELECT quadrant, model_id, unit_price, quantity "
               "FROM sales_transactions WHERE unit_price>0 AND quantity>0", db)
    df["lnP"] = np.log(df.unit_price)
    df["lnQ"] = np.log(df.quantity)
    out = []
    for q, g in df.groupby("quadrant"):
        # need >1 model for FE; fall back to plain OLS if only one
        formula = "lnQ ~ lnP + C(model_id)" if g.model_id.nunique() > 1 else "lnQ ~ lnP"
        res = smf.ols(formula, data=g).fit()
        ci = res.conf_int().loc["lnP"]
        out.append(dict(coefficient="beta_demand", key=q,
                        estimate=res.params["lnP"], ci_low=ci[0], ci_high=ci[1],
                        std_err=res.bse["lnP"], r2=res.rsquared, n=int(res.nobs)))
    return pd.DataFrame(out)


# ── γ recovery :  bom_cost = α + γ·lithium_shock  (per region) ───────────
def recover_gamma(db: Path = DB_PATH) -> pd.DataFrame:
    """Cost-transmission rigidity per region. DGP is level-linear
    bom = base·(1 + γ·(L/100 − 1)) = base·(1−γ) + base·γ·(L/100).
    Regress bom on Lr=L/100  → slope b1 = base·γ, intercept b0 = base·(1−γ),
    so γ = b1/(b0+b1)  (base = b0+b1, unknown, cancels). CI via delta method
    on the ratio using the 2×2 parameter covariance — no preset base needed,
    no attenuation bias."""
    df = _read("SELECT region, bom_cost_per_unit, lithium_price_index "
               "FROM supply_chain_costs WHERE bom_cost_per_unit>0", db)
    out = []
    for r, g in df.groupby("region"):
        g = g.assign(Lr=g.lithium_price_index / 100)
        res = smf.ols("bom_cost_per_unit ~ Lr", data=g).fit()
        b0, b1 = res.params["Intercept"], res.params["Lr"]
        base = b0 + b1
        gamma = b1 / base
        # delta method:  g = b1/(b0+b1);  J = [∂g/∂b0, ∂g/∂b1]
        J = np.array([-b1 / base**2, b0 / base**2])
        cov = res.cov_params().loc[["Intercept", "Lr"], ["Intercept", "Lr"]].values
        se = float(np.sqrt(J @ cov @ J))
        out.append(dict(coefficient="gamma_cost", key=r,
                        estimate=float(gamma), ci_low=gamma - 1.96*se,
                        ci_high=gamma + 1.96*se, std_err=se,
                        r2=res.rsquared, n=int(res.nobs)))
    return pd.DataFrame(out)


# ── recovery table : estimate vs埋入真值, does 95% CI cover? ─────────────
def recovery_table(db: Path = DB_PATH, truth_path: Path = TRUTH_PATH) -> pd.DataFrame:
    truth = json.load(open(truth_path, encoding="utf-8"))
    tab = pd.concat([recover_beta(db), recover_gamma(db)], ignore_index=True)
    tmap = {"beta_demand": truth.get("beta_demand", {}),
            "gamma_cost":  truth.get("gamma_cost", {})}
    tab["truth"] = tab.apply(lambda r: tmap[r.coefficient].get(r.key, np.nan), axis=1)
    tab["covered"] = (tab.truth >= tab.ci_low) & (tab.truth <= tab.ci_high)
    tab["abs_err"] = (tab.estimate - tab.truth).abs()
    cols = ["coefficient", "key", "truth", "estimate", "ci_low", "ci_high",
            "std_err", "covered", "r2", "n"]
    return tab[cols].round(4)


# ── baseline snapshot (latest period per region) for the online engine ───
def _baseline_pack(db: Path = DB_PATH) -> dict:
    fin = _read("SELECT * FROM financial_snapshots", db)
    latest = fin.sort_values("period").groupby("region").tail(1).set_index("region")
    # per-region unit economics from sales + supply (latest year)
    sales = _read("SELECT region, unit_price, quantity FROM sales_transactions", db)
    asp = sales.groupby("region").apply(
        lambda g: np.average(g.unit_price, weights=g.quantity)).to_dict()
    supply = _read("SELECT region, bom_cost_per_unit FROM supply_chain_costs", db)
    unit_cost = supply.groupby("region").bom_cost_per_unit.median().to_dict()

    pack = {}
    for r, row in latest.iterrows():
        rev, ni, eq = float(row.automotive_sales_revenue), float(row.net_income), float(row.equity)
        a, uc = float(asp.get(r, np.nan)), float(unit_cost.get(r, np.nan))
        base_qty = rev / a if a else np.nan
        # back out fixed cost so ROE_base == net_income/equity exactly (engine ties to DB)
        fixed_cost = (a - uc) * base_qty - ni
        pack[r] = dict(quadrant=row.quadrant, asp=a, unit_cost=uc,
                       base_qty=base_qty, fixed_cost=fixed_cost, equity=eq,
                       revenue=rev, net_income=ni, roe_base=ni / eq if eq else np.nan)
    return pack


# ── assemble + write simulation_config.json ──────────────────────────────
def build_config(db: Path = DB_PATH, truth_path: Path = TRUTH_PATH,
                 out: Path = CFG_PATH) -> dict:
    tab   = recovery_table(db, truth_path)
    truth = json.load(open(truth_path, encoding="utf-8"))
    beta  = tab[tab.coefficient == "beta_demand"].set_index("key")
    gamma = tab[tab.coefficient == "gamma_cost"].set_index("key")

    config = {
        "meta": {"source": "calibration.py", "note": "coefficients recovered from nev.db"},
        # recovered coefficients (+ std_err so simulate.py can Monte-Carlo the band)
        "coefficients": {
            "beta_demand":  {q: {"value": float(beta.loc[q, "estimate"]),
                                 "std_err": float(beta.loc[q, "std_err"])}
                             for q in beta.index},
            "gamma_cost":   {r: {"value": float(gamma.loc[r, "estimate"]),
                                 "std_err": float(gamma.loc[r, "std_err"])}
                             for r in gamma.index},
            "theta_q":      truth.get("theta_q", {}),
        },
        "regions": truth.get("regions", {}),
        "baseline": _baseline_pack(db),
    }
    json.dump(config, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    return config


# optional Streamlit cache wrapper (import-safe: no hard dependency at import time)
def cached_config():
    try:
        import streamlit as st
        return st.cache_data(build_config)()
    except Exception:
        if CFG_PATH.exists():
            return json.load(open(CFG_PATH, encoding="utf-8"))
        return build_config()


if __name__ == "__main__":
    tab = recovery_table()
    print("\n=== PARAMETER RECOVERY TABLE ===")
    with pd.option_context("display.width", 120, "display.max_columns", None):
        print(tab.to_string(index=False))
    ok = tab.covered.mean()
    print(f"\nCI covers truth: {tab.covered.sum()}/{len(tab)}  ({ok:.0%})")
    cfg = build_config()
    print(f"✓ wrote {CFG_PATH.name}  ({len(cfg['baseline'])} regions, "
          f"{len(cfg['coefficients']['beta_demand'])} β, "
          f"{len(cfg['coefficients']['gamma_cost'])} γ)")
