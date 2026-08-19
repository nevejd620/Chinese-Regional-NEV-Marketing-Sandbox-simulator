"""
Phase 4 · build_corpus.py —— 离线构建期脚本（跑一次，产物进 Git，运行期不执行）

做四件事：
  1. 切片  : corpus/*.md 按 `##` 标题切，抽 标题 / 正文 / （来源：…）/ 视角标签
  2. 嵌入  : 调 embedding API，把「语料切片」与「triggers 的 40 条 query」一次性向量化
  3. 落盘  : corpus/chunks.jsonl（正文+元数据） + corpus/vecs.npz（两组向量）
  4. 诊断  : 打印 20 格各自的检索结果，看有效分辨率够不够、两个视角重不重合

为什么在这里嵌入而不在运行期：
  · 运行期不装嵌入模型、不调嵌入 API —— Cloud 内存零压力，用户只需 generation key
  · trigger 空间有限（20 格 × 2 视角 = 40 条 query），穷举得完，就没必要现场算
  · 同一动作永远检索到同一批材料 → 可复现、可审计（宪章 §2 目标③）

用法：
    export ZHIPU_API_KEY=xxxx          # Windows: set ZHIPU_API_KEY=xxxx
    python build_corpus.py             # 构建 + 诊断
    python build_corpus.py --dry-run   # 只切片和诊断切片质量，不调 API、不花额度
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

import triggers as TG

ROOT = Path(__file__).resolve().parent
CORPUS_DIR = ROOT / "corpus"
CHUNKS_PATH = CORPUS_DIR / "chunks.jsonl"
VECS_PATH = CORPUS_DIR / "vecs.npz"

# 视角 → 语料文件。检索时按视角隔离，保证两个视角取回不重复的材料。
VIEW_FILES = {"policy": "policy.md", "strategy": "strategy.md"}

# 供应商配置：与 config.py 末尾追加的三个常量保持一致（换厂商只改这里/那里）
BASE_URL = os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
EMBED_MODEL = os.getenv("EMBED_MODEL", "embedding-3")
API_KEY_ENV = ("ZHIPU_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY")

TOP_K = 3          # 每个视角取几条
BATCH = 16         # 嵌入批大小
_SRC_RE = re.compile(r"^（来源[：:](.+)）\s*$")


# ══════════════════════════ 1. 切片 ══════════════════════════
def _split_md(text: str, view: str, fname: str) -> list[dict]:
    """按 `##` 标题切片。标题行本身进 embed_text（标题信息量高，值得参与检索）。"""
    chunks, cur = [], None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("##"):
            if cur:
                chunks.append(cur)
            cur = {"title": line.lstrip("#").strip(), "body": [], "sources": []}
            continue
        if cur is None:
            continue                                   # 首个 ## 之前的内容丢弃
        m = _SRC_RE.match(line.strip())
        if m:
            cur["sources"].append(m.group(1).strip())
        elif line.strip():
            cur["body"].append(line.strip())
    if cur:
        chunks.append(cur)

    out = []
    for i, c in enumerate(chunks):
        body = "".join(c["body"])
        if not body:
            print(f"  ⚠ 跳过空条目：{c['title']}")
            continue
        out.append({
            "id": f"{view}-{i:03d}",
            "view": view,                              # 视角隔离用
            "file": fname,
            "title": c["title"],
            "body": body,
            "sources": c["sources"],
            # 送进向量空间的文本 = 标题 + 正文
            "embed_text": f"{c['title']}。{body}",
        })
    return out


def load_chunks() -> list[dict]:
    all_chunks = []
    for view, fname in VIEW_FILES.items():
        path = CORPUS_DIR / fname
        if not path.exists():
            sys.exit(f"缺少语料文件：{path}")
        cs = _split_md(path.read_text(encoding="utf-8"), view, fname)
        print(f"  {fname}: {len(cs)} 条")
        all_chunks += cs
    return all_chunks


def audit_chunks(chunks: list[dict]) -> None:
    """切片质量自检：长度、来源、数字密度。--dry-run 时也跑，不花额度。"""
    print("\n── 切片质量 ──")
    digits = re.compile(r"\d")
    warn = 0
    for c in chunks:
        n = len(c["body"])
        d = len(digits.findall(c["body"]))
        flags = []
        if n < 60:
            flags.append("偏短")
        if n > 320:
            flags.append("偏长")
        if not c["sources"]:
            flags.append("缺来源")
        if d > 25:
            flags.append(f"数字多({d})")
        if flags:
            warn += 1
            print(f"  ⚠ {c['id']} {c['title'][:26]} → {'、'.join(flags)}")
    print(f"  {len(chunks)} 条，{warn} 条待留意"
          f"（偏长会挤占提示词；数字多会与引擎读数抢镜）")


# ══════════════════════════ 2. 嵌入 ══════════════════════════
def _client():
    key = next((os.getenv(k) for k in API_KEY_ENV if os.getenv(k)), None)
    if not key:
        sys.exit(f"未找到 API key，请设置环境变量之一：{' / '.join(API_KEY_ENV)}")
    try:
        from openai import OpenAI                        # 各家均提供 OpenAI 兼容接口
    except ImportError:
        sys.exit("请先安装：pip install openai")
    return OpenAI(api_key=key, base_url=BASE_URL)


def embed(texts: list[str], label: str) -> np.ndarray:
    """批量嵌入 + 三次重试。返回 L2 归一化后的矩阵（归一化后余弦 == 点积）。"""
    cli = _client()
    vecs = []
    for s in range(0, len(texts), BATCH):
        batch = texts[s:s + BATCH]
        for attempt in range(3):
            try:
                r = cli.embeddings.create(model=EMBED_MODEL, input=batch)
                vecs += [d.embedding for d in r.data]
                break
            except Exception as e:                       # noqa: BLE001
                if attempt == 2:
                    sys.exit(f"嵌入失败（{label} 第 {s} 批）：{e}")
                print(f"  重试 {attempt + 1}/3 …（{e}）")
                time.sleep(2 * (attempt + 1))
        print(f"  {label}: {min(s + BATCH, len(texts))}/{len(texts)}")
    M = np.asarray(vecs, dtype=np.float32)
    return M / np.clip(np.linalg.norm(M, axis=1, keepdims=True), 1e-9, None)


# ══════════════════════════ 3. 落盘 ══════════════════════════
def save(chunks: list[dict], cvecs: np.ndarray,
         qkeys: list[str], qvecs: np.ndarray) -> None:
    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps({k: v for k, v in c.items() if k != "embed_text"},
                               ensure_ascii=False) + "\n")
    np.savez_compressed(
        VECS_PATH,
        corpus_vecs=cvecs,
        corpus_ids=np.array([c["id"] for c in chunks]),
        query_keys=np.array(qkeys),                      # "Q1|CREATE::policy"
        query_vecs=qvecs,
        embed_model=np.array(EMBED_MODEL),
    )
    print(f"\n写出 {CHUNKS_PATH.name}（{len(chunks)} 条）"
          f" · {VECS_PATH.name}（{cvecs.shape} + {qvecs.shape}）")


# ══════════════════════════ 4. 诊断 ══════════════════════════
def diagnose(chunks: list[dict], cvecs: np.ndarray,
             qkeys: list[str], qvecs: np.ndarray) -> None:
    """有效分辨率诊断：20 格是否真的检索出 20 组不同材料，两个视角是否重合。"""
    idx_by_view = {v: [i for i, c in enumerate(chunks) if c["view"] == v]
                   for v in VIEW_FILES}
    qpos = {k: i for i, k in enumerate(qkeys)}
    title = {i: chunks[i]["title"] for i in range(len(chunks))}

    def topk(key, view):
        rows = idx_by_view[view]
        sims = cvecs[rows] @ qvecs[qpos[f"{key}::{view}"]]
        order = np.argsort(-sims)[:TOP_K]
        return [rows[o] for o in order]

    print("\n" + "=" * 62)
    print("检索诊断（每格 policy 3 条 + strategy 3 条）")
    print("=" * 62)

    sigs, overlaps = [], 0
    for q in TG.QUADRANTS:
        for s in TG.STATES:
            key = f"{q}|{s}"
            p, t = topk(key, "policy"), topk(key, "strategy")
            sigs.append(tuple(sorted(p + t)))
            if set(p) & set(t):
                overlaps += 1
            print(f"\n[{key}]")
            print(f"   政策 · {' ／ '.join(title[i][:20] for i in p)}")
            print(f"   战略 · {' ／ '.join(title[i][:20] for i in t)}")

    n = len(sigs)
    uniq = len(set(sigs))
    print("\n" + "=" * 62)
    print(f"有效分辨率：{n} 格 → {uniq} 组不同的检索结果")
    if uniq < n * 0.6:
        print("  ⚠ 重复偏高：多数格子拿到同一批材料。要么补语料（知道缺哪一格），")
        print("    要么把 trigger 维度合并 —— 让数据决定，别硬凑格子数。")
    else:
        print("  ✓ 分辨率健康：格子之间确实取到了不同材料。")
    print(f"视角隔离：两视角交集非空的格子 {overlaps}/{n}"
          f"（按 view 分池检索，预期为 0）")

    # 覆盖率：有没有切片从未被任何格子选中 → 那是白写的
    used = {i for sig in sigs for i in sig}
    idle = [c["title"] for i, c in enumerate(chunks) if i not in used]
    print(f"语料利用率：{len(used)}/{len(chunks)} 条被用到")
    if idle:
        print("  未被任何格子选中：")
        for t_ in idle:
            print(f"    · {t_[:40]}")


# ══════════════════════════ main ══════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="只切片与质量自检，不调 API")
    args = ap.parse_args()

    print("── 切片 ──")
    chunks = load_chunks()
    audit_chunks(chunks)

    if args.dry_run:
        print("\n--dry-run：未调用 API。检查上方切片质量后，去掉该参数正式构建。")
        return

    qkeys, qtexts = [], []
    for key, views in TG.QUERIES.items():
        for view in TG.VIEWS:
            qkeys.append(f"{key}::{view}")
            qtexts.append(views[view])

    print(f"\n── 嵌入（模型 {EMBED_MODEL}）──")
    print(f"  共 {len(chunks)} 条语料 + {len(qtexts)} 条 query")
    cvecs = embed([c["embed_text"] for c in chunks], "语料")
    qvecs = embed(qtexts, "query")

    save(chunks, cvecs, qkeys, qvecs)
    diagnose(chunks, cvecs, qkeys, qvecs)


if __name__ == "__main__":
    main()
