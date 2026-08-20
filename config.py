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


# =============================================================================
# ═════════════ Phase 3 · v2：跨象限价格外溢（场 A · 只增不改）═════════════
# =============================================================================
# 目的：v1 里四象限是四个互不相通的玻璃缸——你在 Q1 打到骨折，Q2/Q3/Q4 纹丝不动。
#       现实中价格战会跨象限踩踏（Q3 走量降价吸走 Q4 的客；Q1 高端降价压到 Q2）。
#
# 做法（守 P3.9 当初推迟它的理由）：**单参数嵌套 Logit**，不做 4×4 全耦合交叉弹性矩阵。
#   · 象限【内】分份额：沿用原 logit_shares，θ 分场完好、一行不改；
#   · 象限【间】分总需求：按各象限的"价格指数"（inclusive value）再分一次；
#   · 邻近性**复用象限两轴定义**（价格层级 price_tier × 动力路线 powertrain），
#     不新增任何"邻近度"参数——相邻(共享一轴)替代强，对角(两轴都不同)替代弱。
# 于是全部新增参数只有下面 1 个标量 + 1 个衰减系数，复杂度可控、可解释。

SIGMA_CROSS = 0.35     # 跨象限替代强度：0=完全隔绝(回到 v1)，越大越容易跨象限被抢走
                       # 0.15≈弱(仅渗透) / 0.35≈中(踩踏可见) / 0.6+≈强(全行业同沉)
CROSS_DIAG = 0.45      # 对角象限(两根轴都不同)的替代折减；相邻象限记 1.0

# 象限在两根博弈轴上的坐标（复用 model_dim: price_tier × powertrain_focus 的定义）
QUAD_AXES = {
    "Q1": ("Premium", "BEV"),    # 高端 · 纯电
    "Q2": ("Premium", "Multi"),  # 高端 · 多路线
    "Q3": ("Mass",    "Multi"),  # 中低端 · 多路线
    "Q4": ("Mass",    "BEV"),    # 中低端 · 纯电
}


def cross_weight(q_from, q_to):
    """两象限间的替代权重：同象限=1；相邻(共享一根轴)=1；对角(两轴皆异)=CROSS_DIAG。"""
    if q_from == q_to:
        return 1.0
    a1, b1 = QUAD_AXES[q_from]
    a2, b2 = QUAD_AXES[q_to]
    shared = (a1 == a2) + (b1 == b2)
    return 1.0 if shared >= 1 else CROSS_DIAG


# ── v2 · 规模效应（产量 → 单位成本）─────────────────────────────────────────
# 【为什么要有】v1 里 spread 对规模中性（销量翻倍，ROIC 一分不变），于是跨象限外溢
#   只改蛋糕大小、打不到价值轴。补上这一环，「被抢走产量 → 单位成本上升 → 毛利变薄
#   → spread 下沉」才走得通，价格战的跨象限踩踏才真的有后果。
#
# 【"规模"指哪个规模】＝**企业自身产量**（生产规模），不是市场总量（TAM）。
#   · 生产规模是**竞争性**的：我多卖一台、对手少卖一台，我成本降、他成本升 → 能制造分化。
#   · 市场规模是**非竞争性**的：蛋糕变大则同象限所有企业成本同比例下降，相对格局不变、
#     spread 排序不动 —— 那又会退回"规模中性"，白做。故必须用生产规模。
#   （现实中两者混合，中国 NEV 的成本下行有很大一块来自行业级电池扩产；此处有意只取
#     竞争性的那一面，忽略的那一面对相对格局无影响，对本沙盘的结论无损失。）
#
# 【函数形式与参数的确切含义】
#   AC(V) = AC_ref × (V / V_ref) ^ (−b)，   b = −log2(1 − SCALE_ELASTICITY)
#   · SCALE_ELASTICITY（下方参数）**不是弹性**，而是"**产量翻倍时的单位成本降幅**"
#     （经验曲线里的 progress rate）。e=0.025 即"产量翻一倍，单位成本降 2.5%"。
#     ⚠ 参数名沿用历史称呼、暂不改名；真实含义以此注释为准。
#   · **真·单位成本弹性** b = −log2(1−e)：产量 +1% → 单位成本 −b%。e=0.025 → b≈0.0365。
#   · **总成本弹性** ε_C = d lnC / d lnQ = 1 − b（<1 即存在规模经济）。e=0.025 → ε_C≈0.963。
#   · **规模报酬** RTS = 1/ε_C。e=0.025 → RTS≈1.038，属**温和递增**、接近规模报酬不变。
#   · V_ref = 该象限中性基线下的单企业平均产量（TAM/N），故**中性时成本不变**，
#     v1 的标定不被破坏，只有偏离基线才显影。
#
# 【长期口径 · 与模型自洽】本引擎的资本随产量等比调整（assets = revenue / turnover，
#   实测产量 ×0.5/×1/×2 时资产/营收恒定），即**所有投入可变**——这正是**长期成本函数**的
#   前提。故此处的规模效应只能解释为**长期规模经济**（采购议价、产线配置与专业化分工、
#   供应链谈判地位），**不可**解释为"摊薄固定成本"（那是短期效应，前提是产能固定）。
#   又：Phase 3 是【单点均衡·比较静态】、无时间轴，故这不是沿时间累积的**学习曲线**，
#   而是**长期平均成本曲线上的移动**（给定产量 Q，最优规模下的最低成本）。两者同为幂律。
#
# 【已知局限 · 诚实声明】幂律的弹性是**恒定的**：不论已经多大，再翻倍永远降同样百分比。
#   真实 LRAC 是 **L 形**——过了最小有效规模(MES)即趋平。中国 NEV 已历多轮价格战、
#   行业早越过 MES，故常弹性形式会**系统性高估高产量端的收益**。此处不引入 MES 拐点
#   （多参数、多逻辑＝过度精细，撞宪章 §3 数值层"想标得更准→立即停"），改为**把 e 取在
#   反映『平坦段残余规模收益』的低位**来近似。取值依据是产业常识，非实测标定。
SCALE_ELASTICITY = 0.025  # 产量翻倍→单位成本降 2.5%（b≈0.037, RTS≈1.04）
                          # 0=关闭(回到 v1) / 0.025≈成熟行业平坦段 / 0.08+≈早期爬产


# ══════════════════════════════════════════════════════════════
# ═══════════ Phase 4 · 生成式简报（RAG）· 末尾追加 ═══════════
# ══════════════════════════════════════════════════════════════
# 供应商无关：国内主流平台（智谱 / 阿里云百炼 / 腾讯混元 / 百度千帆）均提供
# OpenAI 兼容接口，故只需 base_url + 两个模型名。换厂商改这三行即可，代码不动。
#
# 分工：EMBED_MODEL 只在【构建期】由 build_corpus.py 调用（作者本地跑一次，
#       产物 corpus/vecs.npz 随仓库走）；LLM_MODEL 在【运行期】由 brief.py 调用，
#       用的是**用户自带的 key**。因此用户只需 generation 权限，不需要 embedding。

LLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
LLM_MODEL    = "glm-4-flash"      # 永久免费档：演示不会因额度耗尽而中断
EMBED_MODEL  = "embedding-3"      # 仅构建期使用
LLM_SIGNUP_URL = "https://open.bigmodel.cn"

# 生成参数：温度略低于闲聊场景 —— 简报要的是稳定措辞，不是创意
LLM_TEMPERATURE = 0.6
LLM_MAX_TOKENS  = 4000      # 五段中文近千字，2000 会把 JSON 截断在半截（实测）
LLM_TIMEOUT_S   = 60

# 检索：每个视角取几条。语料仅 31 条，k=3 已能覆盖「锚定 2 条 + 补位 1 条」
RAG_TOP_K = 3

# 🔴 红线开关（不建议关闭，留此常量是为了让约束**在代码里可见、可审计**）
#   出口对账：简报里出现的每个数字必须能在引擎读数里逐字对上，
#   且禁止"腰斩/翻倍/高出三成"这类无阿拉伯数字、实质在做算术的表达。
#   不过关的句子直接丢弃并回退模板句 —— 宁可少一句，不可脏一个数。
RAG_RECONCILE_NUMBERS = True
RAG_RECONCILE_ARITH_WORDS = True
