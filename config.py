"""
NEV 沙盘 Phase 0 · 配置层 (对应 JSON 常数层)
所有 §B 埋入真值、可行域、象限/区域设定集中于此，供 generate_data 读取。
诚实声明：以下系数为「设定并经回归恢复验证」的真值，非真实市场实证发现。
"""
import numpy as np

# ── 时间轴 ────────────────────────────────────────────────
START_DATE = "2023-01-01"
N_DAYS = 1095                      # 三年
RNG_SEED = 42

# ── 区域 × 象限 (对应四象限映射) ──────────────────────────
REGIONS = ["Shanghai", "Shenzhen", "Hefei", "Changzhou", "Xian", "Liuzhou"]
QUADRANTS = ["Q1", "Q2", "Q3", "Q4"]

# 区域→主打象限 (要素禀赋决定它擅长哪个竞技场)
REGION_QUADRANT = {
    "Shanghai": "Q1", "Shenzhen": "Q2", "Hefei": "Q1",
    "Changzhou": "Q2", "Xian": "Q4", "Liuzhou": "Q3",
}

# ── §B1 行为系数真值 (A类，进回归，待恢复) ────────────────
BETA_DEMAND = {"Q1": -1.3, "Q2": -1.1, "Q3": -1.8, "Q4": -2.4}   # 价格弹性
GAMMA_BASE  = {"Q1": 0.55, "Q2": 0.45, "Q3": 0.40, "Q4": 0.60}   # 成本传导基线
THETA_Q     = {"Q1": 0.40, "Q2": 0.40, "Q3": 0.25, "Q4": 0.10}   # 竞争强度(占位, Phase3)

# 区域电池集群指数 → 调节 γ (高集群→低 γ)
BATTERY_CLUSTER = {
    "Shanghai": 0.55, "Shenzhen": 0.70, "Hefei": 0.85,
    "Changzhou": 0.60, "Xian": 0.30, "Liuzhou": 0.50,
}

# ── §B4 生命周期：象限成熟度基线 (横向，已编码) ───────────
MATURITY_BASE = {"Q1": 0.30, "Q2": 0.65, "Q3": 0.80, "Q4": 0.75}
DRIFT_PER_YEAR = -0.01            # 毛利/ASP 中枢逐年漂移 (价格战压薄)
# maturity 各阶段三年轨迹斜率 (成长陡升 / 成熟平稳 / 收割低平)
MATURITY_SLOPE = {"growth": 0.12, "mature": 0.02, "harvest": 0.01}

# ── §B3 象限画像中枢 (B类潜变量驱动的比率盒子, 来自 sheet 8) ─
# (低界, 高界) 硬约束；截断正态 μ 由 positioning 在界内插值
QUAD_PROFILE = {
    "Q1": dict(asp=(150_000, 250_000), margin=(0.12, 0.16), batt_share=(0.40, 0.50),
               turnover=(0.7, 0.9), rd=(0.12, 0.16), de=(0.5, 2.3), sell=(0.08, 0.15)),
    "Q2": dict(asp=(250_000, 390_000), margin=(0.17, 0.25), batt_share=(0.25, 0.35),
               turnover=(0.7, 0.9), rd=(0.08, 0.11), de=(0.1, 0.4), sell=(0.06, 0.12)),
    "Q3": dict(asp=(120_000, 150_000), margin=(0.18, 0.21), batt_share=(0.35, 0.45),
               turnover=(0.85, 1.0), rd=(0.06, 0.08), de=(0.3, 0.5), sell=(0.04, 0.09)),
    "Q4": dict(asp=(45_000, 70_000),   margin=(0.05, 0.12), batt_share=(0.40, 0.50),
               turnover=(1.2, 1.8), rd=(0.02, 0.04), de=(0.3, 0.8), sell=(0.03, 0.06)),
}

# 自研三子项象限中枢 (0-10)：电池/智驾/芯片
SELFDEV_BASE = {
    "Q1": dict(batt=3, adas=8, chip=6),
    "Q2": dict(batt=4, adas=7, chip=5),
    "Q3": dict(batt=9, adas=5, chip=6),
    "Q4": dict(batt=1, adas=1, chip=1),
}
LAMBDA_BATT = 0.35                # 自研电池压低 γ 的强度: γ_eff = γ_base*(1 - λ*batt/10)

# ── 宏观随机过程参数 (A类外生原语) ────────────────────────
MACRO = dict(
    lithium=dict(mu=100.0, phi=0.98, sigma=3.5),      # AR(1) 均值回归
    nickel=dict(mu=100.0, phi=0.97, sigma=3.0),
    rare_earth=dict(mu=100.0, phi=0.97, sigma=3.5),
    steel_al=dict(mu=100.0, phi=0.98, sigma=2.0),
    semi=dict(mu=100.0, phi=0.96, sigma=4.0),
    interest=dict(start=0.030, sigma=0.0006, lo=0.015, hi=0.040),
    carbon=dict(mu=800.0, phi=0.98, sigma=25.0),
    subsidy_start=0.06, subsidy_end=0.02,             # 全国补贴退坡
)

# 车型：每区域若干车型
MODELS_PER_REGION = 3
COMPONENT_TYPES = ["battery_pack", "e_drive", "domain_controller", "chip", "raw_material"]
TAX_RATE = 0.20
ERP = 0.055                        # 股权风险溢价 (JSON)
PB_MULTIPLE = {"Q1": 3.0, "Q2": 2.2, "Q3": 1.5, "Q4": 1.2}   # 象限估值倍数

# ── Phase 2 · WACC 补齐 (CAPM 两条腿) ─────────────────────
# 股权 β：CAPM 的 Re = rf + β·ERP。按九公司象限锚点设定（成长/波动越高→β 越高）。
EQUITY_BETA   = {"Q1": 1.6, "Q2": 1.2, "Q3": 1.0, "Q4": 1.1}
# 债务成本信用利差：Rd = rf + spread。先用统一 +2.0%（沿用默认，需要再按象限分）。
CREDIT_SPREAD = 0.020


# =============================================================================
# ══════════════════════════ Phase 3 · 博弈层扩展（只增不改）══════════════════
# =============================================================================
# 说明：以下全部为 Phase 3 新增的【博弈层规则常数】，直接追加在本文件末尾
# （沿用本 config.py 的 append-only 规矩）。上方 Phase 0–2 的量一律复用、绝不重定义：
#   β=BETA_DEMAND · θ=THETA_Q · γ 成本代理=BATTERY_CLUSTER · QUAD_PROFILE(键 asp/margin/
#   turnover/de，均为 (lo,hi) 带) · PB_MULTIPLE · EQUITY_BETA · ERP · CREDIT_SPREAD ·
#   TAX_RATE · rf=MACRO["interest"]["start"]。
# 17 家预设企业＝表外博弈玩家（类比 Tesla 锚点，绝对额不落 nev.db）。

# ── 市场禀赋新维（cluster 已在上方 BATTERY_CLUSTER；这里只补 market：本地需求体量拉力）──
MARKET_ENDOWMENT = {
    "Shanghai": 0.70, "Hefei": 0.56, "Shenzhen": 0.91, "Changzhou": 0.55,
    "Xian": 0.36, "Liuzhou": 0.45,
}

RF_START = MACRO["interest"]["start"]   # 无风险利率起点(=0.030)，供 game 读

def cluster(region):   # γ 成本传导代理（复用真 BATTERY_CLUSTER）
    return BATTERY_CLUSTER.get(region, 0.5)

def market(region):    # 市场体量拉力（P3 新维）
    return MARKET_ENDOWMENT.get(region, 0.5)

# ── 竞争类型映射（P3.11：象限→竞技场类型；规则常数、非数据）──
COMPETITION_TYPE_MAP = {
    "Q1": "price_share", "Q2": "price_share", "Q3": "ecosystem", "Q4": "comparative",
}

# 象限国内总蛋糕 TAM（相对份额×体量用；量纲不重要，只做相对）
QUAD_TAM = {"Q1": 60.0, "Q2": 50.0, "Q3": 120.0, "Q4": 90.0}

# ── Logit 份额 / 非价格吸引力 aᵢ / 生态·联盟 旋钮（数值层设定，可调不改结构）──
A_BASE   = 3.0        # 非价格吸引力共同截距（softmax 不溢出；象限内同加同减不改份额）
A_POS    = 1.2        # positioning(定位)→aᵢ 斜率
QUAD_A_TILT = {"Q1": 0.6, "Q2": 0.5, "Q3": 0.3, "Q4": -0.2}   # 象限固有非价格倾向
A_MARKET = 0.4        # 市场禀赋(market)→aᵢ 小幅拉动

ECO_GAIN = 1.2        # 生态投资→aᵢ：a_eco = ECO_GAIN·sqrt(invest)（边际递减）
ECO_OPEX = 0.06       # 生态投资折当期营收占比费用（吃当期 EBIT，换未来 aᵢ——真实权衡）
ALLY_GAIN = 0.8       # 换电联盟：入盟且盟友在场→各 +ALLY_GAIN 到 aᵢ（图二上浮）
ECO_SLIDER_MAX = 1.0  # 生态投资滑块上限（0–1）

COST_RELIEF = 0.12    # 集群减免：unit_cost ×= (1 − COST_RELIEF·(cluster−0.5))

# 合成资产负债表比率（真 QUAD_PROFILE 无 eq/cash-占资产列——这两条是 Phase 3 为“表外
# 合成企业”补的数值层设定；de/turnover/margin/asp 仍全走真 QUAD_PROFILE）
BS_EQ_ASSET   = {"Q1": 0.28, "Q2": 0.45, "Q3": 0.40, "Q4": 0.35}   # 股东权益占总资产
BS_CASH_ASSET = {"Q1": 0.25, "Q2": 0.30, "Q3": 0.20, "Q4": 0.20}   # 现金占总资产

# ── 17 预设博弈企业（§C 落位）+ 换电联盟 A/B/C + 天然不结盟锚点 ──
# home 全部取自上方 REGIONS；quad×home 自由（博弈层 city⊥quadrant）
PRESET_FIRMS = [
    dict(firm_id="Q1-1", quad="Q1", home="Shanghai",  pos=0.90, firm_swaps=0, swap_alliance=None, note="Tesla 影子·原型级天然不结盟（不换电→不入盟）"),
    dict(firm_id="Q1-2", quad="Q1", home="Hefei",     pos=0.70, firm_swaps=1, swap_alliance="A",  note="蔚来型主锚·换电先锋·盟A↔Q3-2"),
    dict(firm_id="Q1-3", quad="Q1", home="Hefei",     pos=0.55, firm_swaps=1, swap_alliance="C",  note="盟C↔Q1-5（Q1 内部）"),
    dict(firm_id="Q1-4", quad="Q1", home="Shenzhen",  pos=0.62, firm_swaps=1, swap_alliance="B",  note="盟B↔Q3-3"),
    dict(firm_id="Q1-5", quad="Q1", home="Shanghai",  pos=0.48, firm_swaps=1, swap_alliance="C",  note="盟C↔Q1-3（Q1 内部）"),
    dict(firm_id="Q2-1", quad="Q2", home="Shenzhen",  pos=0.85, firm_swaps=0, swap_alliance=None, note="Q2 全员不结盟"),
    dict(firm_id="Q2-2", quad="Q2", home="Shanghai",  pos=0.72, firm_swaps=0, swap_alliance=None, note="Q2 全员不结盟"),
    dict(firm_id="Q2-3", quad="Q2", home="Changzhou", pos=0.60, firm_swaps=0, swap_alliance=None, note="Q2 全员不结盟"),
    dict(firm_id="Q2-4", quad="Q2", home="Xian",      pos=0.50, firm_swaps=0, swap_alliance=None, note="Q2 全员不结盟"),
    dict(firm_id="Q2-5", quad="Q2", home="Shenzhen",  pos=0.40, firm_swaps=0, swap_alliance=None, note="Q2 全员不结盟"),
    dict(firm_id="Q3-1", quad="Q3", home="Hefei",     pos=0.80, firm_swaps=1, swap_alliance=None, note="比亚迪型主锚·原型级天然不结盟（垂直整合·自有补能生态）"),
    dict(firm_id="Q3-2", quad="Q3", home="Xian",      pos=0.45, firm_swaps=1, swap_alliance="A",  note="蔚来型跨象限盟友·盟A↔Q1-2"),
    dict(firm_id="Q3-3", quad="Q3", home="Shenzhen",  pos=0.58, firm_swaps=1, swap_alliance="B",  note="盟B↔Q1-4"),
    dict(firm_id="Q3-4", quad="Q3", home="Shanghai",  pos=0.50, firm_swaps=0, swap_alliance=None, note=""),
    dict(firm_id="Q4-1", quad="Q4", home="Liuzhou",   pos=0.55, firm_swaps=0, swap_alliance=None, note="Q4 全员不结盟"),
    dict(firm_id="Q4-2", quad="Q4", home="Liuzhou",   pos=0.45, firm_swaps=0, swap_alliance=None, note="比亚迪入门辅锚·宽口径天然不结盟"),
    dict(firm_id="Q4-3", quad="Q4", home="Xian",      pos=0.40, firm_swaps=0, swap_alliance=None, note="Q4 全员不结盟"),
]

ALLIANCES = {
    "A": ("Q1-2", "Q3-2"),   # 跨象限 Q1↔Q3
    "B": ("Q1-4", "Q3-3"),   # 跨象限 Q1↔Q3
    "C": ("Q1-3", "Q1-5"),   # Q1 内部
}

NATURAL_NON_ALLY = {"Q1-1", "Q3-1", "Q4-2"}   # 特斯拉、比亚迪主锚、比亚迪入门辅锚

def firms_in_quadrant(quad):
    """图一玩家：同象限（全国）预设企业。"""
    return [f for f in PRESET_FIRMS if f["quad"] == quad]

def alliance_partner(firm_id):
    """返回该 firm 的盟友 firm_id；天然不结盟企业恒 None。"""
    if firm_id in NATURAL_NON_ALLY:
        return None
    for a, b in ALLIANCES.values():
        if firm_id == a:
            return b
        if firm_id == b:
            return a
    return None
