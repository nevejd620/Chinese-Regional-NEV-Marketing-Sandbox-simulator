"""
Phase 4 · make_cache.py —— 生成演示缓存（构建期脚本，跑一次，产物进 Git）

用途：为几条典型演示路径预先生成简报，存进 `cache/*.json`。
      用户没填 API Key 时，沙盘直接读缓存 —— 断网、限流、面试现场都能演示。

🔴 为什么必须走引擎、不能填占位数字：
   缓存是给【没填 Key 的用户】看的。他在页面上拨了旋钮，上方 A/B 两段图表显示的是
   引擎真实结果，下方简报若显示另一套数字，就当场破掉了本项目最硬的一条红线
   ——"简报里每个数字都必须能在引擎输出里逐字对上"，而且破在最容易被看见的免费路径上。
   故本脚本【完整复刻 app.py 的取数链路】：simulate → financials → game，一个数字都不手填。

产物只有 json，没有 docx：docx 由 `brief.to_docx(rep, ...)` 在用户点下载时现场渲染
（纯确定性渲染，同一份 json 永远渲染出同一份文档）。预存 docx 是冗余，且改版式还得重跑。

用法：
    export ZHIPU_API_KEY=xxxx        # Colab: os.environ[...] = getpass(...)
    python make_cache.py             # 生成全部演示路径
    python make_cache.py --dry-run   # 只算引擎读数、不调 LLM（校验取数链路）
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

from calibration import cached_config
from simulate import simulate_roe
import financials
import game
import config as C
import copy_cn as T
import brief

# 与 app.py 保持一致的展示层换算（生态投资 → 需求侧位移 %）
ECO_TO_DEMAND_PCT = 15.0

CITY_CN = {"Shanghai": "上海", "Shenzhen": "深圳", "Hefei": "合肥",
           "Changzhou": "常州", "Xian": "西安", "Liuzhou": "柳州"}

# ── 演示路径：覆盖最典型的几种局面，不求穷举 ──────────────────
# 只做 3–4 条：缓存不是覆盖率问题，是【演示路径】问题。
# 多了则每次改 prompt / 语料 / 模板都要全部重跑，还会淹没提交记录。
PRESETS = [
    dict(name="价格战沉底", city="Xian", quad="Q4",
         price=-15, eco=0.0, ally=False, shock=20, ruler="spread"),
    dict(name="生态与联盟浮起", city="Hefei", quad="Q1",
         price=0, eco=0.6, ally=True, shock=0, ruler="spread"),
    dict(name="厚毛利基线", city="Shenzhen", quad="Q2",
         price=0, eco=0.2, ally=False, shock=0, ruler="spread"),
    dict(name="垂直整合抗冲击", city="Liuzhou", quad="Q3",
         price=-8, eco=0.3, ally=False, shock=40, ruler="roic"),
]


def build_readout(cfg, city, quad, price, eco, ally, shock, ruler):
    """完整复刻 app.py 的取数链路 —— 只搬运引擎结果，不做任何计算。"""
    # ── A 段：simulate → financials ──
    demand_shift = eco / C.ECO_SLIDER_MAX * ECO_TO_DEMAND_PCT if C.ECO_SLIDER_MAX else 0.0
    res = simulate_roe(city,
                       dict(price_change=price, lithium_shock=shock,
                            demand_shift=demand_shift), cfg)

    spread_end = None
    if res.get("ebit_p50") is not None:
        sl = financials.spread_line(
            np.array(res["ebit_p50"]), quadrant=quad,
            shareholders_equity=res["shareholders_equity"],
            interest_bearing_debt=res["interest_bearing_debt"],
            cash_and_equivalents=res["cash_and_equivalents"],
            tax_rate=res["tax_rate"])
        last = sl["spread"][-1]
        spread_end = None if last != last else float(last)      # NaN → None

    dupont = {}
    b = cfg["baseline"][city]
    if all(k in b for k in ("total_revenue", "total_assets")):
        dm = financials.compute_value_metrics(
            operating_income=b["ebit_base"], net_income=b["net_income"],
            total_revenue=b["total_revenue"], total_assets=b["total_assets"],
            shareholders_equity=b["equity"],
            interest_bearing_debt=b["interest_bearing_debt"],
            cash_and_equivalents=b["cash_and_equivalents"],
            quadrant=quad, tax_rate=b["tax_rate"])
        dupont = {k: dm[k] for k in
                  ("net_margin", "asset_turnover", "equity_multiplier")}

    # ── B 段：game ──
    p0 = game.build_user_firm(city, quad)["p0"]
    c1 = game.chart_one(city, quad, user_price=p0 * (1 + price / 100.0),
                        eco_invest=eco)
    c2 = game.chart_two(city, quad, eco_invest=eco, alliance_on=ally)
    v = c1["verdict"]
    you1 = next(p for p in c1["points"] if p["is_user"])
    you2 = next(p for p in c2["points"] if p["is_user"])

    return brief.Readout(
        city=city, city_cn=CITY_CN.get(city, city),
        quad=quad, quad_cn=T.QUAD_CELL[quad]["short"],
        price_pct=price, eco=eco, ally=ally, shock_pct=shock,
        ruler_cn=T.SCORER_NAMES.get(ruler, ruler),
        roe_base=res["roe_base"], roe_end=res["roe_p50"][-1], spread_end=spread_end,
        beta_used=res["beta_used"], gamma_used=res["gamma_used"], **dupont,
        verdict_state=v.get("state", "CREATE"),
        verdict_sentence=T.verdict_sentence(v),
        share=you1["share"], share_rank=v.get("share_rank", "—"),
        spread_rank=v.get("spread_rank", "—"), spread_game=you1.get("spread"),
        a_value=you2["a_value"], in_alliance=you2["in_alliance"],
        competition_cn=T.COMPETITION_CN.get(c1["competition_type"], ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="只算引擎读数、不调 LLM（校验取数链路，不花额度）")
    args = ap.parse_args()

    key = next((os.getenv(k) for k in
                ("ZHIPU_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY") if os.getenv(k)), "")
    if not (key or args.dry_run):
        sys.exit("未找到 API key，请设置 ZHIPU_API_KEY；或加 --dry-run 只校验取数。")

    cfg = cached_config()
    for p in PRESETS:
        r = build_readout(cfg, p["city"], p["quad"], p["price"], p["eco"],
                          p["ally"], p["shock"], p["ruler"])
        v = r.values()
        print(f"\n── {p['name']} · {v['city']} · {v['quad']} ──")
        print(f"   触发键 {r.trigger_key()}｜裁决 {v['verdict_cn']}")
        print(f"   股东回报 {v['roe_end']}（基准 {v['roe_base']}）"
              f"｜价值利差 {v['spread_end']}"
              f"｜份额 {v['share']} 第{v['share_rank']}｜价值第{v['spread_rank']}")
        if args.dry_run:
            continue
        rep = brief.build(r, api_key=key)
        path = brief.save_cache(rep)
        drops = len(rep.get("dropped") or [])
        print(f"   → {path.name}｜模式 {rep['mode']}"
              f"｜对账丢弃 {drops} 句{'｜' + rep['error'] if rep['error'] else ''}")

    if args.dry_run:
        print("\n--dry-run：未调用 LLM、未写缓存。核对上方读数后去掉该参数正式生成。")
    else:
        print(f"\n完成。缓存目录：{brief.CACHE_DIR}")
        print("记得把 cache/*.json 一并提交 —— 它是「断网也能演示」的底气。")


if __name__ == "__main__":
    main()
