"""
NEV 沙盘 · 单一入口（两 tab：象限地图 / 沙盘）

Phase 4 归并版：原「Phase 2 财务解剖」与「Phase 3 定价博弈」两个 tab 合并为**一页沙盘**。
合并只动展示层（本文件），simulate.py / financials.py / game.py / calibration.py **一行未改**。

归并要点（详见 PHASE4 归并方案）：
- 定价滑块 P2/P3 **合一**（原来两根、互不相通，拨了一边另一边不动 —— 属真实混乱，本次修掉）。
- 原 P2「需求侧位移(demand_shift)」由 P3「生态投资」**正式接管**
  （闭合 PHASE1_audit_log §G4 挂了两阶段的 open item）。
- 原 P3「象限跟随 Phase 2」开关**删除**：一页只有一个象限选择器，天然同步。
- 「碳酸锂价格冲击」更名「关键原材料价格冲击（锂价冲击）」：通用名主标签 + NEV 别名进括号，
  落实宪章 §5 唯一红线（基座只认通用名）。它是**外生环境**、不是你的动作，故移出动作组。
- 控制台分两组：**我的动作**（定价 / 生态投资 / 联盟，守 ≤3）与
  **牌面与环境**（城市 / 象限 / 外生冲击 / 记分尺子，不占动作预算，见宪章 §10.2 修订）。
- 版面：结论前置 → 控制台 → 图A（我自己·上下双线）→ 图B|图C（并排·打价格 vs 结生态）
        → 总裁办简报（Phase 4 占位）→ 折叠区（象限地图 / 参数恢复表 / 诚实声明）。

Run:  streamlit run app.py
"""
from pathlib import Path
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

from ensure_db import ensure_db
from calibration import recovery_table, cached_config
from simulate import simulate_roe
import financials
import game
import config as C
import copy_cn as T

st.set_page_config(page_title="NEV 沙盘 · 选址与定价博弈", layout="wide")

ensure_db()
config = cached_config()
cities = list(config["baseline"].keys())

CITY_CN = {"Shanghai": "上海", "Shenzhen": "深圳", "Hefei": "合肥",
           "Changzhou": "常州", "Xian": "西安", "Liuzhou": "柳州"}
cn_of = lambda r: CITY_CN.get(r, r)

# 图二散点按象限上色（上排 Premium 用暖色系、下排 Mass 用冷色系，与象限地图的行向一致）
QUAD_COLOR = {
    "Q1": "#8E5BD0",   # 高端 · 纯电
    "Q2": "#C9457E",   # 高端 · 多路线
    "Q3": "#2E8B78",   # 中低端 · 多路线
    "Q4": "#3B7DD8",   # 中低端 · 纯电
}

# 归并用的两个展示层常数（**不属引擎**，只是把一根旋钮接到两台引擎上）：
PRICE_RANGE = (-30, 15)      # 合一后的定价区间，取 P3 口径（预设战略按此标定）
ECO_TO_DEMAND_PCT = 15.0     # 生态投资拨满 → 给 Phase 2 引擎的加性需求位移上限(%)
#   ↑ 原 P2「需求侧位移」滑块量程为 ±15%，此处以其正向上限做刻度对齐，
#     使「生态投资=0」严格等于「无位移」（t0 恒等不破）。属数值层设定，不求准。


def _t(name, default):
    """文案取自 copy_cn；本次归并新增的几条若 copy_cn 尚未补，先用内置默认值兜底。
    （宪章 §6：一切人话最终都应落进 copy_cn.py，这里只是过渡兜底，不是第二文案层。）"""
    return getattr(T, name, default)


def _home_quadrant(city):
    """该城市在 nev.db 基线里所属的象限（图 A 的 β/成长阶段就锚在它上面）。"""
    return config["baseline"].get(city, {}).get("quadrant")


def _follow_city():
    """换城市 → 象限默认跟到该城的本位象限（用户仍可自行改成别的做推演）。
    默认状态下两台引擎的价格起点因此天然对齐（实测比值 0.86–1.03）；
    也让「选址禀赋 → 象限战略」这条因果链在界面上真的显出来：
    城市不是筛选器，它带着一份禀赋和一个默认定位。"""
    hq = _home_quadrant(st.session_state.get("k_city"))
    if hq:
        st.session_state["k_quad"] = hq


# 首次进入：象限落在首个城市的本位象限上（必须在 widget 渲染前写 session_state）
if "k_quad" not in st.session_state:
    _hq0 = _home_quadrant(cities[0])
    if _hq0:
        st.session_state["k_quad"] = _hq0


def _index_of(options, value, fallback=0):
    try:
        return options.index(value)
    except (ValueError, AttributeError):
        return fallback


# ══════════════════════════ 图 A · 我自己（ROE / 价值利差 上下双线）══════════════════════════
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


# ══════════════════════════ 图 B / 图 C · 博弈散点 ══════════════════════════
def _fig_arena(c1, y_key, y_lab):
    """图 B · 象限内竞争：份额 × 记分尺子（纯竞争、无联盟）。"""
    fig = go.Figure()
    xs = [p["share"] for p in c1["points"]]
    ys = [p.get(y_key) for p in c1["points"]]
    labels = [("你" if p["is_user"] else p["firm_id"]) for p in c1["points"]]
    colors = ["#e4572e" if p["is_user"] else "#4c9be8" for p in c1["points"]]
    sizes = [26 if p["is_user"] else 15 for p in c1["points"]]
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers+text", text=labels, textposition="top center",
        marker=dict(size=sizes, color=colors, line=dict(width=1, color="white")),
        hovertext=[f"{l}｜售价 {p['price']/1e4:.1f}万｜份额 {p['share']:.0%}"
                   f"｜{y_lab} {T.fmt_pct(p.get(y_key))}"
                   for l, p in zip(labels, c1["points"])],
        hoverinfo="text", showlegend=False))
    fig.add_hline(y=0, line=dict(color="#C0392B", dash="dash"),
                  annotation_text=T.ZERO_LINE_P3, annotation_position="top left",
                  annotation_font=dict(color="#C0392B", size=11))
    fig.update_xaxes(title_text=T.CHART1_XAXIS, tickformat=".0%")
    fig.update_yaxes(title_text=y_lab)
    fig.update_layout(height=420, margin=dict(t=40, b=50, l=55, r=20))
    return fig


def _fig_eco(c2, y_key, y_lab):
    """图 C · 区域/全国竞合：非价格吸引力 × 记分尺子（跨象限、联盟连边）。"""
    fig = go.Figure()
    pt_by_id = {p["firm_id"]: p for p in c2["points"]}
    for e in c2["edges"]:
        a, b = pt_by_id.get(e["a"]), pt_by_id.get(e["b"])
        if a and b:
            fig.add_trace(go.Scatter(
                x=[a["a_value"], b["a_value"]], y=[a.get(y_key), b.get(y_key)],
                mode="lines", line=dict(width=2, color="rgba(120,180,120,0.7)", dash="dot"),
                hoverinfo="skip", showlegend=False))

    def _hover(p, lab):
        return (f"{lab}｜{p['quad']}｜非价格吸引力 {p['a_value']:.2f}"
                f"｜{y_lab} {T.fmt_pct(p.get(y_key))}"
                + ("｜在盟" if p["in_alliance"] else ""))

    for qd in ["Q1", "Q2", "Q3", "Q4"]:
        pts = [p for p in c2["points"] if p["quad"] == qd and not p["is_user"]]
        if not pts:
            continue
        fig.add_trace(go.Scatter(
            x=[p["a_value"] for p in pts], y=[p.get(y_key) for p in pts],
            mode="markers+text", text=[p["firm_id"] for p in pts],
            textposition="top center", name=T.QUAD_CELL[qd]["short"],
            marker=dict(size=14, color=QUAD_COLOR[qd],
                        line=dict(width=[2.2 if p["in_alliance"] else 1 for p in pts],
                                  color=["#3d3d3d" if p["in_alliance"] else "white"
                                         for p in pts])),
            hovertext=[_hover(p, p["firm_id"]) for p in pts],
            hoverinfo="text", showlegend=True, legendgroup=qd))

    you_pts = [p for p in c2["points"] if p["is_user"]]
    if you_pts:
        fig.add_trace(go.Scatter(
            x=[p["a_value"] for p in you_pts], y=[p.get(y_key) for p in you_pts],
            mode="markers+text", text=["你"], textposition="top center", name="你",
            marker=dict(size=26, color="#e4572e",
                        line=dict(width=[2.2 if p["in_alliance"] else 1 for p in you_pts],
                                  color=["#3d3d3d" if p["in_alliance"] else "white"
                                         for p in you_pts])),
            hovertext=[_hover(p, "你") for p in you_pts],
            hoverinfo="text", showlegend=True))

    fig.add_hline(y=0, line=dict(color="#C0392B", dash="dash"),
                  annotation_text=T.ZERO_LINE_P3, annotation_position="top left",
                  annotation_font=dict(color="#C0392B", size=11))
    fig.update_xaxes(title_text=T.CHART2_XAXIS)
    fig.update_yaxes(title_text=y_lab)
    fig.update_layout(height=420, margin=dict(t=40, b=90, l=55, r=20),
                      legend=dict(orientation="h", yanchor="top", y=-0.16,
                                  xanchor="center", x=0.5, title_text="象限"))
    return fig


# ══════════════════════════ 控制台 ══════════════════════════
def render_console():
    """一页一个控制台。返回全部旋钮/牌面状态（同时也是 Phase 4 简报的动作快照来源）。"""
    quads = list(C.QUAD_PROFILE.keys())

    st.markdown(f"**{_t('CONSOLE_ACTION_TITLE', '我的动作')}**")
    a1, a2, a3 = st.columns([2, 2, 1], gap="large")
    with a1:
        price_pct = st.slider(T.SLIDER_PRICE, PRICE_RANGE[0], PRICE_RANGE[1], 0, step=1,
                              key="k_price", help=_t("HELP_PRICE", ""))
    with a2:
        eco = st.slider(T.SLIDER_ECO, 0.0, C.ECO_SLIDER_MAX, 0.0, step=0.05, key="k_eco",
                        help=_t("HELP_ECO", ""))
    with a3:
        st.markdown(T.TOGGLE_ALLY)
        ally = st.toggle(" ", value=False, key="k_ally", label_visibility="collapsed")

    st.markdown(f"**{_t('CONSOLE_ENV_TITLE', '牌面与环境')}**"
                f"　:gray[{_t('CONSOLE_ENV_HINT', '（不是你的动作：牌面是给定的，冲击是外生的）')}]")
    e1, e2, e3, e4 = st.columns([1.2, 1.4, 2, 2], gap="large")
    with e1:
        city = st.selectbox("城市 / 选址", cities, format_func=cn_of, key="k_city",
                            on_change=_follow_city, help=_t("HELP_CITY", ""))
    with e2:
        quad = st.selectbox("战略象限", quads,
                            format_func=lambda x: T.QUAD_CELL[x]["short"], key="k_quad",
                            help=_t("HELP_QUAD", ""))
        _hq = _home_quadrant(city)
        if _hq and quad != _hq and _t("QUAD_OFF_HOME", ""):
            st.caption(_t("QUAD_OFF_HOME", "").format(home=T.QUAD_CELL[_hq]["short"]))
    with e3:
        shock = st.slider(_t("SLIDER_SHOCK", "关键原材料价格冲击（锂价冲击）%"),
                          -30, 60, 0, step=5, key="k_shock",
                          help=_t("HELP_SHOCK", ""))
    with e4:
        # 记分尺子 = 纵轴用哪把量尺。份额已是图 B 横轴，不再作纵轴尺子。
        ruler_opts = [k for k in T.SCORER_NAMES if k != "share"]
        scorer = st.radio(T.SCORER_LABEL, ruler_opts, horizontal=True,
                          format_func=lambda s: T.SCORER_NAMES[s], key="k_ruler")

    with st.expander(T.PRESET_TITLE, expanded=False):
        st.caption(T.PRESET_HINT)
        pcols = st.columns(len(T.PRESET_STRATEGIES))
        for col, (_pid, _p) in zip(pcols, T.PRESET_STRATEGIES.items()):
            with col:
                if st.button(_p["name"], key=f"preset_{_pid}", use_container_width=True):
                    # 只替用户拨已有旋钮，不新增旋钮、不碰引擎。
                    st.session_state["k_price"] = _p["knobs"]["price"]
                    st.session_state["k_eco"] = _p["knobs"]["eco"]
                    st.session_state["k_ally"] = _p["knobs"]["ally"]
                    st.session_state["preset_active"] = _pid
                    st.rerun()
                st.caption(_p["desc"])
        _act = st.session_state.get("preset_active")
        if _act:
            st.caption(f"当前预设：**{T.PRESET_STRATEGIES[_act]['name']}**（继续拨旋钮即可自由微调）")

    return dict(city=city, quad=quad, price_pct=price_pct, eco=eco,
                ally=ally, shock=shock, scorer=scorer)


# ══════════════════════════ 图 A 区（我自己）══════════════════════════
def render_self(k):
    """原 Phase 2：ROE 射线 + 价值利差射线 + 动态裁决 + 基线杜邦。返回读数包（供简报）。"""
    city, quad = k["city"], k["quad"]
    # 生态投资 → 需求侧位移（%）：原第三滑块的正式驱动通道
    demand_shift = k["eco"] / C.ECO_SLIDER_MAX * ECO_TO_DEMAND_PCT if C.ECO_SLIDER_MAX else 0.0
    sliders = dict(price_change=k["price_pct"], lithium_shock=k["shock"],
                   demand_shift=demand_shift)
    res = simulate_roe(city, sliders, config)

    has_ebit = res.get("ebit_p50") is not None
    spr_p05 = spr_p50 = spr_p95 = None
    if has_ebit:
        def _spread_of(ebit_line):
            sl = financials.spread_line(
                np.array(ebit_line), quadrant=quad,
                shareholders_equity=res["shareholders_equity"],
                interest_bearing_debt=res["interest_bearing_debt"],
                cash_and_equivalents=res["cash_and_equivalents"],
                tax_rate=res["tax_rate"])
            return [None if (x != x) else float(x) for x in sl["spread"]]   # NaN→None
        spr_p05, spr_p50, spr_p95 = (_spread_of(res["ebit_p05"]),
                                     _spread_of(res["ebit_p50"]),
                                     _spread_of(res["ebit_p95"]))

    skey = f"prev::{city}"
    prev = st.session_state.get(skey)

    st.markdown(f"#### {_t('SEC_A_TITLE', 'A · 你自己：账面赚不赚，价值创没创造')}")
    if _t("SEC_A_SUB", ""):
        st.caption(_t("SEC_A_SUB", ""))
    st.caption(f"基准 ROE：`{config['baseline'][city]['roe_base']:+.1%}`"
               "　（基准财报取该城基线；象限只切换资本成本口径）")

    g1, g2 = st.columns(2, gap="large")
    with g1:
        st.markdown(f"**{T.PANEL_ROE_TITLE}**")
        roe_fig = _panel(res["days"], res["roe_p05"], res["roe_p50"], res["roe_p95"],
                         (prev["roe"] if prev else None), "#185FA5", "rgba(24,95,165,A%)",
                         T.AXIS_ROE_LABEL, zero_ref=False, zero_label="",
                         base_ref=res["roe_base"], base_label=T.ROE_BASE_LABEL,
                         this_label=T.SHADE_THIS_LABEL, prev_label=T.SHADE_PREV_LABEL)
        roe_fig.update_layout(xaxis_title=T.AXIS_TIME_LABEL)
        st.plotly_chart(roe_fig, use_container_width=True)
        if T.ROE_NOTE:
            st.caption(T.ROE_NOTE)
    with g2:
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
    if prev and T.SHADE_NOTE:
        st.caption(T.SHADE_NOTE)

    if has_ebit:
        st.session_state[skey] = dict(roe=res["roe_p50"], spr=spr_p50)

    roe_end = res["roe_p50"][-1]
    spr_end = spr_p50[-1] if has_ebit else None
    if has_ebit:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(T.label("roe"), f"{roe_end:+.1%}", f"{res['roe_delta_end']:+.1%} vs 基准",
                  help=T.tip("roe"))
        m2.metric(T.label("spread"), (f"{spr_end:+.1%}" if spr_end is not None else "—"),
                  help=T.tip("spread"))
        m3.metric("β / γ 采用", f"{res['beta_used']:.2f} / {res['gamma_used']:.2f}")
        m4.metric("象限", quad)
        if spr_end is not None:
            v = f"{abs(spr_end) * 100:.0f}"
            if spr_end > 0:
                st.success(T.VERDICT_CREATE.format(v=v))
            elif roe_end > 0:
                st.error(T.VERDICT_WINSALES_LOSEVALUE.format(v=v))
            else:
                st.error(T.VERDICT_DESTROY.format(v=v))
        else:
            st.warning(T.VERDICT_NA)

    # 基线杜邦（t0 结构解剖，静态）
    bb = config["baseline"][city]
    if all(key in bb for key in ("total_revenue", "total_assets")):
        dm = financials.compute_value_metrics(
            operating_income=bb["ebit_base"], net_income=bb["net_income"],
            total_revenue=bb["total_revenue"], total_assets=bb["total_assets"],
            shareholders_equity=bb["equity"], interest_bearing_debt=bb["interest_bearing_debt"],
            cash_and_equivalents=bb["cash_and_equivalents"], quadrant=quad,
            tax_rate=bb["tax_rate"])
        if T.DUPONT_FORMULA:
            st.caption(T.DUPONT_FORMULA)
        d1, d2, d3 = st.columns(3)
        d1.metric(T.label("net_margin"), f"{dm['net_margin']:+.1%}", help=T.tip("net_margin"))
        d2.metric(T.label("asset_turnover"), f"{dm['asset_turnover']:.2f}",
                  help=T.tip("asset_turnover"))
        d3.metric(T.label("equity_multiplier"), f"{dm['equity_multiplier']:.2f}",
                  help=T.tip("equity_multiplier"))

    return dict(roe_end=roe_end, spread_end=spr_end, has_ebit=has_ebit,
                beta_used=res["beta_used"], gamma_used=res["gamma_used"],
                demand_shift=demand_shift)


# ══════════════════════════ 图 B/C 区（博弈）══════════════════════════
def render_game(k):
    """原 Phase 3：图 B 象限内竞争 / 图 C 跨象限竞合，并排。返回读数包（供简报）。"""
    city, quad, scorer = k["city"], k["quad"], k["scorer"]
    st.markdown(f"#### {_t('SEC_B_TITLE', 'B · 你和对手：打价格战，还是结生态')}")
    st.caption(f"{T.P3_INTRO}　{_t('SEC_B_SUB', '')}")

    p0 = game.build_user_firm(city, quad)["p0"]
    user_price = p0 * (1.0 + k["price_pct"] / 100.0)
    c1 = game.chart_one(city, quad, user_price=user_price, eco_invest=k["eco"])
    c2 = game.chart_two(city, quad, eco_invest=k["eco"], alliance_on=k["ally"])
    y_lab = T.SCORER_NAMES[scorer]

    b, c = st.columns(2, gap="large")
    with b:
        st.markdown(f"**{T.CHART1_TITLE}**")
        st.plotly_chart(_fig_arena(c1, scorer, y_lab), use_container_width=True)
        st.caption(T.CHART1_SUB)
    with c:
        st.markdown(f"**{T.CHART2_TITLE}**")
        st.plotly_chart(_fig_eco(c2, scorer, y_lab), use_container_width=True)
        st.caption(T.CHART2_SUB)

    v = c1["verdict"]
    you1 = next(p for p in c1["points"] if p["is_user"])
    you2 = next(p for p in c2["points"] if p["is_user"])
    flip = T.READOUT_FLIP if v.get("ruler_flip") else ""
    r1 = T.READOUT_C1.format(share=you1["share"], spread=T.fmt_pct(you1["spread"]),
                             srank=v.get("share_rank", "—"), vrank=v.get("spread_rank", "—"),
                             flip=flip)
    r2 = T.READOUT_C2.format(a=you2["a_value"], spread=T.fmt_pct(you2.get(scorer)),
                             ally=(T.READOUT_ALLY if k["ally"] else ""))
    col_a, col_b = st.columns(2)
    col_a.markdown(f"**{_t('READOUT_TITLE_C1', '图 B 读数 · 象限内竞争')}**"); col_a.write(r1)
    col_a.caption(f"竞争类型：{T.COMPETITION_CN[c1['competition_type']]}（θ={C.THETA_Q[quad]}）")
    col_b.markdown(f"**{_t('READOUT_TITLE_C2', '图 C 读数 · 区域 / 全国竞合')}**"); col_b.write(r2)

    return dict(verdict=v, share=you1["share"], spread_game=you1["spread"],
                a_value=you2["a_value"], in_alliance=you2["in_alliance"],
                competition_type=c1["competition_type"])


# ══════════════════════════ 象限地图 ══════════════════════════
def _quad_stats(q):
    """从 config 真值拼该象限的 β/θ/ASP/毛利 —— 进卡片 ⓘ tooltip，与引擎同源、不手抄。"""
    b = C.BETA_DEMAND[q]
    th = C.THETA_Q[q]
    lo, hi = C.QUAD_PROFILE[q]["asp"]
    m0, m1 = C.QUAD_PROFILE[q]["margin"]
    return (f"价格弹性 β {b} · 定价权 θ {th} · "
            f"ASP {lo/1e4:g}–{hi/1e4:g}万 · 毛利 {m0*100:.0f}–{m1*100:.0f}%")


def _quad_card(col, q, highlight=None, compact=False, show_play=True):
    cell = T.QUAD_CELL[q]
    with col.container(border=True):
        st.markdown(f"**{cell['name']}**")
        if q == highlight:
            st.markdown(":blue-background[◀ 你选的象限]")
        if compact:
            if show_play:
                st.caption(f"打法 · {cell['play']}")
        else:
            st.markdown(f"**{T.QUAD_FIELD['feature']}**：{cell['feature']}")
            st.markdown(f"**{T.QUAD_FIELD['anchors']}**：{cell['anchors']}")
            st.markdown(f"**{T.QUAD_FIELD['strategy']}**：{cell['strategy']}")
            st.markdown(f"**{T.QUAD_FIELD['params']}**：{_quad_stats(q)}")


def render_quadrant_map(highlight=None, compact=False, show_play=True):
    """2×2 象限地图。compact=True 为精简条（名称 + 可选策略一行）；否则为「象限地图」tab 详版。"""
    if not compact:
        st.subheader(T.QUAD_MAP_TITLE)
        st.caption(T.QUAD_MAP_INTRO)
    st.caption(T.QUAD_AXIS_Y_TOP)
    r1c1, r1c2 = st.columns(2)
    _quad_card(r1c1, "Q1", highlight, compact, show_play)
    _quad_card(r1c2, "Q2", highlight, compact, show_play)
    r2c1, r2c2 = st.columns(2)
    _quad_card(r2c1, "Q4", highlight, compact, show_play)
    _quad_card(r2c2, "Q3", highlight, compact, show_play)
    st.caption(T.QUAD_AXIS_Y_BOT)
    st.caption(T.QUAD_AXIS_X)
    if not compact:
        st.caption(T.QUAD_MAP_NOTE)
        if T.PARAM_BETA_DESC or T.PARAM_THETA_DESC:
            st.divider()
            st.markdown(f"**{T.PARAM_READ_TITLE}**")
            if T.PARAM_BETA_DESC:
                st.markdown(f"- **β**：{T.PARAM_BETA_DESC}")
            if T.PARAM_THETA_DESC:
                st.markdown(f"- **θ**：{T.PARAM_THETA_DESC}")


# ══════════════════════════ 折叠区 ══════════════════════════
def render_appendix(quad):
    with st.expander(T.QUAD_MAP_TITLE, expanded=False):
        render_quadrant_map(highlight=quad, compact=True, show_play=True)
    with st.expander("参数恢复表　(回归估计 vs 埋入真值 · 项目立身之本)", expanded=False):
        tab = recovery_table()
        show = tab.assign(
            covered=tab.covered.map({True: "✓", False: "✗"})
        ).rename(columns={"coefficient": "系数", "key": "象限/区域", "truth": "真值",
                          "estimate": "回归估计", "ci_low": "CI下", "ci_high": "CI上",
                          "std_err": "标准误", "covered": "覆盖", "r2": "R²", "n": "样本"})
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.caption(f"CI 覆盖真值：{int(tab.covered.sum())}/{len(tab)}　"
                   "· 覆盖即证明系数是从数据恢复、而非编造")
    with st.expander("关于 / 诚实声明", expanded=False):
        st.caption(T.PROXY_NOTE_P3)


# ══════════════════════════ 沙盘主页 ══════════════════════════
def render_sandbox():
    st.caption("选址禀赋 → 象限战略 → 定价博弈 → 财务价值裁决 · "
               "系数由 nev.db 回归恢复，非手填")
    headline = st.container()          # 结论前置：先占位，算完回填（宪章 §6）

    k = render_console()
    st.divider()
    self_read = render_self(k)
    st.divider()
    game_read = render_game(k)
    st.divider()

    # ── 首屏一句人话结论：以博弈四态裁决为准（它含名次，信息量最大）──
    with headline:
        st.markdown(f"### {T.verdict_sentence(game_read['verdict'])}")

    # ── 总裁办简报（Phase 4 · 待建）──
    st.markdown(f"#### {_t('SEC_C_TITLE', 'C · 总裁办简报')}")
    st.info(_t("BRIEF_PLACEHOLDER", "Phase 4 建设中：简报区。"))

    st.divider()
    render_appendix(k["quad"])


# ══════════════════════════ 单一入口 · 两 tab ══════════════════════════
st.title("新能源汽车区域选址 · 定价博弈沙盘")

tab_quad, tab_sandbox = st.tabs(["象限地图", "沙盘 · 定价博弈与价值裁决"])
with tab_quad:
    render_quadrant_map(highlight=st.session_state.get("k_quad"))
with tab_sandbox:
    render_sandbox()
