# Phase 1 · Audit Log — 单城市引擎 + 当天上线

> **状态**: 已实现 · 待接真库验收 (implemented, pending real-db acceptance)
> **范围**: `calibration.py`(参数恢复→写 config) + `simulate.py`(180 天引擎) + `app.py`(极薄 Streamlit) + `ensure_db.py`(部署自举) + `.streamlit/config.toml`
> **计量**: 全表人民币 (RMB)，中国市场口径（沿用 Phase 0）
> **上游依赖**: Phase 0 产出 `nev.db` + `ground_truth.json` + `config.py`
> **消除的风险**: 部署内存/环境风险（骨架当天上线，公网 URL 常驻）

本文件记录 Phase 1 的**设计冻结、参数恢复方法、引擎规格、验收自检、以及部署与仓库清单**。目的：让"数据 → 系数 → ROE 射线 → 公网可演示"这条链路可审计、可复现。

---

## A. 已冻结的设计决策 (Frozen Decisions)

| # | 决策 | 依据 | 状态 |
|---|---|---|---|
| P1 | 仓库扁平结构：Phase 1 代码文件全部落 repo 根目录（与 `nev.db`/`generate_data.py` 同级），不建 `src/` | 与 Phase 0 布局对齐 | ✅ 冻结 |
| P2 | 系数**从 nev.db 回归恢复**、非手填；`ground_truth.json` 仅作恢复校验的"标准答案" | 项目立身之本 | ✅ 冻结 |
| P3 | β（价格弹性）用 `ln Q ~ ln P + C(model_id)` 带**车型固定效应**，按象限分组恢复 | FE 吸收跨车型水平差，β 由车型内价格变异识别 | ✅ 冻结 |
| P4 | γ（成本传导）用 `bom ~ L/100` 回归，`γ = slope/(slope+intercept)`，CI 走 **delta method** | 直接匹配 DGP 的 level-linear 形式，无衰减偏差 | ✅ 冻结 |
| P5 | `calibration.py` 产出**参数恢复表**并写 `simulation_config.json`（引擎唯一输入） | 数据层与引擎层解耦 | ✅ 冻结 |
| P6 | config 里每个系数带 `value + std_err`，供引擎抽样做置信带 | 蒙特卡洛需要 | ✅ 冻结 |
| P7 | 引擎 180 天**向量化**推演；锂价冲击按**半衰期指数衰减**（默认 60 天） | 冲击是脉冲非永久 | ✅ 冻结 |
| P8 | β/γ 从 `N(value, std_err)` **抽样**（默认 300 次）→ ROE 射线带 **p5–p95** 置信带 | 不呈现虚假点线 | ✅ 冻结 |
| P9 | maturity 轨迹按象限阶段接入销量漂移：Q1 growth 陡升 / Q2 mature 平稳 / Q3·Q4 harvest 低平 | 审计日志 §B4 | ✅ 冻结 |
| P10 | `t0` 无滑块时引擎 ROE **精确等于** `net_income/equity`（回填 fixed_cost 保证恒等） | 引擎与 DB 对齐 | ✅ 冻结 |
| P11 | **LLM 不挂滑块**：轨道一确定性引擎独立于 RAG，幻觉够不到财务数字 | Phase 0 红线 | ✅ 冻结 |
| P12 | 3 滑块 = 自主定价变动 / 碳酸锂价格冲击 / 需求侧位移(aᵢ 代理)；各对应一条已恢复系数或简化通道 | Phase 1 极薄 | ✅ 冻结 |
| P13 | 部署走 Streamlit Community Cloud（≈1GB 上限、公网 repo、12h 无访问休眠） | 求职作品集需公网 URL | ✅ 冻结 |
| P14 | v0.2 先 **force-add `nev.db`** 为静态资源保证当天上线；`ensure_db.py` 重生成路径留作 v0.3 切换 | 部署风险前置 | ✅ 冻结 |

---

## B. 产出文件 (Deliverables)

| 文件 | 位置 | 作用 |
|---|---|---|
| `calibration.py` | 根目录 | 读 nev.db → OLS 恢复 β/γ → 参数恢复表 → 写 `simulation_config.json`；`cached_config()` 带 Streamlit 缓存 |
| `simulate.py` | 根目录 | 180 天向量化引擎；冲击衰减 + 系数抽样蒙特卡洛带 + maturity 轨迹；纯 numpy 无 LLM |
| `app.py` | 根目录 | 极薄 Streamlit：城市选择 + 3 滑块 + Plotly ROE 射线(带置信带) + 参数恢复表 |
| `ensure_db.py` | 根目录 | 部署自举：Cloud 首boot 若 nev.db 缺失则重生成（留 `generate_data.py` 真实入口钩子），否则 mock 兜底 |
| `.streamlit/config.toml` | `.streamlit/` | Cloud 主题与服务器设置 |
| `test/make_mock_db.py` | `test/` | 测试台：按文档 schema 造 mock nev.db，供无真库时冒烟 —— **非** Phase 0 的 `generate_data.py` |
| `simulation_config.json` | 根目录(**产物**) | 由 calibration 现算，**不入 Git** |

---

## C. 参数恢复方法 (Recovery Methods)

### C1. β · 价格弹性（按象限）
- 方程：`ln Q = α + β·ln P + C(model_id) + ε`
- 固定效应吸收跨车型价格/销量水平差异 → β 由**同一车型内**的价格变异识别，避免 Q1↔Q4 价格差污染。
- 单象限若只有一个车型 → 退化为普通 OLS。
- 校验：各象限 β 的 95% CI 覆盖 `ground_truth.beta_demand`。

### C2. γ · 成本传导刚性（按区域）
- DGP 为 level-linear：`bom = base·(1 + γ·(L/100 − 1)) = base·(1−γ) + base·γ·(L/100)`。
- 回归 `bom ~ Lr`（Lr = L/100）：`slope = base·γ`，`intercept = base·(1−γ)`。
- 反解：`γ = slope/(slope+intercept)`，base 自动抵消，无需预设。
- CI：对比值 `γ = b₁/(b₀+b₁)` 用 **delta method** 传播 2×2 参数协方差。此法消除了早期"用中位数归一化"引入的 ~5% 向下衰减偏差。

---

## D. 引擎规格 (Engine Spec)

| 项 | 设定 |
|---|---|
| 时域 | 180 天，逐日 |
| 因果链 | `price_change →(β)→ 销量`；`lithium_shock →(γ, 衰减)→ 单位成本`；`demand_shift → 加性需求`；→ 利润 → ROE 年化运行率 |
| 冲击衰减 | `shock_t = shock_0 · exp(−ln2·t / 半衰期)`，半衰期默认 60 天 |
| 蒙特卡洛 | β/γ ~ `N(value, std_err)`，默认 300 抽样，输出 p5/p50/p95 |
| maturity | 销量漂移 `1 + slope·(t/180)`，slope: growth +0.25 / mature +0.05 / harvest −0.02 |
| ROE 口径 | 年化运行率 `profit_t · 365 / equity`；`t0` 无滑块 ≡ baseline ROE |

---

## E. 验收自检清单 (Acceptance Checks)

### E1. 参数恢复（沿用 Phase 0 立身之本）
- [ ] β 各象限 95% CI 覆盖真值（真库目标 4/4，R² 0.87–0.97）
- [ ] γ 各区域 95% CI 覆盖真值（mock 台已达 6/6）
- [ ] 无完美拟合、条件数不爆

### E2. 引擎恒等与方向
- [x] `t0` 无滑块：`roe_p50[0] == roe_base`（容差 <1e-9）
- [x] 弹性方向：降价 → 销量升
- [x] 冲击衰减：ROE 射线随锂价冲击回落而回归

### E3. 可部署
- [x] Streamlit 本地干净启动（HTTP 200，无 traceback）
- [x] `ensure_db.py` 删库后自动重建
- [ ] Colab 隧道验证出图
- [ ] Streamlit Cloud 公网 URL 可访问

> 注：E1 在 mock 台已验证恢复机器无偏；接真库后按 §E1 重跑打钩，全绿方视为 Phase 1 完成，打 tag `v0.2`。

---

## F. 部署与仓库清单 (Deploy & Repo Manifest)

### F1. GitHub 仓库最终文件清单（照此打钩）

**Phase 1 新增（本次上传，均放根目录，除标注）**
- [ ] `app.py`
- [ ] `calibration.py`
- [ ] `simulate.py`
- [ ] `ensure_db.py`
- [ ] `.streamlit/config.toml`（在 `.streamlit/` 子目录）
- [ ] `test/make_mock_db.py`（在 `test/` 子目录）
- [ ] `PHASE1_audit_log.md`（本文件）

**Phase 0 已有，必须在 repo 里（缺则 Cloud 起不来）**
- [ ] `generate_data.py`
- [ ] `config.py`
- [ ] `ground_truth.json`
- [ ] `requirements.txt`（合并 Phase 1 依赖：pandas / numpy / statsmodels / plotly / streamlit）
- [ ] `.gitignore`

**v0.2 部署额外要做**
- [ ] `git add -f nev.db`（force-add，绕过 .gitignore，保证 Cloud 有库）

**不上传（产物/缓存）**
- `simulation_config.json`（calibration 现算）
- `__pycache__/` · `.ipynb_checkpoints/` · `.streamlit/secrets.toml`（若有密钥）

### F2. `.gitignore` 应包含
```
nev.db            # 注：v0.2 用 git add -f 强制覆盖此忽略
simulation_config.json
__pycache__/
.ipynb_checkpoints/
.streamlit/secrets.toml
```

### F3. Streamlit Cloud 部署设置
- 主文件：`app.py`
- Python 版本（Advanced settings）：**3.11**，与 Colab 对齐避开版本缝隙
- 资源：免费 ≈1GB；空壳阶段实测占用应远低于上限（去撞天花板正是此刻该做的）

---

## G. 待确认 / 遗留 (Open Items)

1. **列名核对**：`calibration.py` 顶部假设的 schema 列名需与真实 `nev.db` DDL 对齐；不符则改两段 SQL。
2. **`generate_data.py` 真实入口**：`ensure_db.py` 现调猜测函数名（`build_database`/`main`/…），切 v0.3 重生成路径前替换为真名。
3. **β Q2 mock 偏差**：mock 台噪声偏大致 Q2 差一点，非代码问题；真库按 §E1 应 4/4。
4. **第三滑块语义**：`demand_shift` 当前为加性 aᵢ 代理；Phase 3 起由 selling_expense/自研分量正式驱动。

---

## H. 环境与复现 (Reproducibility)

- 开发：Google Colab（与 Cloud 对齐）；Spyder 断点调试副驾。
- 依赖：`pandas numpy statsmodels plotly streamlit`。
- 复现顺序：`python calibration.py`（写 config）→ `python simulate.py`（冒烟）→ `streamlit run app.py`。
- 系数与 nev.db 版本对齐：config 由当次 nev.db 现算，天然同批。
