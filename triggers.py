"""
Phase 4 · triggers.py —— 触发枚举与检索 query 模板（纯常量，无 IO、无 API、零依赖）

trigger_key = "{象限}|{裁决态}"，共 4 × 5 = 20 格。
两个维度都来自【引擎】：象限是用户选的战略定位，裁决态是 game._verdict 算出来的结果。

旋钮档位【不】参与 trigger —— 它只决定"讲得多重"，由 readout 的定值字符串带过去，
不影响"该讲什么道理"，故不进检索键（少一个维度 ≈ 少 3 倍语料压力）。

每格给两条 query：policy（区位/政策视角）与 strategy（竞争/生态视角），
对应简报 §三 的两个二级标题，各检索一次 top-3 → 合计 6 条不重复素材。

构建期：build_corpus.py 把这 40 条 query 一次性嵌入 → 存进 corpus/vecs.npz
运行期：brief.py 按 trigger_key 查表取向量，不调嵌入 API、不装嵌入模型。

自检：  python triggers.py
"""

# ── 象限：定位画像（写给检索用的语义关键词，不是给用户看的文案）──────
# 用户可见文案一律在 copy_cn.py；这里的词是喂给向量空间的，越贴语料用词越好。
QUAD_TERMS = {
    "Q1": "高端纯电 品牌溢价 智能驾驶 换电与补能网络 重资产投入 增长期",
    "Q2": "高端多路线 混动增程 全路线布局 高毛利 渠道与服务 成熟期",
    "Q3": "中低端多路线 垂直整合 自研电池 规模制造 成本控制 收获期",
    "Q4": "中低端纯电 极致性价比 薄毛利 走量 下沉市场 收获期",
}

# ── 裁决态：这一局的处境（决定"该讲什么道理"）─────────────────
# 键名必须与 game._verdict 返回的 state 完全一致（含 Phase 3 v2 拆出的 CREATE_TRAIL）。
STATE_TERMS = {
    "CREATE":         "差异化定价 守住毛利 价值创造 可持续盈利",
    "CREATE_TRAIL":   "打赢价格战却回报垫底 规模不等于优势 让份额守毛利",
    "WIN_ALONE":      "份额第一但毁灭价值 以价换量 增收不增利 价格战代价",
    "LOSE_ALONE":     "掉队 份额与价值双失 竞争力不足 定位失当",
    "MUTUAL_DESTROY": "行业性价格战 集体亏损 内卷 产能过剩 反内卷",
}

QUADRANTS = list(QUAD_TERMS)
STATES = list(STATE_TERMS)

# ── query 模板：两个视角 ────────────────────────────────────
# 刻意【不含任何数字】—— 检索 query 里出现数字会把财务读数带进语义空间，
# 是红线的第一道闸（沿用 Individual Assignment 2 已验证的约束）。
_Q_POLICY = "{quad} 区域产业政策 地方配套 集群禀赋 落地条件 {state}"
_Q_STRATEGY = "{quad} 企业战略 竞争格局 生态与联盟 {state}"

VIEWS = ("policy", "strategy")


def trigger_key(quad, state):
    """引擎输出 → 触发键。

    容错（承接 Phase 1 §C4 / Phase 2 P2.14 的一贯做法）：
    裁决态为 NA、None 或未知时，回退到该象限的 CREATE 格，简报照出、不崩。
    """
    if quad not in QUAD_TERMS:
        quad = QUADRANTS[0]
    if state not in STATE_TERMS:
        state = "CREATE"
    return f"{quad}|{state}"


def parse(key):
    """触发键 → (象限, 裁决态)。"""
    quad, state = key.split("|", 1)
    return quad, state


def build_queries():
    """20 格 × 2 视角 = 40 条 query。构建期嵌入用；运行期只查表。"""
    out = {}
    for q in QUADRANTS:
        for s in STATES:
            out[f"{q}|{s}"] = {
                "policy": _Q_POLICY.format(quad=QUAD_TERMS[q], state=STATE_TERMS[s]),
                "strategy": _Q_STRATEGY.format(quad=QUAD_TERMS[q], state=STATE_TERMS[s]),
            }
    return out


QUERIES = build_queries()


if __name__ == "__main__":
    print(f"{len(QUADRANTS)} 象限 × {len(STATES)} 裁决态 = {len(QUERIES)} 格")
    print(f"{len(QUERIES)} 格 × {len(VIEWS)} 视角 = {len(QUERIES) * len(VIEWS)} 条 query\n")

    for k in ("Q4|WIN_ALONE", "Q1|MUTUAL_DESTROY", "Q3|CREATE_TRAIL"):
        print(f"── {k} ──")
        for view in VIEWS:
            print(f"  [{view}]   {QUERIES[k][view]}")
        print()

    # 容错自检
    assert trigger_key("Q9", "NA") == "Q1|CREATE"
    assert parse(trigger_key("Q2", "LOSE_ALONE")) == ("Q2", "LOSE_ALONE")
    print("容错自检通过：未知象限/裁决态 → 回退 CREATE 格，不崩。")
