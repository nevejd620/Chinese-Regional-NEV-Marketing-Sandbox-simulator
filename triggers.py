"""
Phase 4 · triggers.py —— 触发枚举与检索 query 模板（纯常量，无 IO、无 API、零依赖）

两个视角各有自己的触发维度（v2 修订，依据首轮构建诊断）：

  policy   视角 ← 「城市 × 裁决态」= 6 × 5 = 30 条 query
  strategy 视角 ← 「象限 × 裁决态」= 4 × 5 = 20 条 query

为什么 policy 用城市而不用象限（v1 的做法）：
  policy.md 里多数切片是【按城市】组织的，而城市在运行期是已知的。
  v1 用象限当键，导致选西安却检索到柳州的材料，且「柳州：上游资源短板」
  这条泛化性强的切片在 20 格里出现了 17 次，把城市专属材料全挤掉。

配套的锚定检索（见 build_corpus.py / brief.py）：
  strategy.md 的 9 条恰好是「5 裁决态 + 4 象限」，与 trigger 的两个维度一一对应，
  故不靠相似度去猜 —— 先按元数据【锚定】裁决态与象限两条，再用相似度补第三条。
  结构化元数据优先、语义检索补位，比纯相似度更可控、更可审计。

自检：  python triggers.py
"""

# ── 城市：区域禀赋画像（policy 视角的检索维度）─────────────────
# 键名必须与 simulation_config.json 的 baseline 键一致（英文城市名）。
CITY_TERMS = {
    "Hefei":     "合肥 整车制造 产销一体 零部件配套 产业集群",
    "Shenzhen":  "深圳 电子供应链 电池 智能网联 港口出海 土地资源",
    "Shanghai":  "上海 整车与智能网联 自动驾驶 核心零部件 高质量发展",
    "Changzhou": "常州 动力电池产业带 中游配套 补能设施 消费端",
    "Xian":      "西安 商用车与乘用车 内陆制造 零部件配套缺口",
    "Liuzhou":   "柳州 小型经济型车 低成本供应链 上游资源 产业集群",
}

# ── 象限：定位画像（strategy 视角的检索维度）───────────────────
QUAD_TERMS = {
    "Q1": "高端纯电 品牌溢价 智能驾驶 换电与补能网络 重资产投入 增长期",
    "Q2": "高端多路线 混动增程 全路线布局 高毛利 渠道与服务 成熟期",
    "Q3": "中低端多路线 垂直整合 自研电池 规模制造 成本控制 收获期",
    "Q4": "中低端纯电 极致性价比 薄毛利 走量 下沉市场 收获期",
}

# ── 裁决态：这一局的处境（两个视角共用）────────────────────────
# 键名必须与 game._verdict 返回的 state 完全一致。
STATE_TERMS = {
    "CREATE":         "差异化定价 守住毛利 价值创造 可持续盈利",
    "CREATE_TRAIL":   "打赢价格战却回报垫底 规模不等于优势 让份额守毛利",
    "WIN_ALONE":      "份额第一但毁灭价值 以价换量 增收不增利 价格战代价",
    "LOSE_ALONE":     "掉队 份额与价值双失 竞争力不足 定位失当",
    "MUTUAL_DESTROY": "行业性价格战 集体亏损 内卷 产能过剩 反内卷",
}

CITIES = list(CITY_TERMS)
QUADRANTS = list(QUAD_TERMS)
STATES = list(STATE_TERMS)
VIEWS = ("policy", "strategy")

# ── query 模板 ─────────────────────────────────────────────
# 刻意【不含任何数字】—— query 里出现数字会把财务读数带进语义空间，
# 是红线的第一道闸（沿用 Individual Assignment 2 已验证的约束）。
_Q_POLICY = "{city} 区域产业政策 地方配套 集群禀赋 落地条件 {state}"
_Q_STRATEGY = "{quad} 企业战略 竞争格局 生态与联盟 {state}"


def policy_key(city, state):
    """policy 视角的 query 键。未知城市/裁决态 → 回退，简报照出、不崩。"""
    city = city if city in CITY_TERMS else CITIES[0]
    state = state if state in STATE_TERMS else "CREATE"
    return f"{city}|{state}"


def strategy_key(quad, state):
    """strategy 视角的 query 键。"""
    quad = quad if quad in QUAD_TERMS else QUADRANTS[0]
    state = state if state in STATE_TERMS else "CREATE"
    return f"{quad}|{state}"


def trigger_key(quad, state):
    """对外的场面标识：仍以「象限|裁决态」表示这一局，用作缓存键与模板选择。
    （检索键另有 policy_key / strategy_key 两支，见上。）"""
    quad = quad if quad in QUAD_TERMS else QUADRANTS[0]
    state = state if state in STATE_TERMS else "CREATE"
    return f"{quad}|{state}"


def parse(key):
    a, b = key.split("|", 1)
    return a, b


def build_queries():
    """返回 {view: {key: query_text}}。构建期嵌入用；运行期只查表。"""
    pol = {f"{c}|{s}": _Q_POLICY.format(city=CITY_TERMS[c], state=STATE_TERMS[s])
           for c in CITIES for s in STATES}
    stg = {f"{q}|{s}": _Q_STRATEGY.format(quad=QUAD_TERMS[q], state=STATE_TERMS[s])
           for q in QUADRANTS for s in STATES}
    return {"policy": pol, "strategy": stg}


QUERIES = build_queries()


if __name__ == "__main__":
    n_p, n_s = len(QUERIES["policy"]), len(QUERIES["strategy"])
    print(f"policy   : {len(CITIES)} 城市 × {len(STATES)} 裁决态 = {n_p} 条")
    print(f"strategy : {len(QUADRANTS)} 象限 × {len(STATES)} 裁决态 = {n_s} 条")
    print(f"合计 {n_p + n_s} 条 query\n")

    print("── 示例 ──")
    print(f"[policy   Xian|WIN_ALONE]\n  {QUERIES['policy']['Xian|WIN_ALONE']}")
    print(f"[strategy Q4|WIN_ALONE]\n  {QUERIES['strategy']['Q4|WIN_ALONE']}\n")

    assert policy_key("Nowhere", "NA") == "Hefei|CREATE"
    assert strategy_key("Q9", None) == "Q1|CREATE"
    assert trigger_key("Q2", "LOSE_ALONE") == "Q2|LOSE_ALONE"
    print("容错自检通过：未知城市/象限/裁决态 → 回退，不崩。")
