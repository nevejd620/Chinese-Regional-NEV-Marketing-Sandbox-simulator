"""
NEV 沙盘 Phase 2 · 财务解剖与价值裁决层 (financials.py)

接 simulate.py / financial_snapshots 的损益·资产输出，算：
    杜邦三因子 → ROIC → WACC → 价值创造 spread = ROIC − WACC

纯 numpy/pandas，无 LLM。计量：人民币，中国口径（沿用 Phase 0–1）。

设计红线（务必守住）：
  · invested_capital / roic / wacc 均为**派生聚合量**，运行时按公式算、不入库
    （schema legend：单一真相源，避免存了与原子列对不上）。
  · WACC 权重用**市值派生** E = 账面权益 × pb_multiple[象限]，不用账面权益
    （sheet 8：蔚来账面权益被累计亏损侵蚀，账面 D/E、ROE 失真）。
  · 有息负债 D = interest_bearing_debt（非总负债）。
  · 核心 `compute_value_metrics` 为**纯函数**：既能吃 financial_snapshots 的基线截面，
    也能吃 simulate.py 的**日度 EBIT 数组**（Phase 2 决策 A：spread 随滑块动）。
    → 这就是"算层与显示层解耦、且不重复实现 WACC"的落点。
"""
import numpy as np
import pandas as pd
import config


# ─────────────────────────────────────────────────────────────
# 价值裁决核心：标量或等长 numpy 数组皆可
#   · 吃 financial_snapshots 单行 → 标量，得该 cell 的 t0 基线裁决
#   · 吃 simulate 的日度 EBIT/净利线 → 数组，得随滑块迁移的 spread 轨迹
#   quadrant 为标量（一个 cell 属一个象限）；资本结构口径在 180 天内视为不变，
#   只有 EBIT/净利随滑块变（价格/成本冲击打的是利润，不是当期资本结构）。
# ─────────────────────────────────────────────────────────────
def compute_value_metrics(
    *,
    operating_income,          # EBIT（ROIC/NOPAT 用，付息前口径）
    net_income,                # 归母净利（ROE 分子）
    total_revenue,
    total_assets,
    shareholders_equity,       # 账面权益
    interest_bearing_debt,     # 有息负债 D（非总负债）
    cash_and_equivalents,
    quadrant,
    rf=None,                   # 无风险利率；缺省取 config 起点，日度路径可传 macro 序列
    tax_rate=None,
):
    if rf is None:
        rf = config.MACRO["interest"]["start"]
    if tax_rate is None:
        tax_rate = config.TAX_RATE

    # ── 派生：投入资本（聚合量，运行时算，不读库）──────────────
    invested_capital = interest_bearing_debt + shareholders_equity - cash_and_equivalents

    # ── 杜邦三因子：ROE = 净利率 × 资产周转率 × 权益乘数 ─────────
    net_margin        = net_income / total_revenue
    asset_turnover    = total_revenue / total_assets
    equity_multiplier = total_assets / shareholders_equity
    roe               = net_margin * asset_turnover * equity_multiplier   # ≡ net_income/equity

    # ── ROIC = NOPAT / 投入资本 ─────────────────────────────────
    #   §C4 式容错：若某 cell 投入资本 ≤ 0（现金 > 有息债+权益，或权益被亏损侵蚀为负），
    #   ROIC 无经济意义 → 标 NaN，让前沿图自动跳过该点，不崩、不出假值。
    nopat   = operating_income * (1.0 - tax_rate)
    ic_safe = np.where(np.asarray(invested_capital, dtype=float) > 0,
                       invested_capital, np.nan)
    roic    = nopat / ic_safe

    # ── WACC：市值加权（E 用市值派生，不用账面权益）────────────
    pb            = config.PB_MULTIPLE[quadrant]
    market_equity = shareholders_equity * pb        # E
    debt          = interest_bearing_debt           # D（有息）
    V             = market_equity + debt
    cost_equity   = rf + config.EQUITY_BETA[quadrant] * config.ERP     # CAPM: Re = rf + β·ERP
    cost_debt     = rf + config.CREDIT_SPREAD                          # Rd = rf + 信用利差
    wacc          = (market_equity / V) * cost_equity \
                    + (debt / V) * cost_debt * (1.0 - tax_rate)        # 债务腿税盾

    # ── 价值裁决 ────────────────────────────────────────────────
    spread = roic - wacc                            # 正=创造价值，负=毁灭价值

    return dict(
        invested_capital=invested_capital,
        net_margin=net_margin,
        asset_turnover=asset_turnover,
        equity_multiplier=equity_multiplier,
        roe=roe,
        nopat=nopat,
        roic=roic,
        cost_equity=cost_equity,
        cost_debt=cost_debt,
        wacc=wacc,
        spread=spread,
    )


# ─────────────────────────────────────────────────────────────
# DB 侧包装：吃 financial_snapshots 截面 → 逐 cell 价值宽表 + 营收增速（横轴）
#   横轴口径（Phase 2 决策 2）：营收增速，用 CAGR（多期几何年化）。
# ─────────────────────────────────────────────────────────────
def value_table_from_snapshots(df):
    rows = []
    for (region, quadrant), g in df.groupby(["region", "quadrant"]):
        g = g.sort_values("period")
        rev = g["total_revenue"].to_numpy(dtype=float)
        if len(rev) >= 2 and rev[0] > 0:
            revenue_growth = (rev[-1] / rev[0]) ** (1.0 / (len(rev) - 1)) - 1.0  # CAGR
        else:
            revenue_growth = np.nan
        last = g.iloc[-1]                            # 最近一期截面做裁决
        m = compute_value_metrics(
            operating_income=float(last["operating_income"]),
            net_income=float(last["net_income"]),
            total_revenue=float(last["total_revenue"]),
            total_assets=float(last["total_assets"]),
            shareholders_equity=float(last["shareholders_equity"]),
            interest_bearing_debt=float(last["interest_bearing_debt"]),
            cash_and_equivalents=float(last["cash_and_equivalents"]),
            quadrant=quadrant,
            tax_rate=float(last["tax_rate"]) if "tax_rate" in last else None,
        )
        m.update(region=region, quadrant=quadrant, revenue_growth=revenue_growth)
        rows.append(m)
    cols = ["region", "quadrant", "revenue_growth",
            "net_margin", "asset_turnover", "equity_multiplier", "roe",
            "roic", "wacc", "spread", "invested_capital", "nopat",
            "cost_equity", "cost_debt"]
    return pd.DataFrame(rows)[cols]


def load_snapshots(db_path="nev.db"):
    """只读取 financial_snapshots（不写库，沿用 Phase 1 只读原则）。"""
    import sqlite3
    con = sqlite3.connect(db_path)
    try:
        return pd.read_sql_query("SELECT * FROM financial_snapshots", con)
    finally:
        con.close()


if __name__ == "__main__":
    # 冒烟：真库在则跑，否则提示（真验收在 notebook / smoke_test）
    import os
    if os.path.exists("nev.db"):
        tbl = value_table_from_snapshots(load_snapshots())
        pd.set_option("display.width", 160, "display.max_columns", 20)
        print(tbl.round(4).to_string(index=False))
    else:
        print("nev.db 不在当前目录；请在 repo 根目录运行，或跑 smoke_test_financials.py 验证算法。")
