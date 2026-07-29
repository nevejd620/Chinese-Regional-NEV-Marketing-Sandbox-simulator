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

from ensure_db import ensure_db                              # noqa: E402
from calibration import recovery_table, cached_config        # noqa: E402
from simulate import simulate_roe                            # noqa: E402
import financials                                            # noqa: E402  Phase 2 价值裁决层

st.set_page_config(page_title="NEV 沙盘 · Phase 1", layout="wide")

ensure_db()                                                  # regenerate db on Cloud if missing
config = cached_config()                                     # cached build/read of config
cities = list(config["baseline"].keys())


@st.cache_data(show_spinner=False)
def cached_value_table():
    """Phase 2：读 financial_snapshots → 杜邦/ROIC/WACC/spread 价值宽表（静态基线截面）。
    与 config 同源于当次 nev.db，天然同批；不写库、不挂 LLM。"""
    return financials.value_table_from_snapshots(financials.load_snapshots())

st.title("NEV 区域定价沙盘 · Phase 1")
st.caption("选址禀赋 → 象限战略 → 定价冲击 → ROE 价值裁决 · 系数由 nev.db 回归恢复,非手填")

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

with right:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=res["days"], y=res["roe_p95"], mode="lines",
                             line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=res["days"], y=res["roe_p05"], mode="lines",
                             line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(24,95,165,0.15)", name="p5–p95 置信带"))
    fig.add_trace(go.Scatter(x=res["days"], y=res["roe_p50"], mode="lines",
                             line=dict(color="#185FA5", width=2.5), name="ROE 中位射线"))
    fig.add_hline(y=res["roe_base"], line=dict(color="#888780", dash="dash"),
                  annotation_text="基准 ROE", annotation_position="top left",
                  annotation_font=dict(color="#888780", size=12))
    fig.update_layout(height=380, margin=dict(l=10, r=70, t=30, b=10),
                      xaxis_title="推演天数 (0–180)", yaxis_title="ROE(年化运行率)",
                      yaxis_tickformat=".0%", legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("ROE @ t0",   f"{res['roe_p50'][0]:+.1%}")
    c2.metric("ROE @ t180", f"{res['roe_p50'][-1]:+.1%}",
              f"{res['roe_delta_end']:+.1%} vs 基准")
    c3.metric("β / γ 采用", f"{res['beta_used']:.2f} / {res['gamma_used']:.2f}")

# ═══════════════════════════════════════════════════════════════
# Phase 2 · 财务解剖与价值裁决 (杜邦 → ROIC−WACC · 静态基线截面)
#   不挂 LLM；不随上方滑块（价值口径独立于短期冲击演示，见 Phase 2 决策台账）。
# ═══════════════════════════════════════════════════════════════
st.divider()
st.subheader("财务解剖与价值裁决　(杜邦 → ROIC − WACC · 静态基线截面)")
st.caption("回答「这个 ROE 到底创没创造价值」。数字取自 financial_snapshots 基线截面，"
           "为 t0 价值裁决——独立于上方滑块（滑块动的是 ROE 射线，价值坐标是固定背景）。")

vt = cached_value_table()
sel = vt[(vt.region == city) & (vt.quadrant == q)]

fcol, rcol = st.columns([3, 2], gap="large")

with fcol:
    # ── ROIC−WACC 价值创造前沿：全 cell 静态铺开，当前城市高亮 ──
    QUAD_COLOR = {"Q1": "#185FA5", "Q2": "#3E8E7E", "Q3": "#C77D3A", "Q4": "#8A6FA8"}
    ffig = go.Figure()
    for qd, g in vt.groupby("quadrant"):
        ffig.add_trace(go.Scatter(
            x=g.revenue_growth, y=g.spread, mode="markers",
            marker=dict(size=13, color=QUAD_COLOR.get(qd, "#888780")),
            name=qd, text=[cn_of(r) for r in g.region],
            hovertemplate="%{text}·" + qd +
                          "<br>营收增速 %{x:.1%}<br>spread %{y:+.1%}<extra></extra>"))
    if not sel.empty:
        ffig.add_trace(go.Scatter(
            x=sel.revenue_growth, y=sel.spread, mode="markers",
            marker=dict(size=22, color="rgba(0,0,0,0)",
                        line=dict(color="#C0392B", width=3)),
            name="当前选中", hoverinfo="skip"))
    ffig.add_hline(y=0, line=dict(color="#C0392B", dash="dash"),
                   annotation_text="价值创造分界 (ROIC=WACC)",
                   annotation_position="bottom right",
                   annotation_font=dict(color="#C0392B", size=12))
    ffig.update_layout(height=420, margin=dict(l=10, r=40, t=30, b=10),
                       xaxis_title="营收增速 (CAGR)",
                       yaxis_title="价值创造 spread = ROIC − WACC",
                       xaxis_tickformat=".0%", yaxis_tickformat=".0%",
                       legend=dict(orientation="h", y=1.12))
    st.plotly_chart(ffig, use_container_width=True)
    st.caption("横轴＝规模扩张速度，纵轴＝每单位资本创造/毁灭的价值。"
               "零轴之上创造价值、之下毁灭价值；**右下＝高增长却毁价值（赢销量≠赢价值）**。"
               "红圈＝当前选中城市。")

with rcol:
    if sel.empty:
        st.info(f"financial_snapshots 暂无 {cn_of(city)} × {q} 的截面，跳过该 cell 裁决。")
    else:
        s = sel.iloc[0]
        st.markdown("**杜邦三因子**　ROE = 净利率 × 周转率 × 权益乘数")
        d1, d2, d3 = st.columns(3)
        d1.metric("净利率", f"{s.net_margin:+.1%}")
        d2.metric("资产周转率", f"{s.asset_turnover:.2f}")
        d3.metric("权益乘数", f"{s.equity_multiplier:.2f}")
        st.markdown("**价值裁决**　spread = ROIC − WACC")
        v1, v2, v3 = st.columns(3)
        v1.metric("ROIC", f"{s.roic:+.1%}" if pd.notna(s.roic) else "—")
        v2.metric("WACC", f"{s.wacc:.1%}")
        v3.metric("ROE", f"{s.roe:+.1%}")
        if pd.notna(s.spread):
            box = st.success if s.spread > 0 else st.error
            box(f"{cn_of(city)} × {q}："
                f"{'创造价值 ✓' if s.spread > 0 else '毁灭价值 ✗'}"
                f"（spread {s.spread:+.1%}）")
        else:
            st.warning("该 cell 投入资本 ≤ 0，ROIC 无经济意义，已跳过裁决。")

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
