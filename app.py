"""
NEV 沙盘 · 单一入口（两 tab：象限地图 / 沙盘）

Phase 4 归并版：原「Phase 2 财务解剖」与「Phase 3 定价博弈」两个 tab 合并为**一页沙盘**。
合并只动展示层（本文件），simulate.py / financials.py / game.py / calibration.py **一行未改**。

归并要点（详见 PHASE4 归并方案）：
- 定价滑块 P2/P3 **合一**（原来两根、互不相通，拨了一边另一边不动 —— 属真实混乱，本次修掉）。
- 原 P2「需求侧位移(demand_shift)」由 P3「生态投资」**正式接管**
  （闭合 PHASE1_audit_log §G4 挂了两阶段的 open item）。
- 原 P3「象限跟随 Phase 2」开关**删除**：一页只有一个象限选择器，天然同步。
- **城市 ⊥ 象限解耦**（Phase 3 §B 冻结）在 UI 上原样保持：城市不决定象限，
  两个选择器互不联动。`baseline[city]["quadrant"]` 只是该城基线企业碰巧所处的
  象限（数值层的一条记录），**不是城市的属性**，不得用它驱动界面行为。
- 「碳酸锂价格冲击」更名「关键原材料价格冲击（锂价冲击）」：通用名主标签 + NEV 别名进括号，
  落实宪章 §5 唯一红线（基座只认通用名）。它是**外生环境**、不是你的动作，故移出动作组。
- 控制台分两组：**我的动作**（定价 / 生态投资 / 联盟，守 ≤3）与
  **牌面与环境**（城市 / 象限 / 外生冲击 / 评判指标，不占动作预算，见宪章 §10.2 修订）。
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
import brief

st.set_page_config(page_title="NEV 沙盘 · 选址与定价博弈", layout="wide")

ensure_db()
config = cached_config()
cities = list(config["baseline"].keys())

CITY_CN = {"Shanghai": "上海", "Shenzhen": "深圳", "Hefei": "合肥",
           "Changzhou": "常州", "Xian": "西安", "Liuzhou": "柳州"}
cn_of = lambda r: CITY_CN.get(r, r)

# 四象限色板：**单一真相源在 copy_cn.QUAD_COLOR**，象限地图与图 C 共用，
# 保证卡片颜色与散点颜色一一对应（此前两处各写一套，对不上号）。
QUAD_COLOR = getattr(T, "QUAD_COLOR", {
    "Q1": "#0E9BAE", "Q2": "#6F5BD6", "Q3": "#0E9F6E", "Q4": "#E5A017"})
SECTION_COLOR = getattr(T, "SECTION_COLOR", {
    "A": "#12A47A", "B": "#0E9BAE", "C": "#6F5BD6"})


def _inject_css():
    """全局样式：圆角、卡片阴影、分区色带。主题色在 .streamlit/config.toml。"""
    st.markdown("""
    <style>
      /* 卡片：圆角 + 轻描边 + 极淡阴影，替代默认的直角灰框 */
      div[data-testid="stVerticalBlockBorderWrapper"] {
          border-radius: 14px !important;
          border: 1px solid rgba(18,164,122,.18) !important;
          box-shadow: 0 1px 3px rgba(20,38,31,.05);
      }
      /* 折叠面板、输入框、按钮统一圆角 */
      details, div[data-testid="stExpander"] { border-radius: 12px !important; }
      .stButton > button, .stDownloadButton > button,
      .stTextInput input, .stSelectbox div[data-baseweb="select"] > div {
          border-radius: 10px !important;
      }
      /* 分区标题：左侧色带 + 浅色底，做视觉引导 */
      .sec-head {
          border-left: 5px solid var(--accent);
          background: linear-gradient(90deg, var(--tint), transparent 65%);
          padding: .55rem .9rem; border-radius: 0 12px 12px 0; margin: .2rem 0 .1rem;
      }
      .sec-head .t { font-size: 1.12rem; font-weight: 700; color: #14261F; }
      .sec-head .s { font-size: .84rem; color: #5A6B64; margin-top: .15rem; }
      /* 控制台两组之间的呼吸位 */
      .grp-gap { height: 1.4rem; }
      /* 开关与滑块基线对齐（滑块比开关多一行数值） */
      .tgl-pad { height: 1.55rem; }
    </style>""", unsafe_allow_html=True)


def _section(key, title, sub=""):
    """带色带的分区标题。key ∈ {A,B,C}，颜色取自 copy_cn.SECTION_COLOR。"""
    accent = SECTION_COLOR.get(key, "#12A47A")
    tint = accent + "1F"                      # 同色 12% 透明度做底纹
    sub_html = f'<div class="s">{sub}</div>' if sub else ""
    st.markdown(
        f'<div class="sec-head" style="--accent:{accent};--tint:{tint}">'
        f'<div class="t">{title}</div>{sub_html}</div>', unsafe_allow_html=True)

# 归并用的两个展示层常数（**不属引擎**，只是把一根旋钮接到两台引擎上）：
PRICE_RANGE = (-30, 15)      # 合一后的定价区间，取 P3 口径（预设战略按此标定）
ECO_TO_DEMAND_PCT = 15.0     # 生态投资拨满 → 给 Phase 2 引擎的加性需求位移上限(%)
#   ↑ 原 P2「需求侧位移」滑块量程为 ±15%，此处以其正向上限做刻度对齐，
#     使「生态投资=0」严格等于「无位移」（t0 恒等不破）。属数值层设定，不求准。


def _t(name, default):
    """文案取自 copy_cn；本次归并新增的几条若 copy_cn 尚未补，先用内置默认值兜底。
    （宪章 §6：一切人话最终都应落进 copy_cn.py，这里只是过渡兜底，不是第二文案层。）"""
    return getattr(T, name, default)


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
    """图 B · 象限内竞争：份额 × 评判指标（纯竞争、无联盟）。"""
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
    """图 C · 区域/全国竞合：非价格吸引力 × 评判指标（跨象限、联盟连边）。"""
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
        # 滑块比开关多一行数值文本，补等高的占位块，让开关与滑块轨道同高
        st.markdown('<div class="tgl-pad"></div>', unsafe_allow_html=True)
        ally = st.toggle(" ", value=False, key="k_ally", label_visibility="collapsed")

    st.markdown('<div class="grp-gap"></div>', unsafe_allow_html=True)
    st.markdown(f"**{_t('CONSOLE_ENV_TITLE', '牌面与环境')}**"
                f"　:gray[{_t('CONSOLE_ENV_HINT', '（不是你的动作：牌面是给定的，冲击是外生的）')}]")
    e1, e2, e3, e4 = st.columns([1.2, 1.4, 2, 2], gap="large")
    with e1:
        city = st.selectbox("城市 / 选址", cities, format_func=cn_of, key="k_city",
                            help=_t("HELP_CITY", ""))
    with e2:
        quad = st.selectbox("战略象限", quads,
                            format_func=lambda x: T.QUAD_CELL[x]["short"], key="k_quad",
                            help=_t("HELP_QUAD", ""))
    with e3:
        shock = st.slider(_t("SLIDER_SHOCK", "关键原材料价格冲击（锂价冲击）%"),
                          -30, 60, 0, step=5, key="k_shock",
                          help=_t("HELP_SHOCK", ""))
    with e4:
        # 评判指标 = 纵轴用哪个指标。份额已是图 B 横轴，故不再作纵轴指标。
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

    _section("A", _t("SEC_A_TITLE", "A · 你自己"), _t("SEC_A_SUB", ""))
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
    dupont = {}
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
        dupont = {kk: dm[kk] for kk in
                  ("net_margin", "asset_turnover", "equity_multiplier")}

    return dict(roe_end=roe_end, spread_end=spr_end, has_ebit=has_ebit,
                beta_used=res["beta_used"], gamma_used=res["gamma_used"],
                demand_shift=demand_shift, **dupont)


# ══════════════════════════ 图 B/C 区（博弈）══════════════════════════
def render_game(k):
    """原 Phase 3：图 B 象限内竞争 / 图 C 跨象限竞合，并排。返回读数包（供简报）。"""
    city, quad, scorer = k["city"], k["quad"], k["scorer"]
    _section("B", _t("SEC_B_TITLE", "B · 你和对手"),
             f"{T.P3_INTRO}　{_t('SEC_B_SUB', '')}")

    # 当前象限提示 + 就地回看象限地图。
    # Streamlit 无法用程序切 tab，所以不做假链接：用 popover 把地图原地弹出来，
    # 比"点了跳不过去"的超链接诚实，也少一次来回。
    qc = QUAD_COLOR.get(quad, "#12A47A")
    h1, h2 = st.columns([3, 1])
    with h1:
        st.markdown(
            _t("CURRENT_QUAD_HINT", "当前所在象限：{quad}").format(
                quad=f'<span style="color:{qc};font-weight:700">'
                     f'{T.QUAD_CELL[quad]["short"]}</span>'),
            unsafe_allow_html=True)
    with h2:
        label = _t("QUAD_MAP_POPOVER", "查看象限地图")
        if hasattr(st, "popover"):
            with st.popover(label, use_container_width=True):
                render_quadrant_map(highlight=quad, compact=True, show_play=True)
        else:                                   # 老版本 Streamlit 降级
            with st.expander(label, expanded=False):
                render_quadrant_map(highlight=quad, compact=True, show_play=True)

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
    color = QUAD_COLOR.get(q, "#12A47A")
    with col.container(border=True):
        # 卡片标题用该象限的颜色 —— 与图 C 散点同色，一眼能对上号
        st.markdown(
            f'<div style="border-left:4px solid {color};padding-left:.5rem;'
            f'font-weight:700;color:{color}">{cell["name"]}</div>',
            unsafe_allow_html=True)
        if q == highlight:
            st.markdown(
                f'<div style="display:inline-block;margin:.35rem 0;padding:.1rem .5rem;'
                f'border-radius:8px;background:{color}22;color:{color};'
                f'font-size:.8rem;font-weight:600">◀ 你选的象限</div>',
                unsafe_allow_html=True)
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


# ══════════════════════════ C 段 · 商业分析简报 ══════════════════════════
def _pack_readout(k, self_read, game_read):
    """把两台引擎【已经算好】的读数装进 brief.Readout。

    🔴 这里只做搬运，不做任何计算 —— 简报里的每个数字都必须能在上方图表里
       逐字对上。一旦在这里动算术，就等于凭空造了第二个真相源。
    """
    v = game_read["verdict"]
    return brief.Readout(
        city=k["city"], city_cn=cn_of(k["city"]),
        quad=k["quad"], quad_cn=T.QUAD_CELL[k["quad"]]["short"],
        price_pct=k["price_pct"], eco=k["eco"], ally=k["ally"], shock_pct=k["shock"],
        ruler_cn=T.SCORER_NAMES.get(k["scorer"], k["scorer"]),
        roe_base=config["baseline"][k["city"]]["roe_base"],
        roe_end=self_read["roe_end"], spread_end=self_read["spread_end"],
        beta_used=self_read["beta_used"], gamma_used=self_read["gamma_used"],
        net_margin=self_read.get("net_margin"),
        asset_turnover=self_read.get("asset_turnover"),
        equity_multiplier=self_read.get("equity_multiplier"),
        verdict_state=v.get("state", "CREATE"),
        verdict_sentence=T.verdict_sentence(v),
        share=game_read["share"], share_rank=v.get("share_rank", "—"),
        spread_rank=v.get("spread_rank", "—"), spread_game=game_read["spread_game"],
        a_value=game_read["a_value"], in_alliance=game_read["in_alliance"],
        competition_cn=T.COMPETITION_CN.get(game_read["competition_type"], ""),
    )


def render_brief(k, self_read, game_read):
    """框一 API Key ＋ 框二 生成（并排）→ 框三 输出区（独占一行，只读）。

    框三只读、不接受追问：自由聊天会让用户去问"这个数字怎么算的"，
    而模型手里没有算式，只能编 —— 那正是红线要防的（宪章：非自由聊天框，
    由用户动作触发）。想换个说法，就回上面拨旋钮重生成。
    """
    _section("C", _t("SEC_C_TITLE", "C · 商业分析"), _t("BRIEF_INTRO", ""))

    # ── 框一 / 框二：并排一行 ──
    c1, c2 = st.columns([3, 1], gap="large")
    with c1:
        api_key = st.text_input(
            _t("APIKEY_LABEL", "您的 API Key"), type="password", key="k_apikey",
            placeholder=_t("APIKEY_PLACEHOLDER", ""), help=_t("HELP_APIKEY", ""))
        with st.expander(_t("APIKEY_STEPS_TITLE", "怎么获取 API Key？"), expanded=False):
            st.markdown(_t("APIKEY_STEPS", ""))
    with c2:
        st.markdown("&nbsp;", unsafe_allow_html=True)     # 与输入框基线对齐
        go = st.button(_t("BRIEF_BUTTON", "生成报告"), type="primary",
                       use_container_width=True)

    # ── 生成：仅在点击时调用；同一 trigger_key 本会话内命中缓存，不重复计费 ──
    if go:
        ro = _pack_readout(k, self_read, game_read)
        sig = (ro.trigger_key(), k["city"], k["price_pct"], k["eco"],
               k["ally"], k["shock"], bool(api_key))
        if st.session_state.get("brief_sig") != sig:
            with st.spinner(_t("BRIEF_SPINNER", "正在生成…")):
                st.session_state["brief_rep"] = brief.build(ro, api_key=api_key)
            st.session_state["brief_sig"] = sig

    rep = st.session_state.get("brief_rep")

    # ── 框三：输出区 ──
    with st.container(border=True):
        if rep is None:
            st.caption("填好上面的 Key 后点「生成报告」；留空也可以点，会显示演示版。")
            return

        if rep["mode"] == "live":
            st.caption(_t("BRIEF_MODE_LIVE", ""))
        else:
            st.warning(_t("BRIEF_MODE_FALLBACK", "以下为引擎读数版简报。"))
            if rep.get("error"):
                st.caption(f"{_t('BRIEF_ERROR_PREFIX', '调用未成功：')}{rep['error']}")

        st.markdown(brief.to_markdown(rep))

        # 导出：与屏上【同源同字】，不二次调用模型 —— 看到的即下载到的
        try:
            # 注意：f-string 内的表达式不可跨行（Python < 3.12 会 SyntaxError，
            # 而 Cloud 钉的是 3.11）→ 先算好文件名再拼路径。
            stem = rep["trigger_key"].replace("|", "_")
            path = brief.to_docx(rep, Path("/tmp") / f"brief_{stem}.docx")
            st.download_button(
                _t("BRIEF_DOWNLOAD", "下载 Word 简报"), data=path.read_bytes(),
                file_name=f"商业分析简报_{cn_of(k['city'])}_{k['quad']}.docx",
                mime=("application/vnd.openxmlformats-officedocument"
                      ".wordprocessingml.document"))
        except ImportError:
            st.caption("导出 Word 需要 python-docx：`pip install python-docx`")

        # 对账留痕：被丢弃的句子如实显示（宪章 §2 目标③ 诚实可审计）
        if rep.get("dropped"):
            with st.expander(f"出口对账丢弃了 {len(rep['dropped'])} 句", expanded=False):
                for slot, sent, why in rep["dropped"]:
                    st.caption(f"[{slot}] {sent} → {why}")


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

    # ── C 段 · 商业分析简报（Phase 4）──
    render_brief(k, self_read, game_read)

    st.divider()
    render_appendix(k["quad"])


# ══════════════════════════ 单一入口 · 两 tab ══════════════════════════
_inject_css()
st.title("新能源汽车区域选址 · 定价博弈沙盘")

tab_quad, tab_sandbox = st.tabs(["象限地图", "沙盘 · 定价博弈与价值裁决"])
with tab_quad:
    render_quadrant_map(highlight=st.session_state.get("k_quad"))
with tab_sandbox:
    render_sandbox()
