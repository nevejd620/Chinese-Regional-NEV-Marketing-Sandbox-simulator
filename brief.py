"""
Phase 4 · brief.py —— 总裁办简报（Action-triggered RAG）运行期全部逻辑

数据流（两条通道，只在渲染层汇合）：

  数字通道 ── 引擎读数 → 定值字符串 + 数字白名单 ─────────────┐
                                                              ├→ 出口对账 → 渲染
  检索通道 ── trigger_key → 查表取向量 → 余弦 top-k → LLM ────┘

🔴 红线：LLM 幻觉够不到财务数字。
   · 送进 prompt 的只有【定性标签】（裁决态、档位、名次），没有任何数值
   · LLM 只返回措辞与占位符 {slot}，数值由 python 在渲染层填入
   · 出口对账：扫出的每个数字必须在白名单里，且禁止口算式表达（"腰斩""翻倍"）
   · 不过关的句子丢弃并回退模板句，不是给个警告了事

运行期不装嵌入模型、不调嵌入 API —— 向量在 build_corpus.py 里离线算好随仓库走。

冒烟：python brief.py
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

import triggers as TG

ROOT = Path(__file__).resolve().parent
CHUNKS_PATH = ROOT / "corpus" / "chunks.jsonl"
VECS_PATH = ROOT / "corpus" / "vecs.npz"
CACHE_DIR = ROOT / "cache"

TOP_K = 3
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
MODEL = "glm-4-flash"


# ══════════════════════════════════════════════════════════════
# 一、数字通道：读数 → 定值字符串 + 白名单
# ══════════════════════════════════════════════════════════════
def pct(x, digits=1):
    """百分比定值渲染。全流程只认这一个形态 —— 白名单按【渲染后的字符串】建，
    否则 LLM 复述 '-5.2%' 而白名单里是 '-0.0517'，对账会全部误杀。"""
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return f"{x * 100:+.{digits}f}%"


def pctu(x, digits=0):
    """无符号百分比 —— 用于【水平量】（份额），与带符号的【变动量】区分开。
    份额是"占多少"，不是"变了多少"，写成 +38% 会误导，也会让对账误杀。"""
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return f"{x * 100:.{digits}f}%"


def num(x, digits=2):
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return f"{x:.{digits}f}"


def _band(v, cuts, names):
    """连续值 → 档位标签。送给 LLM 的是这个词，不是数值。"""
    for c, n in zip(cuts, names):
        if v <= c:
            return n
    return names[-1]


@dataclass
class Readout:
    """引擎读数包。全部字段由 app.py 从已算好的结果填入，brief.py 不做任何计算。"""
    city: str = ""
    city_cn: str = ""
    quad: str = ""
    quad_cn: str = ""
    # 旋钮
    price_pct: float = 0.0
    eco: float = 0.0
    ally: bool = False
    shock_pct: float = 0.0
    ruler_cn: str = ""
    # 图 A · 你自己
    roe_base: float | None = None
    roe_end: float | None = None
    spread_end: float | None = None
    beta_used: float | None = None
    gamma_used: float | None = None
    net_margin: float | None = None
    asset_turnover: float | None = None
    equity_multiplier: float | None = None
    # 图 B/C · 博弈
    verdict_state: str = "CREATE"
    verdict_sentence: str = ""
    share: float | None = None
    share_rank: str = "—"
    spread_rank: str = "—"
    spread_game: float | None = None
    a_value: float | None = None
    in_alliance: bool = False
    competition_cn: str = ""

    # ── 定性标签：唯一允许进入 prompt 的"程度"表达 ──────────────
    def labels(self) -> dict:
        return {
            "城市": self.city_cn or self.city,
            "象限": self.quad_cn or self.quad,
            "裁决态": self.verdict_state,
            "定价动作": _band(self.price_pct, [-20, -8, -1, 1, 8],
                              ["大幅下调", "明显下调", "小幅下调", "维持不变",
                               "小幅上调", "明显上调"]),
            "生态投资": _band(self.eco, [0.001, 0.3, 0.7],
                              ["未投入", "少量投入", "中等投入", "大力投入"]),
            "换电联盟": "已加入" if self.ally else "未加入",
            "原材料冲击": _band(self.shock_pct, [-1, 1, 20],
                                ["价格下行", "基本平稳", "温和上涨", "大幅上涨"]),
            "账面回报": ("为正" if (self.roe_end or 0) > 0 else "为负"),
            "价值利差": ("为正" if (self.spread_end or 0) > 0 else "为负"),
            "份额名次": str(self.share_rank),
            "价值名次": str(self.spread_rank),
            "记分尺子": self.ruler_cn,
            "竞争类型": self.competition_cn,
        }

    # ── 定值字符串：渲染层填模板用，【不】进 prompt ──────────────
    def values(self) -> dict:
        return {
            "city": self.city_cn or self.city,
            "quad": self.quad_cn or self.quad,
            "price_pct": f"{self.price_pct:+.0f}%",
            "eco": num(self.eco),
            "ally": "已加入" if self.ally else "未加入",
            "shock_pct": f"{self.shock_pct:+.0f}%",
            "ruler": self.ruler_cn,
            "roe_base": pct(self.roe_base),
            "roe_end": pct(self.roe_end),
            "spread_end": pct(self.spread_end),
            "beta_used": num(self.beta_used),
            "gamma_used": num(self.gamma_used),
            "net_margin": pct(self.net_margin),
            "asset_turnover": num(self.asset_turnover),
            "equity_multiplier": num(self.equity_multiplier),
            "share": pctu(self.share),
            "share_rank": str(self.share_rank),
            "spread_rank": str(self.spread_rank),
            "spread_game": pct(self.spread_game),
            "a_value": num(self.a_value),
            "alliance": "在盟" if self.in_alliance else "未在盟",
            "competition": self.competition_cn,
        }

    def whitelist(self) -> set:
        """允许出现在简报里的数字（按渲染后的形态）。"""
        out = set()
        for v in self.values().values():
            for n in _NUM_RE.findall(str(v)):
                out.add(n)
                out.add(n.lstrip("+"))        # "+5.1%" 亦允许写作 "5.1%"
        return out

    def trigger_key(self) -> str:
        return TG.trigger_key(self.quad, self.verdict_state)


# ══════════════════════════════════════════════════════════════
# 二、检索通道：查表 → 点积 → top-k（无嵌入模型、无 API）
# ══════════════════════════════════════════════════════════════
_STORE = {}


def _load():
    if _STORE:
        return _STORE
    if not (CHUNKS_PATH.exists() and VECS_PATH.exists()):
        _STORE.update(ok=False)
        return _STORE
    chunks = [json.loads(l) for l in CHUNKS_PATH.open(encoding="utf-8") if l.strip()]
    Z = np.load(VECS_PATH, allow_pickle=False)
    _STORE.update(
        ok=True, chunks=chunks,
        cvecs=Z["corpus_vecs"],
        qpos={k: i for i, k in enumerate(Z["query_keys"].tolist())},
        qvecs=Z["query_vecs"],
        rows_by_view={v: [i for i, c in enumerate(chunks) if c["view"] == v]
                      for v in TG.VIEWS},
    )
    return _STORE


def retrieve(city: str, quad: str, state: str, k: int = TOP_K) -> dict:
    """两个视角各检索一次，按 view 分池 → 两边取回的材料天然不重复。

    检索判据与 build_corpus.diagnose 完全一致（结构化元数据优先、语义补位）：
      policy   : 先锚定 1 条该城专属材料，再由相似度从「该城 + 全国性」池补足
      strategy : 先锚定「你的裁决态」「你的象限」两条，再由相似度补第三条
    纯相似度会让泛化性强的切片成为枢纽，把专属材料挤掉（v1 实测 17/20 格被同一条占据）。
    """
    S = _load()
    if not S.get("ok"):
        return {v: [] for v in TG.VIEWS}
    C, V = S["chunks"], S["cvecs"]

    def _sim_order(rows, qvec):
        sims = {i: float(V[i] @ qvec) for i in rows}
        return sorted(rows, key=lambda i: -sims[i])

    def _fill(out, ordered):
        for i in ordered:
            if len(out) >= k:
                break
            if i not in out:
                out.append(i)
        return out[:k]

    out = {}

    pos = S["qpos"].get(f"policy::{TG.policy_key(city, state)}")
    if pos is None:
        out["policy"] = []
    else:
        qv = S["qvecs"][pos]
        rows = [i for i, c in enumerate(C)
                if c["view"] == "policy" and c.get("city") in (city, None)]
        own = [i for i in rows if C[i].get("city") == city]
        picked = [_sim_order(own, qv)[0]] if own else []
        out["policy"] = [C[i] for i in _fill(picked, _sim_order(rows, qv))]

    pos = S["qpos"].get(f"strategy::{TG.strategy_key(quad, state)}")
    if pos is None:
        out["strategy"] = []
    else:
        qv = S["qvecs"][pos]
        rows = [i for i, c in enumerate(C) if c["view"] == "strategy"]
        picked = []
        for key, val in (("state", state), ("quad", quad)):
            hit = next((i for i in rows if C[i].get(key) == val), None)
            if hit is not None and hit not in picked:
                picked.append(hit)
        out["strategy"] = [C[i] for i in _fill(picked, _sim_order(rows, qv))]

    return out


# ══════════════════════════════════════════════════════════════
# 三、生成层：一次调用，只出措辞
# ══════════════════════════════════════════════════════════════
SLOTS = ("summary", "combined", "policy_view", "compete_view", "conclusion")

_SYSTEM = """你是一位面向管理层的战略分析写作助手。你的唯一任务是【组织措辞】。

绝对禁止（违反则整段作废）：
1. 不得写出任何具体数值：百分比、金额、倍数、名次数字，一律不写。
2. 不得做任何计算或比较换算，包括"腰斩""翻倍""高出三成""接近一半"这类
   没有阿拉伯数字但实质在做算术的表达。
3. 不得编造材料中没有的政策、企业或事实。

你会收到：
· 局面标签：这一局的定性描述（不含数值）
· 参考材料：政策与战略材料摘编，可引用其中的观点与做法

只输出一个 JSON 对象，不要 markdown 代码块，不要任何解释。字段：
{
  "summary":      "本轮摘要，120-160字，说清做了什么、落到什么局面、建议方向",
  "combined":     "综合分析，120-160字，把几个动作合起来看是什么局面",
  "policy_view":  "政策与区位视角，200-260字，结合参考材料",
  "compete_view": "竞争与生态视角，200-260字，结合参考材料",
  "conclusion":   "总结，150-200字，收口并给出下一步方向"
}"""


def _prompt(labels: dict, docs: dict) -> str:
    lab = "\n".join(f"· {k}：{v}" for k, v in labels.items())
    def _fmt(items):
        return "\n".join(f"[{c['title']}]\n{c['body']}" for c in items) or "（无）"
    return (f"局面标签：\n{lab}\n\n"
            f"参考材料 · 政策类：\n{_fmt(docs.get('policy', []))}\n\n"
            f"参考材料 · 战略类：\n{_fmt(docs.get('strategy', []))}")


def generate(labels: dict, docs: dict, api_key: str) -> tuple[dict, str]:
    """返回 (slots, error)。任何失败都不抛异常 —— 上层据 error 走降级路径。"""
    try:
        from openai import OpenAI
    except ImportError:
        return {}, "缺少依赖：pip install openai"
    try:
        cli = OpenAI(api_key=api_key, base_url=BASE_URL)
        r = cli.chat.completions.create(
            model=MODEL, temperature=0.6, max_tokens=2000,
            messages=[{"role": "system", "content": _SYSTEM},
                      {"role": "user", "content": _prompt(labels, docs)}])
        txt = r.choices[0].message.content.strip()
        txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
        data = json.loads(txt)
        return {k: str(data.get(k, "")).strip() for k in SLOTS}, ""
    except json.JSONDecodeError:
        return {}, "模型返回的不是合法 JSON"
    except Exception as e:                                    # noqa: BLE001
        return {}, f"{type(e).__name__}: {e}"


# ══════════════════════════════════════════════════════════════
# 四、出口对账：红线的执行机构
# ══════════════════════════════════════════════════════════════
_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?%?")
# 没有阿拉伯数字、但实质在做算术的表达。命中即判该句不合格。
_ARITH_WORDS = ("腰斩", "翻倍", "翻番", "成倍", "减半", "倍增", "折半",
                "三成", "四成", "五成", "六成", "七成", "八成", "九成",
                "过半", "近半", "一半", "三分之", "四分之", "百分之",
                "高出", "低出", "多出", "少了", "增加了", "减少了")
_SENT_SPLIT = re.compile(r"(?<=[。！？；\n])")


def reconcile(text: str, allowed: set) -> tuple[str, list]:
    """逐句审：句中每个数字必须在白名单；出现口算词即判不合格。
    不合格的句子【丢弃】，不是标注警告 —— 宁可少一句，不可脏一个数。"""
    kept, dropped = [], []
    for sent in _SENT_SPLIT.split(text):
        s = sent.strip()
        if not s:
            continue
        bad = [n for n in _NUM_RE.findall(s) if n not in allowed]
        word = next((w for w in _ARITH_WORDS if w in s), None)
        if bad:
            dropped.append((s, f"数字不在白名单：{'、'.join(bad)}"))
        elif word:
            dropped.append((s, f"口算式表达：{word}"))
        else:
            kept.append(s)
    return "".join(kept), dropped


def clean_slots(slots: dict, allowed: set, fallback: dict) -> tuple[dict, list]:
    out, drops = {}, []
    for k in SLOTS:
        txt, d = reconcile(slots.get(k, ""), allowed)
        drops += [(k, s, why) for s, why in d]
        out[k] = txt if len(txt) >= 20 else fallback.get(k, "")   # 整段被清空 → 回退
    return out, drops


# ══════════════════════════════════════════════════════════════
# 五、组装：§二 全部由模板 + 定值字符串生成（零 LLM、零风险）
# ══════════════════════════════════════════════════════════════
def action_rows(r: Readout) -> list[tuple]:
    """§二 的读数表：动作 → 本轮取值 → 对账面的影响 → 对价值/博弈的影响。
    每一格都由引擎读数决定，方向是确定的，不需要模型推断。"""
    v = r.values()
    lab = r.labels()
    return [
        ("定价", v["price_pct"],
         f"经价格弹性 β={v['beta_used']} 传导到销量；账面回报 {v['roe_end']}",
         f"价值利差 {v['spread_end']}；份额 {v['share']}、名次 {v['share_rank']}"),
        ("生态投资", v["eco"],
         f"抬升非价格吸引力至 {v['a_value']}，并作为需求侧位移驱动账面",
         f"价值名次 {v['spread_rank']}；{lab['生态投资']}"),
        ("换电联盟", v["ally"],
         "不直接改动账面成本结构",
         f"跨象限竞合中{v['alliance']}"),
        ("关键原材料价格冲击", v["shock_pct"],
         f"经成本传导 γ={v['gamma_used']} 打到单位成本，按半衰期衰减",
         "外生环境，非你的决策"),
    ]


def dupont_rows(r: Readout) -> list[tuple]:
    v = r.values()
    return [("净利率", v["net_margin"], "每一块钱收入剩下多少"),
            ("资产周转", v["asset_turnover"], "一块钱资产转出多少收入"),
            ("权益乘数", v["equity_multiplier"], "自有资金撬动了多少总资产")]


def fallback_slots(r: Readout) -> dict:
    """降级模板：无 key、调用失败、或某段被对账清空时使用。纯模板，不含推断。"""
    lab = r.labels()
    v = r.values()
    return {
        "summary": (f"本轮在{v['city']}以「{v['quad']}」定位推演："
                    f"定价{lab['定价动作']}，生态投资{lab['生态投资']}，"
                    f"换电联盟{lab['换电联盟']}，外部原材料价格{lab['原材料冲击']}。"
                    f"账面回报{lab['账面回报']}，价值利差{lab['价值利差']}，"
                    f"份额名次 {v['share_rank']}、价值名次 {v['spread_rank']}。"),
        "combined": (f"几个动作合起来看，本局落在「{lab['裁决态']}」这一态；"
                     f"当前记分尺子为{v['ruler']}，竞争类型为{v['competition']}。"),
        "policy_view": "（本段需要调用模型生成，当前使用引擎读数版简报。）",
        "compete_view": "（本段需要调用模型生成，当前使用引擎读数版简报。）",
        "conclusion": (f"综合本轮读数：账面回报{lab['账面回报']}、"
                       f"价值利差{lab['价值利差']}。"
                       f"是否继续沿当前方向加码，取决于你用哪把尺子记分。"),
    }


def build(readout: Readout, api_key: str = "") -> dict:
    """总装。返回一份 report dict —— 屏上与 docx 共用同一份，绝不二次调用模型。"""
    tk = readout.trigger_key()
    docs = retrieve(readout.city, readout.quad, readout.verdict_state)
    fb = fallback_slots(readout)

    if api_key:
        slots, err = generate(readout.labels(), docs, api_key)
    else:
        slots, err = {}, "未填写 API Key"

    if slots:
        slots, drops = clean_slots(slots, readout.whitelist(), fb)
        mode = "live"
    else:
        slots, drops, mode = fb, [], "fallback"

    cites = [{"title": c["title"], "sources": c["sources"], "view": c["view"]}
             for v in TG.VIEWS for c in docs.get(v, [])]
    return dict(trigger_key=tk, mode=mode, error=err, slots=slots,
                values=readout.values(), labels=readout.labels(),
                action_rows=action_rows(readout), dupont_rows=dupont_rows(readout),
                cites=cites, dropped=drops,
                verdict=readout.verdict_sentence, readout=asdict(readout))


# ══════════════════════════════════════════════════════════════
# 六、渲染 · 屏上（§一 + §四，约 500 字）
# ══════════════════════════════════════════════════════════════
def to_markdown(rep: dict) -> str:
    s = rep["slots"]
    parts = [f"**一、本轮摘要**\n\n{s['summary']}",
             f"**四、总结**\n\n{s['conclusion']}",
             "_完整分析（二、行动分析　三、策略分析）见导出文档。_"]
    if rep["cites"]:
        srcs = []
        for c in rep["cites"]:
            for x in c["sources"]:
                if x not in srcs:
                    srcs.append(x)
        parts.append("**引用材料**\n\n" + "\n".join(f"- {x}" for x in srcs))
    return "\n\n".join(parts)


# ══════════════════════════════════════════════════════════════
# 七、渲染 · docx（两页，宋体 + Calibri/Arial）
# ══════════════════════════════════════════════════════════════
def _font(run, size, bold=False, latin="Calibri", east="宋体"):
    from docx.shared import Pt
    from docx.oxml.ns import qn
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = latin
    # python-docx 的 font.name 只写 ascii/hAnsi，从不碰 eastAsia →
    # 中文字符会 fallback 到 Word 默认字体。必须显式设 w:eastAsia。
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east)


def _para(doc, text, size=12, bold=False, level=0, latin="Calibri"):
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
    p = doc.add_paragraph()
    pf = p.paragraph_format
    if level == 0:                                    # 正文
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        pf.first_line_indent = Pt(size * 2)           # 首行缩进 2 字符
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        pf.line_spacing = 1.35
    else:                                             # 标题
        pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
        before, after, exact = {1: (12, 6, 24), 2: (6, 4, 20), 3: (3, 2, 18)}[level]
        pf.space_before, pf.space_after = Pt(before), Pt(after)
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(exact)
    _font(p.add_run(text), size, bold, latin=latin)
    return p


def _table(doc, headers, rows, widths=None):
    from docx.shared import Pt, Cm
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    for i, h in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.text = ""
        _font(cell.paragraphs[0].add_run(h), 10.5, bold=True, latin="Arial")
    for r in rows:
        cells = t.add_row().cells
        for i, val in enumerate(r):
            cells[i].text = ""
            _font(cells[i].paragraphs[0].add_run(str(val)), 10.5, latin="Arial")
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Cm(w)
    return t


def to_docx(rep: dict, path: str | Path) -> Path:
    """两页简报。与屏上同源同字：吃的是同一份 rep，不再调用模型。"""
    from docx import Document
    from docx.shared import Pt

    v, s = rep["values"], rep["slots"]
    doc = Document()
    for sec in doc.sections:
        sec.top_margin = sec.bottom_margin = Pt(56)
        sec.left_margin = sec.right_margin = Pt(56)

    _para(doc, "总裁办简报 · 区域选址与定价博弈", 16, True, level=1, latin="Arial")
    _para(doc, f"{v['city']}　|　{v['quad']}　|　记分尺子：{v['ruler']}",
          10.5, level=3, latin="Arial")

    _para(doc, "一、本轮摘要", 16, True, level=1, latin="Arial")
    _para(doc, s["summary"])

    _para(doc, "二、本局行动分析", 16, True, level=1, latin="Arial")
    _para(doc, "2.1 逐项动作与影响", 14, True, level=2, latin="Arial")
    _table(doc, ["动作", "本轮取值", "对账面的影响", "对价值与博弈的影响"],
           rep["action_rows"], widths=[2.4, 2.0, 5.4, 5.4])
    _para(doc, "2.2 账面结构（杜邦拆解）", 14, True, level=2, latin="Arial")
    _table(doc, ["因子", "取值", "人话"], rep["dupont_rows"], widths=[2.6, 2.4, 10.2])
    _para(doc, "2.3 综合分析", 14, True, level=2, latin="Arial")
    _para(doc, s["combined"])

    _para(doc, "三、策略分析", 16, True, level=1, latin="Arial")
    _para(doc, "3.1 政策与区位视角", 14, True, level=2, latin="Arial")
    _para(doc, s["policy_view"])
    _para(doc, "3.2 竞争与生态视角", 14, True, level=2, latin="Arial")
    _para(doc, s["compete_view"])

    _para(doc, "四、总结", 16, True, level=1, latin="Arial")
    _para(doc, s["conclusion"])

    if rep["cites"]:
        _para(doc, "引用材料", 14, True, level=2, latin="Arial")
        seen = []
        for c in rep["cites"]:
            for x in c["sources"]:
                if x not in seen:
                    seen.append(x)
        for i, x in enumerate(seen, 1):
            _para(doc, f"[{i}] {x}", 9, level=3, latin="Arial")

    _para(doc, "本简报中的全部数值均由确定性引擎计算并直接填入，"
               "语言模型仅负责组织措辞、不参与任何计算。"
               "本模型为简化教学与娱乐用途，非真实预测。",
          9, level=3, latin="Arial")

    path = Path(path)
    doc.save(path)
    return path


# ══════════════════════════════════════════════════════════════
# 八、演示缓存
# ══════════════════════════════════════════════════════════════
def cache_path(trigger_key: str) -> Path:
    return CACHE_DIR / f"{trigger_key.replace('|', '_')}.json"


def load_cache(trigger_key: str) -> dict | None:
    p = cache_path(trigger_key)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                     # noqa: BLE001
            return None
    return None


def save_cache(rep: dict) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    p = cache_path(rep["trigger_key"])
    p.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


# ══════════════════════════════════════════════════════════════
# 冒烟：python brief.py
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    r = Readout(city="Xian", city_cn="西安", quad="Q4", quad_cn="极致性价比",
                price_pct=-12, eco=0.2, ally=False, shock_pct=20, ruler_cn="价值利差",
                roe_base=0.051, roe_end=-0.081, spread_end=-0.052,
                beta_used=-1.35, gamma_used=0.62,
                net_margin=-0.021, asset_turnover=0.88, equity_multiplier=2.4,
                verdict_state="WIN_ALONE", verdict_sentence="份额第一，价值垫底。",
                share=0.38, share_rank="1", spread_rank="5", spread_game=-0.052,
                a_value=1.12, in_alliance=False, competition_cn="价格主导")

    print("trigger_key:", r.trigger_key())
    print("白名单:", sorted(r.whitelist())[:12], "…")

    docs = retrieve(r.city, r.quad, r.verdict_state)
    for view in TG.VIEWS:
        got = [c["title"][:24] for c in docs[view]]
        print(f"检索 {view}: {got or '（未构建语料，跑 build_corpus.py）'}")

    # 对账自检：白名单内数字放行，白名单外与口算词丢弃
    ok, dropped = reconcile(
        "价值利差为 -5.2%，份额 38%。利差较上轮腰斩。回报率高达 -9.9%。",
        r.whitelist())
    print("\n对账保留:", ok)
    for s, why in dropped:
        print("  丢弃:", s, "→", why)

    rep = build(r, api_key="")           # 无 key → 走降级模板
    print("\n模式:", rep["mode"], "|", rep["error"])
    print("\n" + to_markdown(rep))

    try:
        out = to_docx(rep, ROOT / "brief_smoke.docx")
        print(f"\ndocx 已写出：{out}")
    except ImportError:
        print("\n（未装 python-docx，跳过 docx 冒烟：pip install python-docx）")
