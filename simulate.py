"""
Phase 1 · simulate.py
Online engine: given a city + 3 slider values, roll a 180-day ROE trajectory.
Pure numpy, vectorised, deterministic given the sampled coefficients. No LLM.

Causal chain (thin Phase-1 slice):
  price_change ──(β elasticity)──► volume ─┐
  demand_shift ──(additive aᵢ proxy)──────►├─► revenue ─┐
  lithium_shock ─(γ, decays)──► unit_cost ─────────────►├─► profit ─► ROE run-rate
  maturity stage ──────────────► volume drift over horizon ┘

Monte-Carlo: β and γ are sampled from N(value, std_err) written by calibration.py,
so the ROE ray comes with a p5–p95 confidence band, not a false point line.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np

ROOT     = Path(__file__).resolve().parent
CFG_PATH = ROOT / "simulation_config.json"

# maturity stage per quadrant (audit log §B4): growth rises, harvest stays low-flat
STAGE = {"Q1": "growth", "Q2": "mature", "Q3": "harvest", "Q4": "harvest"}
STAGE_SLOPE = {"growth": 0.25, "mature": 0.05, "harvest": -0.02}  # vol drift over horizon


def load_config(path: Path = CFG_PATH) -> dict:
    return json.load(open(path, encoding="utf-8"))


def simulate_roe(city: str, sliders: dict, config: dict,
                 horizon: int = 180, n_mc: int = 300,
                 shock_half_life: int = 60, seed: int = 620) -> dict:
    """
    sliders = {"price_change": %, "lithium_shock": %, "demand_shift": %}
    Returns days + ROE band (p05/p50/p95, annualised run-rate) + t0/tH breakdown.
    """
    b   = config["baseline"][city]
    q   = b["quadrant"]
    asp, uc      = b["asp"], b["unit_cost"]
    base_qty     = b["base_qty"]          # annual units
    fixed_cost   = b["fixed_cost"]
    equity       = b["equity"]
    roe_base     = b["roe_base"]

    beta_c  = config["coefficients"]["beta_demand"][q]
    gamma_map = config["coefficients"]["gamma_cost"]
    if city in gamma_map:
        gamma_c = gamma_map[city]
    else:
        # 该区域未恢复出 γ(如 battery 供应数据缺失):退回同象限已恢复区域的均值,
        # 再退回全局均值。保证引擎不因单区域缺系数而崩。
        same_q = [v for k, v in gamma_map.items()
                  if config.get("regions", {}).get(k, {}).get("quadrant") == q]
        pool = same_q if same_q else list(gamma_map.values())
        gamma_c = {"value": float(np.mean([g["value"] for g in pool])),
                   "std_err": float(np.mean([g["std_err"] for g in pool]))}

    # slider values
    dp   = sliders.get("price_change", 0.0) / 100.0      # permanent price move
    lsh  = sliders.get("lithium_shock", 0.0) / 100.0     # lithium %; decays
    dsh  = sliders.get("demand_shift", 0.0) / 100.0      # aᵢ proxy; permanent

    rng = np.random.default_rng(seed)
    beta  = rng.normal(beta_c["value"],  max(beta_c["std_err"], 1e-9),  n_mc)   # (n_mc,)
    gamma = rng.normal(gamma_c["value"], max(gamma_c["std_err"], 1e-9), n_mc)

    t = np.arange(horizon)                                    # (H,)
    decay = np.exp(-np.log(2) * t / shock_half_life)          # shock decay path
    lith_path = lsh * decay                                    # (H,) lithium % over time
    mat_drift = 1.0 + STAGE_SLOPE[STAGE.get(q, "mature")] * (t / horizon)  # maturity ramp

    # broadcast to (n_mc, H)
    B = beta[:, None]; G = gamma[:, None]
    price_mult  = (1.0 + dp) ** B                             # Q/Q0 = (P/P0)^β
    demand_mult = (1.0 + dsh)
    qty_daily   = base_qty / 365.0 * price_mult * demand_mult * mat_drift[None, :]

    price       = asp * (1.0 + dp)
    unit_cost_t = uc * (1.0 + G * lith_path[None, :])         # (n_mc, H)

    revenue = price * qty_daily
    cost    = unit_cost_t * qty_daily + fixed_cost / 365.0
    profit  = revenue - cost
    roe_rr  = profit * 365.0 / equity                         # annualised run-rate (n_mc, H)

    # Phase 2: EBIT run-rate line via a frozen wedge.
    #   wedge = ebit_base − net_base = baseline (interest + tax), held over the horizon.
    #   → ebit_rr = profit·365 + wedge.  At t0 this ≡ ebit_base (operating_income).
    #   Sliders hit price/volume/unit-cost (all above EBIT), so EBIT moves like profit.
    #   Approx: intra-horizon tax-scaling of the wedge is frozen; financials re-applies
    #   tax cleanly via NOPAT=EBIT·(1−tax). Documented in Phase 2 audit log.
    ebit_base = b.get("ebit_base")
    if ebit_base is not None:
        wedge   = float(ebit_base) - roe_base * equity        # baseline interest+tax
        ebit_rr = profit * 365.0 + wedge                      # (n_mc, H) annualised EBIT
        e05, e50, e95 = np.percentile(ebit_rr, [5, 50, 95], axis=0)
    else:
        e05 = e50 = e95 = None                                # engine still runs w/o Phase 2 fields

    p05, p50, p95 = np.percentile(roe_rr, [5, 50, 95], axis=0)

    def _breakdown(idx):
        return dict(price=float(price),
                    qty_annual=float(np.median(qty_daily[:, idx]) * 365),
                    unit_cost=float(np.median(unit_cost_t[:, idx])),
                    roe=float(np.median(roe_rr[:, idx])))

    return dict(city=city, quadrant=q, stage=STAGE.get(q, "mature"),
                days=t.tolist(), roe_base=roe_base,
                roe_p05=p05.tolist(), roe_p50=p50.tolist(), roe_p95=p95.tolist(),
                roe_delta_end=float(p50[-1] - roe_base),
                # Phase 2: EBIT run-rate band (None if config lacks ebit_base) +
                # baseline balance-sheet items so app.py can call financials.spread_line.
                ebit_p05=(e05.tolist() if e05 is not None else None),
                ebit_p50=(e50.tolist() if e50 is not None else None),
                ebit_p95=(e95.tolist() if e95 is not None else None),
                ebit_base=b.get("ebit_base"),
                interest_bearing_debt=b.get("interest_bearing_debt"),
                cash_and_equivalents=b.get("cash_and_equivalents"),
                shareholders_equity=equity, tax_rate=b.get("tax_rate"),
                breakdown_t0=_breakdown(0), breakdown_tH=_breakdown(horizon - 1),
                beta_used=float(beta_c["value"]), gamma_used=float(gamma_c["value"]))


if __name__ == "__main__":
    cfg = load_config()
    city = next(iter(cfg["baseline"]))
    r = simulate_roe(city, {"price_change": -5, "lithium_shock": 20, "demand_shift": 3}, cfg)
    print(f"city={r['city']}  quadrant={r['quadrant']}  stage={r['stage']}")
    print(f"ROE base            : {r['roe_base']:+.3f}")
    print(f"ROE p50 @ t0        : {r['roe_p50'][0]:+.3f}   (band "
          f"{r['roe_p05'][0]:+.3f}..{r['roe_p95'][0]:+.3f})")
    print(f"ROE p50 @ t180      : {r['roe_p50'][-1]:+.3f}   (band "
          f"{r['roe_p05'][-1]:+.3f}..{r['roe_p95'][-1]:+.3f})")
    print(f"ΔROE end vs base    : {r['roe_delta_end']:+.3f}")
    print(f"β used {r['beta_used']:.3f} · γ used {r['gamma_used']:.3f}")
