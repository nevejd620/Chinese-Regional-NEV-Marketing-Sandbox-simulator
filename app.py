"""
Phase 1 · app.py  (deliberately thin — skeleton that goes live day-one)
City selector + 3 sliders + one Plotly ROE ray (with Monte-Carlo band) + the
parameter-recovery table. NO LLM wired to the sliders (red line: hallucination
never touches the numbers). Run:  streamlit run src/app.py

Deploy: push to Streamlit Community Cloud; nev.db can be force-added as a static
asset, or regenerated on first boot from generate_data.py.
"""
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import numpy as np                                           # noqa: E402
from ensure_db import ensure_db                              # noqa: E402
from calibration import recovery_table, cached_config        # noqa: E402
from simulate import simulate_roe                            # noqa: E402
import financials                                            # noqa: E402  Phase 2 价值裁决层
import copy_cn as T                                          # noqa: E402  人话文案层（纯显示）

st.set_page_config(page_title="NEV 沙盘 · Phase 1", layout="wide")

ensure_db()                                                  # regenerate db on Cloud if missing
config = cached_config()                                     # cached build/read of config
cities = list(config["baseline"].keys())


st.title("新能源汽车区域选址及定价沙盘")
st.caption("选址禀赋 → 象限战略 → 定价冲击 → ROE 与价值创造裁决 · 系数由 nev.db 回归恢复,非手填")

# 显示层：英文 region 键 → 中文名。底层取数一律用英文键,只在 UI 翻译。
CITY_CN = {"Shanghai": "上海", "Shenzhen": "深圳", "Hefei": "合肥",
           "Changzhou": "常州", "Xian": "西安", "Liuzhou": "柳州"}
cn_of = lambda r: CITY_CN.get(r, r)          # 没映射到的回退英文,不会崩

left, right = st.columns([1, 2], gap="large")

with left:
    city = st.selectbox("城市 / 选址", cities, index=0, format_func=cn_of)
    q = config["baseline"][city]["quadrant"]
    st.markdown(f"**象限**：`{q}`　**基准 ROE**："
                f"`{config['baseline'][city]['roe_base']:+.1%}`")
    st.divider()
    price_change  = st.slider("自主定价变动 (%)", -20, 20, 0, 1,
                              help="经 β 弹性传导到销量")
    lithium_shock = st.slider("碳酸锂价格冲击 (%)", -30, 60, 0, 5,
                              help="经 γ 传导到单位成本,按半衰期衰减")
    demand_shift  = st.slider("需求侧位移 (%)", -15, 15, 0, 1,
                              help="aᵢ 心智分量代理(销售费用/智驾),Phase 1 简化为加性")

sliders = dict(price_change=price_change, lithium_shock=lithium_shock,
               demand_shift=demand_shift)
res = simulate_roe(city, sliders, config)

# ── Phase 2 · 价值 spread 逐日线（动态，路 B）：喂 simulate 的 EBIT 线 → financials ──
has_ebit = res.get("ebit_p50") is not None
if has_ebit:
    def _spread_of(ebit_line):
        sl = financials.spread_line(
            np.array(ebit_line), quadrant=res["quadrant"],
            shareholders_equity=res["shareholders_equity"],
            interest_bearing_debt=res["interest_bearing_debt"],
            cash_and_equivalents=res["cash_and_equivalents"],
            tax_rate=res["tax_rate"])
        return [None if (x != x) else float(x) for x in sl["spread"]]   # NaN→None
    spr_p05 = _spread_of(res["ebit_p05"])
    spr_p50 = _spread_of(res["ebit_p50"])
    spr_p95 = _spread_of(res["ebit_p95"])

# ── 「对比上次拨动」：按城市存上一次中位线，用于阴影 ──
skey = f"prev::{city}"
prev = st.session_state.get(skey)


def _panel(days, p05, p50, p95, prev_p50, color, rgba, y_title,
           zero_ref, zero_label, base_ref, base_label,
           this_label, prev_label):
    """一个分区面板：p5–p95 带 + 中位线 +（有上次则）对比阴影 + 参考线。文案全走 copy_cn。"""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=days, y=p95, mode="lines", line=dict(width=0),
                             showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=days, y=p05, mode="lines", line=dict(width=0),
                             fill="tonexty", fillcolor=rgba.replace("A%", "0.13"),
                             name="p5–p95 置信带"))
    if prev_p50 is not None:
        fig.add_trace(go.Scatter(x=days, y=prev_p50, mode="lines",
                                 line=dict(color="#B0AEA8", width=1.4, dash="dot"),
                                 name=prev_label))
        fig.add_trace(go.Scatter(x=days, y=p50, mode="lines", fill="tonexty",
                                 fillcolor=rgba.replace("A%", "0.22"),
                                 line=dict(color=color, width=2.6), name=this_label))
    else:
        fig.add_trace(go.Scatter(x=days, y=p50, mode="lines",
                                 line=dict(color=color, width=2.6), name=this_label))
    if zero_ref:
        fig.add_hline(y=0, line=dict(color="#C0392B", dash="dash"),
                      annotation_text=zero_label, annotation_position="top left",
                      annotation_font=dict(color="#C0392B", size=11))
    if base_ref is not None:
        fig.add_hline(y=base_ref, line=dict(color="#888780", dash="dash"),
                      annotation_text=base_label, annotation_position="bottom left",
                      annotation_font=dict(color="#888780", size=11))
    fig.update_layout(height=250, margin=dict(l=10, r=80, t=20, b=8),
                      yaxis_title=y_title, yaxis_tickformat=".0%",
                      legend=dict(orientation="h", y=1.18), showlegend=True)
    return fig

# ── 段标题 + 结论 ──
if T.SECTION_TITLE:
    st.subheader(T.SECTION_TITLE)
if T.SECTION_CAPTION:
    st.caption(T.SECTION_CAPTION)
if T.HEADLINE_MAIN:
    st.markdown(f"#### {T.HEADLINE_MAIN}")
if T.HEADLINE_SUB:
    st.caption(T.HEADLINE_SUB)

with right:
    # ① 上区：ROE 射线 —— 保留 Phase 1，叠「对比上次」阴影
    st.markdown(f"**{T.PANEL_ROE_TITLE}**")
    roe_fig = _panel(res["days"], res["roe_p05"], res["roe_p50"], res["roe_p95"],
                     (prev["roe"] if prev else None), "#185FA5", "rgba(24,95,165,A%)",
                     T.AXIS_ROE_LABEL, zero_ref=False, zero_label="",
                     base_ref=res["roe_base"], base_label=T.ROE_BASE_LABEL,
                     this_label=T.SHADE_THIS_LABEL, prev_label=T.SHADE_PREV_LABEL)
    roe_fig.update_layout(xaxis_showticklabels=False)
    st.plotly_chart(roe_fig, use_container_width=True)
    if T.ROE_NOTE:
        st.caption(T.ROE_NOTE)
    if prev and T.SHADE_NOTE:
        st.caption(T.SHADE_NOTE)

    # ② 下区：价值 spread 射线 —— 共享时间轴
    st.markdown(f"**{T.PANEL_SPR_TITLE}**")
    if has_ebit:
        spr_fig = _panel(res["days"], spr_p05, spr_p50, spr_p95,
                         (prev["spr"] if prev else None), "#C0392B", "rgba(192,57,43,A%)",
                         T.AXIS_SPR_LABEL, zero_ref=True, zero_label=T.ZERO_LINE_LABEL,
                         base_ref=None, base_label="",
                         this_label=T.SHADE_THIS_LABEL, prev_label=T.SHADE_PREV_LABEL)
        spr_fig.update_layout(xaxis_title=T.AXIS_TIME_LABEL)
        st.plotly_chart(spr_fig, use_container_width=True)
        if T.SPREAD_NOTE:
            st.caption(T.SPREAD_NOTE)
    else:
        st.info("当前 simulation_config.json 缺 `ebit_base`：请在 Colab 重跑 "
                "`python calibration.py` 生成含 Phase 2 字段的 config，价值线即可启用。")

# 存本次中位线，供下次拨动做阴影对照
if has_ebit:
    st.session_state[skey] = dict(roe=res["roe_p50"], spr=spr_p50)

# ── 动态裁决 + 基线杜邦解剖 ──
st.divider()
if has_ebit:
    roe_end = res["roe_p50"][-1]
    spr_end = spr_p50[-1]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(T.label("roe"), f"{roe_end:+.1%}", f"{res['roe_delta_end']:+.1%} vs 基准",
              help=T.tip("roe"))
    m2.metric(T.label("spread"), (f"{spr_end:+.1%}" if spr_end is not None else "—"),
              help=T.tip("spread"))
    m3.metric("β / γ 采用", f"{res['beta_used']:.2f} / {res['gamma_used']:.2f}")
    m4.metric("象限", res["quadrant"])
    if spr_end is not None:
        v = f"{abs(spr_end) * 100:.0f}"                      # {v}=spread 绝对值百分数
        if spr_end > 0:                                     # CREATE
            st.success(T.VERDICT_CREATE.format(v=v))
        elif roe_end > 0:                                   # ① 账面在赚却毁价值（反差）
            st.error(T.VERDICT_WINSALES_LOSEVALUE.format(v=v))
        else:                                               # ③ 账面也亏、更谈不上创造
            st.error(T.VERDICT_DESTROY.format(v=v))
    else:
        st.warning(T.VERDICT_NA)

# 基线杜邦（t0 结构解剖，静态）
bb = config["baseline"][city]
if all(k in bb for k in ("total_revenue", "total_assets")):
    dm = financials.compute_value_metrics(
        operating_income=bb["ebit_base"], net_income=bb["net_income"],
        total_revenue=bb["total_revenue"], total_assets=bb["total_assets"],
        shareholders_equity=bb["equity"], interest_bearing_debt=bb["interest_bearing_debt"],
        cash_and_equivalents=bb["cash_and_equivalents"], quadrant=q, tax_rate=bb["tax_rate"])
    if T.DUPONT_FORMULA:
        st.caption(T.DUPONT_FORMULA)
    d1, d2, d3 = st.columns(3)
    d1.metric(T.label("net_margin"), f"{dm['net_margin']:+.1%}", help=T.tip("net_margin"))
    d2.metric(T.label("asset_turnover"), f"{dm['asset_turnover']:.2f}",
              help=T.tip("asset_turnover"))
    d3.metric(T.label("equity_multiplier"), f"{dm['equity_multiplier']:.2f}",
              help=T.tip("equity_multiplier"))

st.divider()
st.subheader("参数恢复表　(回归估计 vs 埋入真值 · 项目立身之本)")
tab = recovery_table()
show = tab.assign(
    covered=tab.covered.map({True: "✓", False: "✗"})
).rename(columns={"coefficient": "系数", "key": "象限/区域", "truth": "真值",
                  "estimate": "回归估计", "ci_low": "CI下", "ci_high": "CI上",
                  "std_err": "标准误", "covered": "覆盖", "r2": "R²", "n": "样本"})
st.dataframe(show, use_container_width=True, hide_index=True)
st.caption(f"CI 覆盖真值：{int(tab.covered.sum())}/{len(tab)}　"
           "· 覆盖即证明系数是从数据恢复、而非编造")
