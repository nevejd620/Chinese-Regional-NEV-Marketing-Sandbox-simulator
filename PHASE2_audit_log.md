# Phase 2 · Audit Log — 财务解剖与价值裁决（ROE + 价值 spread 双线联动）

> **状态**: ✅ 已收官 · 待打 tag `v0.3`（真库冒烟通过，push 后 Cloud 自动重部署）
> **在线**: https://chinese-regional-nev-marketing-sandbox-simulator-3lpxhv6sebdda.streamlit.app/
> **范围**: `financials.py`(新增·价值裁决层) + `copy_cn.py`(新增·人话文案层) + `config.py`(+CAPM 两条腿) + `calibration.py`(+6 baseline 字段) + `simulate.py`(+EBIT 线) + `app.py`(上下双线 + 阴影 + 动态裁决 + 接 copy_cn)
> **计量**: 全表人民币 (RMB)，中国市场口径（沿用 Phase 0–1）
> **上游依赖**: Phase 1 产出 `nev.db` + `simulation_config.json` + `config.py`
> **核心兑现**: 正面回答"这个 ROE 到底创没创造价值"——**赢销量 ≠ 赢价值**，且随滑块动态可见

本文件记录 Phase 2 的**设计冻结、被推翻的决策、参数与引擎改动、EBIT 楔子近似、验收自检、以及 open items**。目的：让"ROE 射线 → 价值 spread 射线 → 动态裁决"这条链路可审计、可复现，并让十几轮的决策演变有据可查。

---

## A. 已冻结的设计决策 (Frozen Decisions)

| # | 决策 | 依据 | 状态 |
|---|---|---|---|
| P2.1 | `financials.py` 为引擎**纯下游后处理**：吃损益/资产，出杜邦/ROIC/WACC/spread；不碰 DB、不挂 LLM | 三层架构、LLM 红线 | ✅ 冻结 |
| P2.2 | `invested_capital` **运行时自算**（= 有息负债 + 股东权益 − 现金），不读库 | schema legend：派生聚合量、单一真相源，不入库 | ✅ 冻结 |
| P2.3 | WACC 权重用**市值派生** E = 账面权益 × `pb_multiple[象限]`，非账面权益 | sheet 8：蔚来账面权益被亏损侵蚀→账面 D/E、ROE 失真 | ✅ 冻结 |
| P2.4 | `config.py` 补 CAPM 两条腿：`EQUITY_BETA{Q1 1.6/Q2 1.2/Q3 1.0/Q4 1.1}`、`CREDIT_SPREAD 0.020`；复用现有 `ERP/PB_MULTIPLE/TAX_RATE`，rf 取 `MACRO.interest.start` | CAPM 的 Rₑ/R_d 此前 config 里真的缺 | ✅ 冻结 |
| P2.5 | **WACC 只有一处实现**（`financials._wacc`），静态裁决 `compute_value_metrics` 与动态轨迹 `spread_line` 共用 | 不造第二个轮子 | ✅ 冻结 |
| P2.6 | **动态 spread（路 B）**：spread 随滑块逐日重算，与 ROE 射线同步响应 | 兑现"价格战赢销量却毁价值"的题眼 | ✅ 冻结（**推翻**早前决策⑧，见 §B） |
| P2.7 | EBIT 逐日线用**冻结楔子**：`wedge = ebit_base − net_base`（基线利息+税），区间内不变；`ebit_rr = profit·365 + wedge`；t0 精确 ≡ `ebit_base` | 引擎 `fixed_cost` 打包了利息+税，切不出 EBIT，用基线锚点+楔子平移 | ✅ 冻结（近似见 §D） |
| P2.8 | 可视化 = **上下双线分区**（上 ROE 射线 / 下价值 spread 射线），共享 0–180 天时间轴，各有独立 y 轴与零线 | 单企业、两自我信号、共享时间轴才能"同一天对照" | ✅ 冻结 |
| P2.9 | "对比上次拨动"**阴影 = 定性/方向性**表述，不标面积数值 | ROE 是率，率×天积分无干净商业含义；定量交给终点差 | ✅ 冻结 |
| P2.10 | 裁决四态：`CREATE(spread>0)` → `①(spread<0 且 ROE>0，账面赚却毁价值)` → `③(spread<0 且 ROE≤0，账面也亏)` → `NA(投入资本≤0)` | ROE 正负 = 账面赚不赚，区分①③的"反差" | ✅ 冻结 |
| P2.11 | `copy_cn.py` **人话文案层**：两层（主标签常驻 + tooltip 悬浮术语）；纯显示、改它不触发重跑 | 宪章 §6 术语预算；文案与逻辑解耦 | ✅ 冻结 |
| P2.12 | 分析单元 = **区域×象限的"代表性企业"**（企业层，非"市场"）；九公司仅作象限锚点，不逐家入图 | 财务指标只能描述企业主体；可迁移基座 | ✅ 冻结 |
| P2.13 | **时间轴主线**：生产前选址（Phase 0–1）→ 生产后独自结算（Phase 2）→ 生产后互搏（Phase 3）；**区域内不博弈**（选址先于博弈 + 区域禀赋近似垄断）→ 竞争只在全国·同象限 | 已写入 `NEV_architecture.svg` BLOCK E | ✅ 冻结 |
| P2.14 | §C4 式容错扩展：某 cell 投入资本 ≤ 0 → ROIC/spread 标 NaN，图自动跳过，不崩 | 承接 Phase 1 缺系数容错思路 | ✅ 冻结 |
| P2.15 | 治理：**税 bug 不修**（降级 open item）；Phase 2 不回头动 DGP、不重跑 Phase 0 | 宪章 §8 变更闸门 + §3 数值层：不塌、不脏 spread、方向偏保守 | ✅ 冻结 |

---

## B. 决策演变台账（被推翻/撤销的，务必留档）

十几轮迭代中若干决策经历了"做→撤"或"改→回退"，记录如下，避免下次重走：

| 议题 | 演变 | 最终 | 原因 |
|---|---|---|---|
| **决策⑧ 冲击是否驱动 spread** | 先定动态 → 嫌 EBIT 楔子麻烦砍成静态 → **重新推翻回动态（路 B）** | 动态 | 静态下 spread 与 ROE 无活关系、前沿散点沦为死区；动态才是题眼 |
| **前沿散点图** | Phase 2 建了 ROIC−WACC 散点 → **整体移除** | 移到 Phase 3 | 相对排名=博弈概念；单企业绝对分析不该有第二主体（会计原则 + 阶段边界） |
| **价值前沿横轴口径** | 营收增速(CAGR) → 真库冒烟发现 CAGR≈0 挤成竖线 → 改营收规模 level → **随散点一并作废** | 无（散点已删） | DGP 无增长轨迹；且散点整体退场 |
| **裁决取期口径** | 末期 → 全期均值 | 全期均值（曾用于散点，现主用于基线杜邦解剖） | 末期被 drift 压到最惨、不代表稳态 |
| **税 bug** | 拟修并重跑 → **降级 open item、不重跑** | 不修 | 引入宪章后判定属数值层、不脏 spread、偏保守 |
| **Q2 rd/sell 参数** | 考虑下调让 Q2 转正 → **不动（方案 A）** | 不动 | 理想净利率≈1%、赛力斯扣非 −7.84% 证明"高毛利+费用失控+微利/转负"是真实 |

---

## C. 参数与引擎改动 (Changes)

### C1. `config.py`（+CAPM 两条腿，仅追加，不动已有常数）
```python
EQUITY_BETA   = {"Q1": 1.6, "Q2": 1.2, "Q3": 1.0, "Q4": 1.1}   # 九公司象限锚点
CREDIT_SPREAD = 0.020                                          # Rd = rf + 信用利差（统一）
```
追加式，Phase 0/1 读的常数一字未动 → **不触发重跑**（常数层向后兼容）。

### C2. `calibration.py`（`_baseline_pack` +6 字段）
每区域最新一期 `financial_snapshots` 整行已在手（算 `roe_base` 时就读），追加写入 baseline：
`ebit_base`(=operating_income)、`interest_bearing_debt`、`cash_and_equivalents`、`tax_rate`、`total_revenue`、`total_assets`。
β/γ 恢复逻辑**未改**。另：两处 `groupby().apply()` 加 `include_groups=False` 消 DeprecationWarning（需 pandas ≥ 2.2）。

### C3. `simulate.py`（+EBIT 年化 run-rate 线）
在净利级 `profit` 之上，用冻结楔子还原 EBIT：`ebit_rr = profit·365 + wedge`，输出 `ebit_p05/50/95` + 透传资产负债项（供 app 调 `financials.spread_line`）。缺 `ebit_base`（老 config）时 `ebit_*` 返回 None，引擎照跑（容错）。

### C4. `financials.py`（抽共享内核 + 动态函数）
抽出 `_invested_capital / _roic / _wacc` 内核；`compute_value_metrics`（静态全指标）与 **新增 `spread_line`**（吃逐日 EBIT 数组 → 出逐日 roic/wacc/spread）共用同一 `_wacc`。§C4 容错：IC≤0 → ROIC NaN。

### C5. `app.py`（上下双线 + 阴影 + 动态裁决 + 接 copy_cn）
标题改"新能源汽车区域选址及定价沙盘"；静态散点段**换成**上区 ROE 射线 + 下区 spread 射线（共享时间轴）；`st.session_state` 存上次中位线做"对比上次"阴影；裁决按 §A P2.10 四态选句；全部可见文案改从 `copy_cn` 读。ROE 射线、参数恢复表原样保留（只增不删）。

### C6. `copy_cn.py`（新增·人话文案层）
`METRIC_CN` 指标翻译（主标签 + tooltip 两层）+ 结论/轴/note/阴影/裁决四句/杜邦公式/段标题。纯字符串，谁都不依赖，改它秒级热重载、不触发任何重跑。

---

## D. EBIT 楔子近似 (Known Approximation)

`wedge = 利息 + 税`，**冻在基线水平、区间内不变** → EBIT 与净利随滑块平行移动。
- **利息**：近似固定（取决于有息负债，不随当期经营波动）→ 冻结合理。
- **税**：严格应随利润缩放（亏损时税→0）。但 `financials` 的 `NOPAT = EBIT·(1−tax)` 在 ROIC 侧**干净地重扣一次税**，税只在一处生效、不重复。冻结的代价：区间内"税随利润缩放"被近似掉。
- **与税 bug 的关系**：楔子取的是**基线**税，动态部分不碰 `generate_data.py` 里那个"亏损也打八折"的税 bug → 税 bug 连 spread 的动态都不脏。
- 对教学沙盘（宪章 §3 数值层）此近似可接受，t0 恒等不破（EBIT@t0 ≡ ebit_base）。

---

## E. 验收自检清单 (Acceptance Checks)

### E1. 算层（离线合成数据验证）
- [x] 杜邦恒等式：`净利率 × 周转 × 权益乘数 ≡ ROE ≡ 净利/权益`（重构后仍精确，误差 <1e-12）
- [x] WACC 单一实现：`spread_line` 与 `compute_value_metrics` 的 WACC/spread 完全一致
- [x] §C4 容错：投入资本 ≤ 0 → ROIC/spread = NaN，不崩、杜邦/ROE 不受影响

### E2. 引擎恒等与动态
- [x] t0 EBIT 年化 ≡ `ebit_base`（容差极小）
- [x] spread 随滑块动：拨价格战 → ROE 与 spread 同步迁移、spread 穿零轴
- [x] 缺 `ebit_base`（老 config）→ `ebit_*`=None，引擎照跑

### E3. 裁决与文案
- [x] 四态选句正确：CREATE / ①题眼 / ③毁灭 / NA，`{v}` 填对
- [x] `copy_cn` 无残留空位、三模板含 `{v}`、`VERDICT_NA` 无 `{v}`、可 `.format`
- [x] app 所有可见文案走 `copy_cn`，无残留硬编码

### E4. 真库冒烟（Colab，真 nev.db）
- [x] `calibration.py` 重跑写出含 6 个 Phase 2 字段的 config（缺失字段=无）
- [x] EBIT 线成形 True；spread 随滑块动=是（基线 +5.1% → 价格战 −22.0%，穿零轴）
- [x] `copy_cn` 导入 OK
- [~] 参数恢复 **β 4/4 全绿**；**γ 8/10**（Shanghai/Xian 两区 CI 未覆盖真值 → open item G3）

> 收官：§E1–E4 核心全绿，动态"赢销量→毁价值"在真库上成立。待 push + 打 tag `v0.3`。

---

## F. 部署与仓库清单 (Deploy & Repo Manifest)

**Phase 2 新增/改动（均根目录）**
- [ ] `financials.py`（新增）
- [ ] `copy_cn.py`（新增）
- [ ] `config.py`（改：+EQUITY_BETA/CREDIT_SPREAD）
- [ ] `calibration.py`（改：+6 baseline 字段、+include_groups=False）
- [ ] `simulate.py`（改：+EBIT 线）
- [ ] `app.py`（改：上下双线 + 阴影 + 动态裁决 + 接 copy_cn + 标题）
- [ ] `requirements.txt`（改：`pandas>=2.2` + 补 `scipy`）
- [ ] `PHASE2_audit_log.md`（本文件）
- [ ] `NEV_architecture.svg`（改：+BLOCK E 时间轴主线）

**部署动作**
- [ ] 重跑 `python calibration.py` 生成含 Phase 2 字段的 config（**不是重跑 Phase 0**，不动 nev.db）
- [ ] push → Cloud 自动重部署 → 打 tag `v0.3`
- [ ] 若 Cloud 报 `unexpected keyword 'include_groups'` → Cloud 的 pandas < 2.2，`requirements.txt` 已钉 `>=2.2`，通常重装即可

**不上传（产物/缓存）**：`simulation_config.json`（现算）· `__pycache__/` · `.ipynb_checkpoints/`

---

## G. 待确认 / 遗留 (Open Items)

1. **税 bug（数值层，搭车修）**：`generate_data.py` 里 `net=(ebit−interest)×(1−tax)` 对**亏损也打八折**（等于给亏损退 20% 税），应为 `net = ebt − max(0,ebt)×tax`。只脏 `net_income`→ROE，**不脏 spread**（ROIC 走 EBIT），方向偏保守。修它要重跑 Phase 0，故降级：留**下次任何一次 Phase 0 重跑时搭车修复**，边际成本为零。
2. **口径不统一**：ROE **基准取最新一期**（与引擎 t0 恒等挂钩，Phase 1 冻结），而 spread/杜邦解剖曾用**全期均值**。两者服务不同目的、不影响正确性，但口径不齐，记此备查。
3. **γ 8/10 覆盖**：Shanghai(估0.566 vs 真0.505)、Xian(估0.551 vs 真0.625)两区 95% CI 未覆盖真值。样本少(每区~44)+统计波动，R² 健康(0.87–0.91)、象限序数正确，属数值层。非 Phase 2 引入，留 Phase 待优化，不影响价值裁决。
4. **Q3 归因**：比亚迪利润承压是**价格战 + 成本周期 + 海外扩张 + 研发高强度 + 汇率**多因叠加，非单一价格战。其中**海外扩张因 schema 中国口径未建模** → DGP 的 Q3 下压幅度可能偏轻。
5. **Q1 内部分化未编码**：小鹏（完成技术转型/成本下降/智驾溢价/毛利改善）vs 蔚来（换电重资产/2025 净亏 149 亿）同属 Q1，当前单一 `QUAD_PROFILE` 盖住整个 Q1，`maturity_offset` 现为无方向噪声。留 Phase 3 车型级深化（届时有小鹏转型真实案例可用）。
6. **spread>0 但 ROE<0 边界**：创造价值却账面亏损（经营利润正、利息吃成净亏）罕见但存在，现归入 CREATE。不为罕见格单列第五句（宪章 §6）。
7. **Phase 1 遗留（继续挂）**：`ensure_db.py` 真实入口名、γ `gamma_base`/`lambda_batt` 分层深化、第三滑块 `demand_shift` 由 selling_expense 正式驱动。
8. **pandas 版本**：`include_groups=False` 需 pandas ≥ 2.2（已在 requirements 钉下限）。

---

## H. 环境与复现 (Reproducibility)

- 开发：Google Colab（与 Cloud 对齐）；Spyder 断点调试副驾。
- 依赖：`pandas>=2.2 numpy statsmodels plotly streamlit scipy`。
- 复现顺序：`python calibration.py`（写含 Phase 2 字段的 config）→ `streamlit run app.py`。
- 改文案：只动 `copy_cn.py`，热重载生效，**不重跑**。
- 系数与 nev.db 版本对齐：config 由当次 nev.db 现算，天然同批。
