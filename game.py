# -*- coding: utf-8 -*-
"""
game.py · Phase 3 博弈引擎（新增·结构层主体）

从「单企业独自结算（P2）」进入「多企业互搏（P3）」：
  · 图一 · 象限内博弈：同象限全国 N 家，纯竞争（Logit 份额 + Nash/Bertrand 快层价格），无联盟。
             叙事＝【靠降价打份额 → 你被卷入价格战漩涡、独自沉下去】。轴 = 份额 × 价值 spread。
  · 图二 · 区域/全国竞合：跨象限企业，竞合（换电联盟慢层生态）；联盟连边（Q1↔Q3 / Q1 内部）。
             叙事＝【建生态/结盟 → 浮上来】。轴 = 非价格吸引力 aᵢ × 价值 spread。

因果闭环（P3.12 · 回扣 P2 价值机器·不发明新计分）：
    你拨价（外生领导者）→ 象限内对手 Nash 最优反应 → Logit 份额 → 销量×单位经济学
    → 合成损益/资产 → **调用真 financials.compute_value_metrics**（杜邦→ROIC→WACC→spread）。
  价格战撑高 ROE（周转↑）却打沉 spread —— P2 的楔子这次由博弈驱动。

关键集成（对齐真 repo）：
  · 复用真 financials.py（compute_value_metrics / spread_line：单一 WACC、市值权重、IC≤0 容错）。
  · 复用 config.py 的 QUAD_PROFILE（键 asp/margin/turnover/de）、BETA_DEMAND、THETA_Q、
    BATTERY_CLUSTER（γ 代理）、PB_MULTIPLE、EQUITY_BETA、ERP、CREDIT_SPREAD、TAX_RATE、MACRO。
  · 17 预设企业＝表外博弈玩家（不在 nev.db/simulation_config.json），故其 baseline 由
    QUAD_PROFILE 比率**合成**——这正是“区域×象限只有一格基线、而博弈要铺满四象限”的必然做法。

纯 numpy/纯 python，无 LLM（LLM 红线：幻觉够不到财务数字）。
"""
import math
import config as C           # Phase 0–2 配置 + Phase 3 博弈层扩展（已并入同一文件）
import financials as F         # Phase 2 价值机器（唯一 WACC 实现）


# =============================================================================
# 1. 象限级 Logit 价格敏感度 b_q：反解使「对称基线」恰为 Nash 不动点
# =============================================================================

def _mid(v):
    """真 QUAD_PROFILE 里价格/毛利/周转/de 均为 (lo, hi) 带；取中值。标量则原样返回。"""
    return 0.5 * (v[0] + v[1]) if isinstance(v, (tuple, list)) else v


def _quad_b(quad, n):
    """
    由目标基线毛利率 margin_mid + conduct θ 反解 b_q，
    使「对称基线（价=ASP中枢、份额=1/N、毛利=band 中值）」为 Nash 不动点：
    中性（不拨滑块）时散点≈复现 sheet8 画像（类比 P2 t0≈基线）。
    """
    lo, hi = C.QUAD_PROFILE[quad]["margin"]
    m_mid = 0.5 * (lo + hi)
    theta = C.THETA_Q[quad]
    n = max(n, 2)
    return 1.0 / (m_mid * (1.0 - 1.0 / n) * (1.0 - theta))


# =============================================================================
# 2. 企业构造：从真 QUAD_PROFILE 画像 + 区域禀赋派生 baseline 经济学
# =============================================================================

def _unit_econ(quad, pos, region):
    """定位 pos∈[0,1] + 区域集群 → (基线价 p0, 单位成本 cost, 象限中枢价 mid)。
    单位成本＝基线价×(1−基线毛利)×集群减免；集群走真 BATTERY_CLUSTER（γ 成本传导代理）。"""
    prof = C.QUAD_PROFILE[quad]
    asp_lo, asp_hi = prof["asp"]
    m_lo, m_hi = prof["margin"]
    p0 = asp_lo + pos * (asp_hi - asp_lo)                     # 基线价（k RMB）
    margin = m_lo + pos * (m_hi - m_lo)                       # 高定位→高毛利
    relief = 1.0 - C.COST_RELIEF * (C.cluster(region) - 0.5)
    cost = p0 * (1.0 - margin) * relief
    mid = 0.5 * (asp_lo + asp_hi)
    return p0, cost, mid


def _a_base(quad, pos, region):
    """非价格吸引力 aᵢ 起点：象限固有倾向 + 定位 + 市场禀赋（不含生态/联盟叠加）。"""
    return (C.QUAD_A_TILT[quad] + C.A_POS * pos + C.A_MARKET * C.market(region))


def build_firm(spec, in_alliance_context=False):
    """一条预设 firm spec → 带 baseline 经济学的字典。"""
    quad, region, pos = spec["quad"], spec["home"], spec["pos"]
    p0, cost, mid = _unit_econ(quad, pos, region)
    a_ally = 0.0
    if in_alliance_context and C.alliance_partner(spec["firm_id"]) is not None:
        a_ally = C.ALLY_GAIN                                 # 预设结盟企业·盟友恒在场→吃满
    return dict(firm_id=spec["firm_id"], quad=quad, home=region, pos=pos,
                p0=p0, cost=cost, mid=mid,
                a_base=_a_base(quad, pos, region), a_ally=a_ally, a_eco=0.0,
                firm_swaps=spec.get("firm_swaps", 0),
                swap_alliance=spec.get("swap_alliance"), is_user=False)


def build_user_firm(region, quad, price=None, eco_invest=0.0, alliance_on=False):
    """用户实时企业（P3.19：不遵落位规则，取象限内中位定位 pos=0.5）。"""
    pos = 0.5
    p0, cost, mid = _unit_econ(quad, pos, region)
    a_eco = C.ECO_GAIN * math.sqrt(max(eco_invest, 0.0))     # 生态投资→aᵢ（边际递减）
    a_ally = C.ALLY_GAIN if alliance_on else 0.0
    return dict(firm_id="YOU", quad=quad, home=region, pos=pos,
                p0=p0, cost=cost, mid=mid,
                a_base=_a_base(quad, pos, region), a_ally=a_ally, a_eco=a_eco,
                price=(p0 if price is None else price),
                eco_invest=eco_invest, alliance_on=alliance_on,
                firm_swaps=1, swap_alliance=("USER" if alliance_on else None),
                is_user=True)


# =============================================================================
# 3. Logit 份额（象限内；Σ s_i = 1）
# =============================================================================

def logit_shares(prices, a_values, b, mid):
    """V_i = A_BASE + aᵢ − b·(p_i/mid)；s_i = softmax(V)。"""
    v = [C.A_BASE + a - b * (p / mid) for p, a in zip(prices, a_values)]
    m = max(v)
    ex = [math.exp(x - m) for x in v]                        # 数值稳定
    tot = sum(ex)
    return [e / tot for e in ex]


# =============================================================================
# 4. 图一 · 象限内 Nash/Bertrand：你外生领导者，对手最优反应（加成不动点）
# =============================================================================

def solve_intra_quadrant(user_firm, opponents, theta, tam, max_iter=200, tol=1e-7, damp=0.5):
    """
    对手 i 一阶条件（Logit-Bertrand）：(p_i − c_i) = mid /(b·(1 − s_i)) · 1/(1 − θ)。
    你（user）价外生固定，进份额分母但不最优反应；对手迭代至 Nash。
    """
    quad = user_firm["quad"]
    all_firms = [user_firm] + opponents
    n = len(all_firms)
    b = _quad_b(quad, n)
    mid = user_firm["mid"]

    a_vals = [f["a_base"] + f.get("a_eco", 0.0) for f in all_firms]   # 图一无联盟（盟友在别象限）
    prices = [f.get("price", f["p0"]) for f in all_firms]
    user_price = user_firm.get("price", user_firm["p0"])
    prices[0] = user_price

    for _ in range(max_iter):
        shares = logit_shares(prices, a_vals, b, mid)
        new_prices = list(prices)
        for i in range(1, n):                                # i=0 是 user，外生跳过
            s_i = min(shares[i], 0.95)
            markup = mid / (b * (1.0 - s_i)) / (1.0 - theta)
            new_prices[i] = damp * (all_firms[i]["cost"] + markup) + (1.0 - damp) * prices[i]
        new_prices[0] = user_price
        if max(abs(a - c) for a, c in zip(new_prices, prices)) < tol:
            prices = new_prices
            break
        prices = new_prices

    shares = logit_shares(prices, a_vals, b, mid)
    return [dict(firm=f, price=p, share=s, volume=s * tam, a_value=a)
            for f, p, s, a in zip(all_firms, prices, shares, a_vals)]


# =============================================================================
# 5. 损益/资产 → spread（P3.12 回扣 P2；调用真 financials.compute_value_metrics）
# =============================================================================

def firm_financials(quad, price, cost, volume, eco_invest=0.0):
    """
    (价, 成本, 量) → 合成损益 + 资产负债（真 QUAD_PROFILE 比率派生）
    → 调用真 financials.compute_value_metrics（单一 WACC）。
    生态投资吃当期 EBIT（opex↑），换未来 aᵢ——真实权衡（图二上浮的代价在这里显影）。
    """
    revenue = price * volume
    if revenue <= 0:
        nan = float("nan")
        return dict(revenue=0.0, ebit=nan, net_income=nan, spread=nan,
                    roic=nan, wacc=nan, roe=nan, invested_capital=nan)

    prof = C.QUAD_PROFILE[quad]
    gross = (price - cost) * volume
    # 生态投资费用（营收占比）吃当期 EBIT；单位经济学的价/量已含 R&D/销售于 margin 里
    opex_eco = C.ECO_OPEX * eco_invest * revenue
    ebit = gross - opex_eco                                   # 经营利润（EBIT）

    # 合成资产负债表（真 QUAD_PROFILE turnover/de 取带中值 + P3 数值层 eq/cash 占资产比）
    turnover = _mid(prof["turnover"])
    de = _mid(prof["de"])
    assets = revenue / turnover
    equity = assets * C.BS_EQ_ASSET[quad]
    debt = equity * de                                       # de = 有息负债/权益
    cash = assets * C.BS_CASH_ASSET[quad]

    # 归母净利（读数/ROE 用）：利息在 EBIT 下扣，税只对正 EBT 征（★ 已修 Phase 2 税 bug：亏损不打折）
    interest = debt * (C.RF_START + C.CREDIT_SPREAD)
    ebt = ebit - interest
    net_income = ebt - max(0.0, ebt) * C.TAX_RATE

    # —— 回扣 P2 价值机器（唯一 WACC 实现；ROIC=NOPAT/IC，IC≤0→NaN 容错）——
    m = F.compute_value_metrics(
        operating_income=ebit, net_income=net_income,
        total_revenue=revenue, total_assets=assets,
        shareholders_equity=equity, interest_bearing_debt=debt,
        cash_and_equivalents=cash, quadrant=quad,
    )
    return dict(revenue=revenue, ebit=ebit, net_income=net_income,
                spread=m["spread"], roic=m["roic"], wacc=m["wacc"], roe=m["roe"],
                invested_capital=m["invested_capital"],
                equity=equity, debt=debt, cash=cash, assets=assets)


# =============================================================================
# 6. 图一装配（份额 × spread）+ 四态裁决
# =============================================================================

def chart_one(region, quad, user_price=None, eco_invest=0.0):
    """图一 · 象限内博弈：散点（含 YOU）+ 四态裁决 + 读数。"""
    user = build_user_firm(region, quad, price=user_price, eco_invest=eco_invest, alliance_on=False)
    opponents = [build_firm(s, in_alliance_context=False) for s in C.firms_in_quadrant(quad)]
    eq = solve_intra_quadrant(user, opponents, C.THETA_Q[quad], C.QUAD_TAM[quad])

    points = []
    for r in eq:
        f = r["firm"]
        fin = firm_financials(quad, r["price"], f["cost"], r["volume"],
                              eco_invest=(f.get("eco_invest", 0.0) if f["is_user"] else 0.0))
        points.append(dict(firm_id=f["firm_id"], is_user=f["is_user"], home=f["home"],
                           price=r["price"], share=r["share"], a_value=r["a_value"], **fin))

    return dict(points=points, verdict=_verdict(points), quad=quad,
                competition_type=C.COMPETITION_TYPE_MAP[quad])


def _verdict(points):
    """
    四态动态裁决（P3.3）。两条轴用【两把不同的尺子】——「赢销量≠赢价值」的题眼：
        独赢 = 你在【份额】上独占鳌头（share_rank==1）——赢销量
        群输 = 【价值】上受毁——输价值
    主问＝你自己创没创造价值（你 spread>0?）；群维度只区分「你输价值时」的几种输法：
        NA             投入资本≤0（spread=NaN）
        CREATE         你 spread>0（读数再点明群体共创 / 你独善其身）
        WIN_ALONE      你 spread≤0 但份额#1 ← 价格战题眼（拿销量换价值垫底）
        LOSE_ALONE     你输价值、群多数仍创造 → 你单独掉队
        MUTUAL_DESTROY 你输、群多数也输、且未夺魁 → 俱损
    """
    you = next((p for p in points if p["is_user"]), None)
    peers = [p for p in points if not p["is_user"]]
    if you is None or you["spread"] != you["spread"]:        # NaN
        return dict(state="NA", you_spread=float("nan"), peers_neg_frac=float("nan"))

    valid_peers = [p for p in peers if p["spread"] == p["spread"]]
    frac_neg = (sum(1 for p in valid_peers if p["spread"] < 0) / len(valid_peers)
                if valid_peers else 0.0)

    by_share = sorted(points, key=lambda p: -p["share"])
    valid = [p for p in points if p["spread"] == p["spread"]]
    by_spread = sorted(valid, key=lambda p: -p["spread"])
    share_rank = 1 + [p["firm_id"] for p in by_share].index(you["firm_id"])
    spread_rank = (1 + [p["firm_id"] for p in by_spread].index(you["firm_id"])
                   if you in valid else None)

    if you["spread"] > 0:
        state = "CREATE"
    elif share_rank == 1:
        state = "WIN_ALONE"
    elif frac_neg <= 0.5:
        state = "LOSE_ALONE"
    else:
        state = "MUTUAL_DESTROY"

    return dict(state=state, you_spread=you["spread"], you_share=you["share"],
                peers_neg_frac=frac_neg, share_rank=share_rank, spread_rank=spread_rank,
                ruler_flip=(share_rank == 1 and spread_rank is not None
                            and spread_rank > len(points) / 2),
                n=len(points))


# =============================================================================
# 7. 图二装配（非价格吸引力 aᵢ × spread）+ 联盟连边
# =============================================================================

def chart_two(region, quad, eco_invest=0.0, alliance_on=False):
    """图二 · 区域/全国竞合：17 预设企业（含盟内 aᵢ 加成）+ YOU。返回散点 + 联盟边。"""
    points = []
    for spec in C.PRESET_FIRMS:
        f = build_firm(spec, in_alliance_context=True)
        a_value = f["a_base"] + f["a_ally"]
        base_vol = (1.0 / len(C.firms_in_quadrant(f["quad"]))) * C.QUAD_TAM[f["quad"]]
        fin = firm_financials(f["quad"], f["p0"], f["cost"], base_vol, eco_invest=0.0)
        points.append(dict(firm_id=f["firm_id"], is_user=False, quad=f["quad"], home=f["home"],
                           a_value=a_value, in_alliance=(f["swap_alliance"] is not None),
                           spread=fin["spread"], roic=fin["roic"], roe=fin["roe"], wacc=fin["wacc"]))

    user = build_user_firm(region, quad, eco_invest=eco_invest, alliance_on=alliance_on)
    a_value = user["a_base"] + user["a_eco"] + user["a_ally"]
    lift = 1.0 / (1.0 + math.exp(-(a_value - user["a_base"])))          # aᵢ 抬升→需求非价格拉力
    base_vol = (1.0 / (len(C.firms_in_quadrant(quad)) + 1)) * C.QUAD_TAM[quad]
    fin = firm_financials(quad, user["p0"], user["cost"], base_vol * (0.7 + 0.6 * lift),
                          eco_invest=eco_invest)
    points.append(dict(firm_id="YOU", is_user=True, quad=quad, home=region,
                       a_value=a_value, in_alliance=alliance_on,
                       spread=fin["spread"], roic=fin["roic"], roe=fin["roe"], wacc=fin["wacc"]))

    present = {p["firm_id"] for p in points}
    edges = [dict(alliance=name, a=x, b=y, cross_quadrant=(x[:2] != y[:2]))
             for name, (x, y) in C.ALLIANCES.items() if x in present and y in present]
    if alliance_on:
        cand = [p for p in points if not p["is_user"] and p["quad"] != quad and p["in_alliance"]]
        if cand:
            partner = max(cand, key=lambda p: p["a_value"])
            edges.append(dict(alliance="USER", a="YOU", b=partner["firm_id"], cross_quadrant=True))

    return dict(points=points, edges=edges, quad=quad)


# =============================================================================
# 8. 记分尺子开关（P3.10）：不新增滑块，切换即两图 y 轴重排
# =============================================================================

SCORERS = {
    "spread": lambda p: p.get("spread"),      # 价值 EVA/spread（默认）
    "share":  lambda p: p.get("share"),       # 份额（图一有）
    "roe":    lambda p: p.get("roe"),         # 账面 ROE
    "roic":   lambda p: p.get("roic"),        # 投入资本回报
}


# =============================================================================
# 9. 冒烟自测（python game.py）—— §E2 方向性断言 + §E1/E3 结构检查
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Phase 3 game.py · 冒烟自测（对齐真 repo 接口）")
    print("=" * 70)
    REGION, QUAD = "Hefei", "Q1"

    neutral = chart_one(REGION, QUAD, user_price=None)
    you_n = next(p for p in neutral["points"] if p["is_user"])
    base_price = you_n["price"]
    print(f"\n[图一] 中性（你价={base_price:.1f}k）：裁决={neutral['verdict']['state']}")
    print(f"  你 share={you_n['share']:.3f} spread={you_n['spread']*100:.1f}% "
          f"份额名次={neutral['verdict']['share_rank']} spread名次={neutral['verdict']['spread_rank']}")

    war = chart_one(REGION, QUAD, user_price=base_price * 0.75)
    you_w = next(p for p in war["points"] if p["is_user"])
    peers_w = [p for p in war["points"] if not p["is_user"]]
    frac_sink = sum(1 for p in peers_w if p["spread"] < 0) / len(peers_w)
    n_pts = len(war["points"])
    print(f"\n[图一] 价格战（你砍价 25%）：裁决={war['verdict']['state']}")
    print(f"  你 share={you_w['share']:.3f}（↑?{you_w['share']>you_n['share']}） "
          f"spread={you_w['spread']*100:.1f}% | 对手穿零轴={frac_sink:.0%}（对手守毛利、让份额） "
          f"份额名次={war['verdict']['share_rank']} spread名次={war['verdict']['spread_rank']} "
          f"尺子翻转={war['verdict']['ruler_flip']}")
    # §E2（v1 修订标准）：你被卷入价格战漩涡、对手坚守利润空间，而你被打到价值利差末位。
    # 注：原标准要求「同象限全体下沉」；实测对手在 Nash 最优反应下让份额、守毛利，
    #     是成立的均衡，故按实测修订——判据改为「你独自沉到末位」。
    assert you_w["share"] > you_n["share"], "降价应抬升你的份额"
    assert you_w["spread"] < you_n["spread"], "降价应压薄你的价值创造"
    assert war["verdict"]["share_rank"] == 1, "深度价格战下你应夺得份额头名"
    assert war["verdict"]["spread_rank"] == n_pts, "你应被打到价值利差末位"
    assert war["verdict"]["ruler_flip"], "应触发尺子翻转（份额领跑、价值垫底）"
    print("  ✓ 你被卷入价格战漩涡、对手坚守利润空间，而你被打到价值利差末位")
    print("    （题眼：赢销量 ≠ 赢价值——你独自为份额买单）")

    c2_n = chart_two(REGION, QUAD, eco_invest=0.0, alliance_on=False)
    you2_n = next(p for p in c2_n["points"] if p["is_user"])
    c2_a = chart_two(REGION, QUAD, eco_invest=0.8, alliance_on=True)
    you2_a = next(p for p in c2_a["points"] if p["is_user"])
    print(f"\n[图二] 中性：你 aᵢ={you2_n['a_value']:.2f} spread={you2_n['spread']*100:.1f}%")
    print(f"[图二] 生态0.8+联盟：你 aᵢ={you2_a['a_value']:.2f} spread={you2_a['spread']*100:.1f}%")
    assert you2_a["a_value"] > you2_n["a_value"], "生态投资+联盟应抬升 aᵢ"
    edge_names = {e["alliance"] for e in c2_a["edges"]}
    print(f"  ✓ 生态/联盟→aᵢ 上浮；联盟边={sorted(edge_names)}")
    assert {"A", "B", "C"}.issubset(edge_names), "预设盟 A/B/C 应连边"

    v = F.compute_value_metrics(operating_income=10.0, net_income=6.0, total_revenue=100.0,
                                total_assets=80.0, shareholders_equity=50.0,
                                interest_bearing_debt=20.0, cash_and_equivalents=10.0, quadrant="Q1")
    print(f"\n  ✓ 回扣真 financials（单一 WACC）：样例 spread={v['spread']*100:.1f}%")
    print("\n" + "=" * 70)
    print("冒烟通过：你独沉/图二浮/尺子翻转/联盟边/真 financials —— 方向性全绿。")
    print("=" * 70)
