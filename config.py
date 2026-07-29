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
