"""
NEV 沙盘 · 单一入口（Phase 2 财务解剖 + Phase 3 定价博弈，双 tab 并存）

- Phase 2 tab：选址 + 3 滑块 + ROE/价值 spread 上下双线 + 动态裁决 + 参数恢复表（原样保留）。
- Phase 3 tab：选址×象限 + 定价/生态 2 滑块 + 联盟开关 + 记分尺子开关 → 图一(份额×spread)/图二(aᵢ×spread) 双散点 + 四态裁决。
两阶段共享同一个 config / financials / copy_cn；博弈逻辑全在 game.py（LLM 红线：幻觉够不到财务数字）。
Run:  streamlit run app.py
"""
from pathlib import Path
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from ensure_db import ensure_db
from calibration import recovery_table, cached_config
from simulate import simulate_roe
import financials
import game
import copy_cn as T

st.set_page_config(page_title="NEV 沙盘 · 选址与定价博弈", layout="wide")

ensure_db()
config = cached_config()
cities = list(config["baseline"].keys())

CITY_CN = {"Shanghai": "上海", "Shenzhen": "深圳", "Hefei": "合肥",
           "Changzhou": "常州", "Xian": "西安", "Liuzhou": "柳州"}
QUAD_CN = {"Q1": "Q1 纯电先锋", "Q2": "Q2 全路线高端", "Q3": "Q3 垂直整合", "Q4": "Q4 极致性价比"}
cn_of = lambda r: CITY_CN.get(r, r)


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


def render_phase2(config):
    st.caption("选址禀赋 → 象限战略 → 定价冲击 → ROE 与价值创造裁决 · 系数由 nev.db 回归恢复，非手填")
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


def render_phase3():
    st.subheader(T.P3_INTRO)                         # 顶部固定引入句「你定价，对手会还手」
    c_ctrl, c_main = st.columns([1, 3], gap="large")

    with c_ctrl:
        st.markdown("**控制台**")
        region = st.selectbox("选址城市", C.REGIONS, format_func=lambda c: CITY_CN[c],
                              index=1, key="p3_region")
        quad = st.selectbox("战略象限", list(C.QUAD_PROFILE.keys()),
                            format_func=lambda q: T.QUAD_CELL[q]["short"], index=0, key="p3_quad")
        price_pct = st.slider(T.SLIDER_PRICE, -30, 15, 0, step=1, key="p3_price")
        eco = st.slider(T.SLIDER_ECO, 0.0, C.ECO_SLIDER_MAX, 0.0, step=0.05, key="p3_eco")
        ally = st.toggle(T.TOGGLE_ALLY, value=False, key="p3_ally")
        st.divider()
        # 记分尺子 = 图一纵轴用哪把量尺。份额已是图一横轴，不再作纵轴尺子，只留三把"值不值"的尺子。
        ruler_opts = [k for k in T.SCORER_NAMES if k != "share"]   # spread / roe / roic
        scorer = st.radio(T.SCORER_LABEL, ruler_opts,
                          format_func=lambda s: T.SCORER_NAMES[s], key="p3_ruler")
        with st.expander("关于 / 诚实声明"):
            st.caption(T.PROXY_NOTE_P3)

    # ── 计算 ──
    p0 = game.build_user_firm(region, quad)["p0"]
    user_price = p0 * (1.0 + price_pct / 100.0)
    c1 = game.chart_one(region, quad, user_price=user_price, eco_invest=eco)
    c2 = game.chart_two(region, quad, eco_invest=eco, alliance_on=ally)
    y_key_1 = scorer                    # spread / roe / roic —— 纵坐标随尺子切换
    y_lab_1 = T.SCORER_NAMES[scorer]    # 数据与标签同源，不再出现"标签=份额、数值=价值"的错位

    with c_main:
        fig = make_subplots(rows=2, cols=1, vertical_spacing=0.16,
                            subplot_titles=(T.CHART1_TITLE, T.CHART2_TITLE))
        # 图一：份额 × 记分尺子
        xs = [p["share"] for p in c1["points"]]
        ys = [p.get(y_key_1) for p in c1["points"]]
        labels = [("你" if p["is_user"] else p["firm_id"]) for p in c1["points"]]
        colors = ["#e4572e" if p["is_user"] else "#4c9be8" for p in c1["points"]]
        sizes = [26 if p["is_user"] else 15 for p in c1["points"]]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers+text", text=labels, textposition="top center",
            marker=dict(size=sizes, color=colors, line=dict(width=1, color="white")),
            hovertext=[f"{l}｜份额 {p['share']:.0%}｜价值创造 {T.fmt_pct(p['spread'])}"
                       for l, p in zip(labels, c1["points"])],
            hoverinfo="text", showlegend=False), row=1, col=1)
        fig.add_hline(y=0, line_dash="dot", line_color="gray", row=1, col=1)
        fig.update_xaxes(title_text=T.CHART1_XAXIS, tickformat=".0%", row=1, col=1)
        fig.update_yaxes(title_text=y_lab_1, row=1, col=1)
        # 图二：aᵢ × 记分尺子（与图一同一把尺）+ 联盟连边
        pt_by_id = {p["firm_id"]: p for p in c2["points"]}
        for e in c2["edges"]:
            a, b = pt_by_id.get(e["a"]), pt_by_id.get(e["b"])
            if a and b:
                fig.add_trace(go.Scatter(
                    x=[a["a_value"], b["a_value"]], y=[a.get(y_key_1), b.get(y_key_1)],
                    mode="lines", line=dict(width=2, color="rgba(120,180,120,0.7)", dash="dot"),
                    hoverinfo="skip", showlegend=False), row=2, col=1)
        x2 = [p["a_value"] for p in c2["points"]]
        y2 = [p.get(y_key_1) for p in c2["points"]]
        lab2 = [("你" if p["is_user"] else p["firm_id"]) for p in c2["points"]]
        col2 = ["#e4572e" if p["is_user"] else ("#5aa469" if p["in_alliance"] else "#9aa7b4")
                for p in c2["points"]]
        siz2 = [26 if p["is_user"] else 14 for p in c2["points"]]
        fig.add_trace(go.Scatter(
            x=x2, y=y2, mode="markers+text", text=lab2, textposition="top center",
            marker=dict(size=siz2, color=col2, line=dict(width=1, color="white")),
            hovertext=[f"{l}｜{p['quad']}｜非价格吸引力 {p['a_value']:.2f}｜{y_lab_1} {T.fmt_pct(p.get(y_key_1))}"
                       + ("｜在盟" if p["in_alliance"] else "")
                       for l, p in zip(lab2, c2["points"])],
            hoverinfo="text", showlegend=False), row=2, col=1)
        fig.add_hline(y=0, line_dash="dot", line_color="gray", row=2, col=1)
        fig.update_xaxes(title_text=T.CHART2_XAXIS, row=2, col=1)
        fig.update_yaxes(title_text=y_lab_1, row=2, col=1)
        fig.update_layout(height=760, margin=dict(t=60, b=40, l=60, r=30))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"{T.CHART1_SUB}　|　{T.CHART2_SUB}")

        # ── 底部：动态裁决 + 读数 ──
        v = c1["verdict"]
        you1 = next(p for p in c1["points"] if p["is_user"])
        you2 = next(p for p in c2["points"] if p["is_user"])
        st.markdown(f"### 裁决　{T.verdict_sentence(v)}")
        flip = T.READOUT_FLIP if v.get("ruler_flip") else ""
        r1 = T.READOUT_C1.format(share=you1["share"], spread=T.fmt_pct(you1["spread"]),
                                 srank=v.get("share_rank", "—"), vrank=v.get("spread_rank", "—"),
                                 flip=flip)
        r2 = T.READOUT_C2.format(a=you2["a_value"], spread=T.fmt_pct(you2.get(y_key_1)),
                                 ally=(T.READOUT_ALLY if ally else ""))
        col_a, col_b = st.columns(2)
        col_a.markdown("**图一读数 · 象限内竞争**"); col_a.write(r1)
        col_a.caption(f"竞争类型：{T.COMPETITION_CN[c1['competition_type']]}（θ={C.THETA_Q[quad]}）")
        col_b.markdown("**图二读数 · 区域/全国竞合**"); col_b.write(r2)


# ══════════════════════════ 象限地图（Phase 2/3 共享）══════════════════════════
import config as C


def _quad_stats(q):
    """从 config 真值拼该象限的 β/θ/ASP/毛利 —— 进卡片 ⓘ tooltip，与引擎同源、不手抄。"""
    b = C.BETA_DEMAND[q]
    th = C.THETA_Q[q]
    lo, hi = C.QUAD_PROFILE[q]["asp"]
    m0, m1 = C.QUAD_PROFILE[q]["margin"]
    return (f"价格弹性 β {b} · 定价权 θ {th} · "
            f"ASP {lo/1e4:g}–{hi/1e4:g}万 · 毛利 {m0*100:.0f}–{m1*100:.0f}%")


def _quad_card(col, q, highlight=None, compact=False):
    cell = T.QUAD_CELL[q]
    with col.container(border=True):
        st.markdown(f"**{cell['name']}**")                     # 名称（全称定位）
        if q == highlight:
            st.markdown(":blue-background[◀ 你选的象限]")       # 精简条高亮
        if compact:
            st.caption(f"打法 · {cell['play']}")               # 精简条：只留一句打法
        else:
            st.markdown(f"**{T.QUAD_FIELD['feature']}**：{cell['feature']}")
            st.markdown(f"**{T.QUAD_FIELD['anchors']}**：{cell['anchors']}")
            st.markdown(f"**{T.QUAD_FIELD['strategy']}**：{cell['strategy']}")
            st.markdown(f"**{T.QUAD_FIELD['params']}**：{_quad_stats(q)}")


def render_quadrant_map(highlight=None, compact=False):
    """2×2 象限地图。compact=True 为双 tab 上方精简条（可高亮所选象限）；否则为「象限地图」tab 详版。"""
    if not compact:
        st.subheader(T.QUAD_MAP_TITLE)
        st.caption(T.QUAD_MAP_INTRO)
    st.caption(T.QUAD_AXIS_Y_TOP)                              # ▲ Premium
    r1c1, r1c2 = st.columns(2)                                 # 上排：Premium 行
    _quad_card(r1c1, "Q1", highlight, compact)
    _quad_card(r1c2, "Q2", highlight, compact)
    r2c1, r2c2 = st.columns(2)                                 # 下排：Mass 行
    _quad_card(r2c1, "Q4", highlight, compact)
    _quad_card(r2c2, "Q3", highlight, compact)
    st.caption(T.QUAD_AXIS_Y_BOT)                              # ▼ Mass
    st.caption(T.QUAD_AXIS_X)                                  # 横轴：BEV ↔ Multi
    if not compact:
        st.caption(T.QUAD_MAP_NOTE)
        if T.PARAM_BETA_DESC or T.PARAM_THETA_DESC:            # β/θ 解释（你写了才显示）
            st.divider()
            st.markdown(f"**{T.PARAM_READ_TITLE}**")
            if T.PARAM_BETA_DESC:
                st.markdown(f"- **β**：{T.PARAM_BETA_DESC}")
            if T.PARAM_THETA_DESC:
                st.markdown(f"- **θ**：{T.PARAM_THETA_DESC}")


# ══════════════════════════ 单一入口 · 三 tab + 顶部象限条 ══════════════════════════
st.title("新能源汽车区域选址 · 定价博弈沙盘")

with st.expander(T.QUAD_MAP_TITLE, expanded=True):            # 双 tab 上方 · 默认展开精简版
    _hl = st.session_state.get("p3_quad", list(C.QUAD_PROFILE.keys())[0])
    render_quadrant_map(highlight=_hl, compact=True)          # 高亮 Phase 3 里所选象限

tab_p2, tab_p3, tab_quad = st.tabs(
    ["Phase 2 · 财务解剖与价值裁决", "Phase 3 · 全国定价博弈与竞合", "象限地图"])
with tab_p2:
    render_phase2(config)
with tab_p3:
    render_phase3()
with tab_quad:
    render_quadrant_map()                                     # 详版
