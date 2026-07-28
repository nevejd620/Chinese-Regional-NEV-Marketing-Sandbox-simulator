"""
NEV 沙盘 Phase 0 · 数据生成 (DGP)
分层生成：A类因果(进回归,纯因果+独立噪声) / B类潜变量画像(截断正态+联合约束)。
会计恒等式收口。产出六张 DataFrame + ground_truth。
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from scipy.stats import truncnorm
import config as C


# ── 工具：截断正态 (B类画像用) ────────────────────────────
def tnorm(lo, hi, mu=None, sigma_frac=0.25, size=1, rng=None):
    """在 [lo,hi] 内抽截断正态；mu 缺省取区间中点，sigma 取区间宽度的 sigma_frac。"""
    if mu is None:
        mu = (lo + hi) / 2
    sigma = (hi - lo) * sigma_frac
    a, b = (lo - mu) / sigma, (hi - mu) / sigma
    return truncnorm.rvs(a, b, loc=mu, scale=sigma, size=size, random_state=rng)


def ar1_path(mu, phi, sigma, n, rng, floor=None):
    """AR(1) 均值回归路径 (A类外生随机过程)。"""
    x = np.empty(n); x[0] = mu
    for t in range(1, n):
        x[t] = mu + phi * (x[t-1] - mu) + rng.normal(0, sigma)
    if floor is not None:
        x = np.maximum(x, floor)
    return x


def build(seed=C.RNG_SEED):
    rng = np.random.default_rng(seed)
    dates = [datetime.fromisoformat(C.START_DATE) + timedelta(days=i) for i in range(C.N_DAYS)]
    date_str = [d.strftime("%Y-%m-%d") for d in dates]
    t_year = np.array([i / 365.0 for i in range(C.N_DAYS)])   # 年进度，用于漂移/maturity

    ground_truth = dict(seed=seed, beta_demand=C.BETA_DEMAND, gamma_base=C.GAMMA_BASE,
                        theta_q=C.THETA_Q, lambda_batt=C.LAMBDA_BATT, gamma_effective={})

    # ═════════ ③-预备：宏观冲击 (A类外生随机过程, 全国日频) ═════════
    m = C.MACRO
    lithium = ar1_path(**m["lithium"], n=C.N_DAYS, rng=rng, floor=40)
    nickel  = ar1_path(**m["nickel"], n=C.N_DAYS, rng=rng, floor=40)
    rare    = ar1_path(**m["rare_earth"], n=C.N_DAYS, rng=rng, floor=40)
    steel   = ar1_path(**m["steel_al"], n=C.N_DAYS, rng=rng, floor=40)
    semi    = ar1_path(**m["semi"], n=C.N_DAYS, rng=rng, floor=40)
    carbon  = ar1_path(**m["carbon"], n=C.N_DAYS, rng=rng, floor=100)
    # 利率：随机游走(截断)
    ir = np.empty(C.N_DAYS); ir[0] = m["interest"]["start"]
    for t in range(1, C.N_DAYS):
        ir[t] = np.clip(ir[t-1] + rng.normal(0, m["interest"]["sigma"]),
                        m["interest"]["lo"], m["interest"]["hi"])
    subsidy = np.linspace(m["subsidy_start"], m["subsidy_end"], C.N_DAYS)
    upstream_policy = np.clip(0.3 + 0.2*np.sin(np.linspace(0, 6, C.N_DAYS)) + rng.normal(0, 0.05, C.N_DAYS), 0, 1)
    inflation = np.clip(ar1_path(mu=0.025, phi=0.99, sigma=0.0004, n=C.N_DAYS, rng=rng), 0.005, 0.06)

    macro_df = pd.DataFrame(dict(
        shock_date=date_str, lithium_price_index=lithium.round(2),
        nickel_cobalt_index=nickel.round(2), rare_earth_index=rare.round(2),
        steel_aluminum_index=steel.round(2), semiconductor_price_index=semi.round(2),
        carbon_credit_price=carbon.round(1), macro_interest_rate=ir.round(5),
        national_subsidy_rate=subsidy.round(4), upstream_policy_index=upstream_policy.round(3),
        inflation_index=inflation.round(4),
    ))

    # ═════════ model_dim (B类画像, 事件驱动) ═════════
    model_rows = []
    unit_meta = {}   # (region) -> list of model dicts, 供 sales 用
    for region in C.REGIONS:
        quad = C.REGION_QUADRANT[region]
        prof = C.QUAD_PROFILE[quad]; sd = C.SELFDEV_BASE[quad]
        pw = "BEV" if quad in ("Q1", "Q4") else "Multi"
        tier = "Premium" if quad in ("Q1", "Q2") else "Mass"
        models = []
        for k in range(C.MODELS_PER_REGION):
            pos = rng.uniform(0, 1)                       # positioning_score
            asp0 = tnorm(*prof["asp"], mu=prof["asp"][0] + pos*(prof["asp"][1]-prof["asp"][0]), rng=rng)[0]
            batt = float(np.clip(tnorm(0, 10, mu=sd["batt"], sigma_frac=0.18, rng=rng)[0], 0, 10))
            adas = float(np.clip(tnorm(0, 10, mu=sd["adas"], sigma_frac=0.18, rng=rng)[0], 0, 10))
            chip = float(np.clip(tnorm(0, 10, mu=sd["chip"], sigma_frac=0.18, rng=rng)[0], 0, 10))
            mid = f"{region[:3].upper()}_{tier[:4].upper()}_{k+1:03d}"
            rec = dict(
                model_id=mid, brand=region+"_Brand", model_name=f"{quad}_Model_{k+1}",
                variant=["Base", "LongRange", "Performance"][k % 3], region_archetype=region,
                powertrain_focus=pw, price_tier=tier, quadrant=quad,
                list_price=round(asp0, 0), battery_capacity_kwh=round(rng.uniform(30, 100), 1),
                range_km=round(rng.uniform(350, 700), 0), charging_speed_kw=round(rng.uniform(60, 480), 0),
                customer_rating=round(float(np.clip(tnorm(0, 5, mu=2.5+pos*2, rng=rng)[0], 0, 5)), 2),
                batt_dev=round(batt, 2), adas_dev=round(adas, 2), chip_dev=round(chip, 2),
                rd_score_display=round(0.5*batt + 0.3*adas + 0.2*chip, 2),
                _pos=pos, _asp0=asp0,
            )
            model_rows.append({k2: v for k2, v in rec.items() if not k2.startswith("_")})
            models.append(rec)
        unit_meta[region] = models
    model_df = pd.DataFrame(model_rows)

    # ═════════ sales_transactions (A类因果: P→Q=exp(α+β lnP+ε)) ═════════
    sales_rows = []
    tid = 0
    for region in C.REGIONS:
        quad = C.REGION_QUADRANT[region]
        beta = C.BETA_DEMAND[quad]
        for mdl in unit_meta[region]:
            list_price = mdl["_asp0"]
            # 需求水平常数 α：让基线销量合理 (随象限规模)
            base_q = {"Q1": 3.2, "Q2": 3.0, "Q3": 4.2, "Q4": 4.8}[quad]
            alpha = base_q - beta * np.log(list_price)     # 使 lnQ 在合理量级
            # 逐日：价格围绕 list_price 独立扰动(A类需强独立变异供回归识别 β)
            for t in range(0, C.N_DAYS, 3):                # 每3天一笔样本(控制行数)
                p = list_price * np.exp(rng.normal(0, 0.15))   # 15% 外生价格变异(促销/调价)
                # 季节性(小，均值零，作噪声不作混淆；年末小冲量)
                seas = 0.05*np.sin(2*np.pi*(t % 365)/365) + (0.05 if (t % 365) > 330 else 0)
                lnq = alpha + beta*np.log(p) + seas + rng.normal(0, 0.05)  # 独立噪声 ε₁
                q = max(1, int(round(np.exp(lnq))))
                tid += 1
                sales_rows.append(dict(
                    transaction_id=f"TXN_{date_str[t].replace('-','')}_{region[:3].upper()}_{tid:06d}",
                    txn_date=date_str[t], region=region, model_id=mdl["model_id"],
                    unit_price=round(p, 0), quantity=q,
                ))
    sales_df = pd.DataFrame(sales_rows)

    # ═════════ supply_chain_costs (A类: C=α₂+Σγ_k Shock_k+ε₂, γ 被 batt_dev 注入) ═════════
    sc_rows = []
    bid = 0
    shock_map = dict(battery_pack=lithium, chip=semi, e_drive=rare,
                     domain_controller=semi, raw_material=steel)
    for region in C.REGIONS:
        quad = C.REGION_QUADRANT[region]
        cluster = C.BATTERY_CLUSTER[region]
        avg_batt = np.mean([mm["batt_dev"] for mm in unit_meta[region]])
        # γ_eff = γ_base × (1 − λ·batt/10) × (1/cluster 影响) —— 电池自研+本地集群双降 γ
        gamma_eff = C.GAMMA_BASE[quad] * (1 - C.LAMBDA_BATT*avg_batt/10) * (1.3 - 0.5*cluster)
        ground_truth["gamma_effective"][region] = round(float(gamma_eff), 4)
        prof = C.QUAD_PROFILE[quad]
        base_cost = prof["asp"][0] * (1 - np.mean(prof["margin"]))   # 基线单车成本
        for t in range(0, C.N_DAYS, 5):
            ctype = C.COMPONENT_TYPES[bid % len(C.COMPONENT_TYPES)]
            shock = shock_map[ctype][t]
            # C = 基线 + γ·(shock-100)/100 * 基线 + 独立噪声(对数正态保正)
            c_unit = base_cost * (1 + gamma_eff*(shock-100)/100) * np.exp(rng.normal(0, 0.03))
            batt_share = float(np.clip(tnorm(*prof["batt_share"], rng=rng)[0], 0.1, 0.7))
            bid += 1
            sc_rows.append(dict(
                batch_id=f"BATCH_{date_str[t].replace('-','')}_{region[:3].upper()}_{bid:06d}",
                cost_date=date_str[t], region=region, quadrant=quad, component_type=ctype,
                bom_cost_per_unit=round(c_unit, 0), battery_bom_share=round(batt_share, 3),
                automotive_cogs_per_unit=round(c_unit * 1.15, 0),   # +非电池成本
            ))
    supply_df = pd.DataFrame(sc_rows)

    # ═════════ regional_infra (B类禀赋, 低频/季度) ═════════
    infra_rows = []
    periods = [f"{y}-Q{q}" for y in (2023, 2024, 2025) for q in (1, 2, 3, 4)]
    market_size_base = {r: rng.uniform(0.2, 1.0) for r in C.REGIONS}
    for region in C.REGIONS:
        quad = C.REGION_QUADRANT[region]
        cluster = C.BATTERY_CLUSTER[region]
        for period in periods:
            infra_rows.append(dict(
                region=region, period=period,
                station_count=int(tnorm(500, 20000, mu=3000+8000*market_size_base[region], rng=rng)[0]),
                port_count=int(tnorm(2000, 120000, mu=15000+40000*market_size_base[region], rng=rng)[0]),
                fast_station_share=round(float(np.clip(tnorm(0, 1, mu=0.45, rng=rng)[0], 0, 1)), 3),
                is_swap_available=int(rng.random() < (0.6 if quad == "Q1" else 0.2)),
                swap_partnership=int(rng.random() < (0.4 if quad == "Q1" else 0.1)),
                local_battery_cluster_index=round(cluster, 3),
                local_subsidy_bonus=round(float(np.clip(tnorm(0, 0.04, rng=rng)[0], 0, 0.04)), 4),
                local_market_size=round(market_size_base[region], 3),
                local_gdp_index=round(float(np.clip(tnorm(0.3, 1.0, rng=rng)[0], 0.3, 1.0)), 3),
                gov_investment=round(float(np.clip(tnorm(0, 1.0, mu=0.3+0.4*market_size_base[region], rng=rng)[0], 0, 1)), 3),
                local_fiscal_capacity=round(float(np.clip(tnorm(0.3, 1.0, rng=rng)[0], 0.3, 1.0)), 3),
                tax_incentive_index=round(float(np.clip(tnorm(0, 1.0, rng=rng)[0], 0, 1)), 3),
            ))
    infra_df = pd.DataFrame(infra_rows)

    # ═════════ financial_snapshots (会计恒等式收口 + B类结构 + maturity 轨迹) ═════════
    fin_rows = []
    # 先聚合 sales → 交付量与均价 (A类聚合)
    sales_df["_period"] = pd.to_datetime(sales_df["txn_date"]).dt.to_period("Q").astype(str)
    sales_df["_period"] = sales_df["_period"].str.replace(r"(\d{4})Q(\d)", r"\1-Q\2", regex=True)
    agg = sales_df.groupby(["region", "_period"]).agg(
        deliveries=("quantity", "sum"),
        asp=("unit_price", "mean"),
    ).reset_index()
    # 成本聚合
    cost_agg = supply_df.groupby(["region"]).agg(cunit=("automotive_cogs_per_unit", "mean")).reset_index()
    cost_map = dict(zip(cost_agg["region"], cost_agg["cunit"]))

    for _, row in agg.iterrows():
        region, period = row["region"], row["_period"]
        quad = C.REGION_QUADRANT[region]
        prof = C.QUAD_PROFILE[quad]
        # maturity 轨迹：象限基线 + 单元残差 + 时间推进
        yprog = (int(period[:4]) - 2023) + (int(period[-1]) - 1) / 4
        stage = "growth" if C.MATURITY_BASE[quad] < 0.5 else ("mature" if C.MATURITY_BASE[quad] < 0.78 else "harvest")
        maturity = np.clip(C.MATURITY_BASE[quad] + C.MATURITY_SLOPE[stage]*yprog + rng.normal(0, 0.03), 0, 1)
        drift = 1 + C.DRIFT_PER_YEAR * yprog
        pos = rng.uniform(0, 1)

        deliveries = int(row["deliveries"])
        asp = row["asp"]
        auto_rev = asp * deliveries
        # 毛利率(B画像×maturity×drift) → 汽车成本
        margin = np.clip(tnorm(*prof["margin"], mu=prof["margin"][0]+maturity*(prof["margin"][1]-prof["margin"][0]), rng=rng)[0] * drift, 0.02, 0.35)
        auto_cost = auto_rev * (1 - margin)
        # 其它收入(B画像)
        service_rev = auto_rev * np.clip(tnorm(0, 0.20, mu=0.05+0.1*pos, rng=rng)[0], 0, 0.2)
        credit_rev = max(0, (carbon.mean()/800) * auto_rev * (0.01 if quad in ("Q1", "Q4") else 0.003))
        total_rev = auto_rev + service_rev + credit_rev
        da = total_rev * np.clip(tnorm(0.02, 0.08, rng=rng)[0], 0.02, 0.08)
        service_cost = service_rev * 0.7
        total_cost = auto_cost + service_cost
        gross = total_rev - total_cost - da
        # 费用(B画像): rd, selling
        rd_ratio = np.clip(tnorm(*prof["rd"], mu=prof["rd"][1]-maturity*(prof["rd"][1]-prof["rd"][0]), rng=rng)[0], 0.01, 0.20)
        sell_ratio = np.clip(tnorm(*prof["sell"], rng=rng)[0], 0.02, 0.18)
        rd_exp = total_rev * rd_ratio
        sell_exp = total_rev * sell_ratio
        ebit = gross - rd_exp - sell_exp                    # 会计恒等式
        # 资本结构(B画像×maturity)
        turnover = np.clip(tnorm(*prof["turnover"], rng=rng)[0], 0.5, 2.0)
        total_assets = total_rev / turnover
        equity_frac = np.clip(0.05 + maturity*0.35, 0.05, 0.45)   # 成长期薄
        equity = total_assets * equity_frac
        de = np.clip(tnorm(*prof["de"], rng=rng)[0], 0.05, 2.5)
        debt = equity * de
        cash = total_assets * np.clip(tnorm(0.10, 0.40, rng=rng)[0], 0.1, 0.4)
        interest = debt * (ir.mean() + 0.02)
        net = (ebit - interest) * (1 - C.TAX_RATE)          # 会计恒等式(可负)
        capex = total_rev * np.clip(tnorm(0.03, 0.15, rng=rng)[0], 0.03, 0.15)
        fcf = ebit*(1-C.TAX_RATE) + da - capex

        fin_rows.append(dict(
            region=region, quadrant=quad, period=period,
            total_revenue=round(total_rev, 0), automotive_sales_revenue=round(auto_rev, 0),
            service_revenue=round(service_rev, 0), regulatory_credit_revenue=round(credit_rev, 0),
            total_cost_of_revenue=round(total_cost, 0), automotive_cost_of_revenue=round(auto_cost, 0),
            depreciation_amortization=round(da, 0), gross_profit=round(gross, 0),
            operating_income=round(ebit, 0), tax_rate=C.TAX_RATE, net_income=round(net, 0),
            total_assets=round(total_assets, 0), shareholders_equity=round(equity, 0),
            interest_bearing_debt=round(debt, 0), cash_and_equivalents=round(cash, 0),
            total_deliveries=deliveries, rd_ratio=round(rd_ratio, 4), capex=round(capex, 0),
            selling_expense=round(sell_exp, 0), fcf=round(fcf, 0),
        ))
    fin_df = pd.DataFrame(fin_rows)

    tables = dict(model_dim=model_df, sales_transactions=sales_df.drop(columns=["_period"]),
                  macro_shocks_log=macro_df, regional_infra=infra_df,
                  supply_chain_costs=supply_df, financial_snapshots=fin_df)
    return tables, ground_truth


if __name__ == "__main__":
    tabs, gt = build()
    for name, df in tabs.items():
        print(f"{name:22s} rows={len(df):6d}  cols={len(df.columns)}")
    print("gamma_effective:", gt["gamma_effective"])
