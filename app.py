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

st.set_page_config(page_title="NEV 沙盘 · Phase 1", layout="wide")

ensure_db()                                                  # regenerate db on Cloud if missing
config = cached_config()                                     # cached build/read of config
cities = list(config["baseline"].keys())

st.title("NEV 区域定价沙盘 · Phase 1")
st.caption("选址禀赋 → 象限战略 → 定价冲击 → ROE 价值裁决 · 系数由 nev.db 回归恢复,非手填")

left, right = st.columns([1, 2], gap="large")

with left:
    city = st.selectbox("城市 / 选址", cities, index=0)
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
                  annotation_text="基准 ROE", annotation_position="right")
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10),
                      xaxis_title="推演天数 (0–180)", yaxis_title="ROE(年化运行率)",
                      yaxis_tickformat=".0%", legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("ROE @ t0",   f"{res['roe_p50'][0]:+.1%}")
    c2.metric("ROE @ t180", f"{res['roe_p50'][-1]:+.1%}",
              f"{res['roe_delta_end']:+.1%} vs 基准")
    c3.metric("β / γ 采用", f"{res['beta_used']:.2f} / {res['gamma_used']:.2f}")

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
