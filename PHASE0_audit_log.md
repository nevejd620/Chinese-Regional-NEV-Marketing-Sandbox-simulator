# Phase 0 · Audit Log — 数据地基与合成数据生成

> **状态**: 设计已冻结 · 待生成 (pre-generation)
> **范围**: `generate_data.py` + `nev.db` (6 表 + 车型维度) + `ground_truth.json` + 标定骨架
> **计量**: 全表人民币 (RMB)，中国市场口径
> **配套文件**: `NEV_SQL_schema.xlsx` (sheet 0–9) · `NEV_architecture.svg`

本文件是 Phase 0 的**设计冻结记录、真实锚点溯源台账、真值登记、以及生成后验收自检清单**。目的：让整个合成数据过程可审计、可复现、可诚实声明。

---

## A. 已冻结的设计决策 (Frozen Decisions)

| # | 决策 | 依据 | 状态 |
|---|---|---|---|
| A1 | 6 张原子表 + `model_dim` 车型维度；衍生指标不入库，运行时算 | xlsx sheet 1–6 | ✅ 冻结 |
| A2 | 象限标签落库规则：sales 经 model_dim；macro 不加象限；supply_chain/financial 加 (region,quadrant) | 会话决议 | ✅ 冻结 |
| A3 | 九公司→四象限映射；特斯拉保留为 Q1 参照/博弈/RAG，**绝对额不落库** | xlsx sheet 7 | ✅ 冻结 |
| A4 | SQL 落库门槛：仅「人民币+中国口径」原子数值入库 | xlsx sheet 7 脚注 | ✅ 冻结 |
| A5 | `equity_beta`/`market_cap`/`pb_multiple` 不入 SQL，作象限级 JSON 常数/派生 | 会话决议 | ✅ 冻结 |
| A6 | 可行域 (6 比率 × 4 象限) 作为**硬约束边界** | xlsx sheet 8 | ✅ 冻结 |
| A7 | 时序：情况一 — 真实锚点只取 2025，DGP 合成三年 (1095 天) + 时间漂移旋钮 | xlsx svg Block④上方 | ✅ 冻结 |
| A8 | 分层生成：A 类因果 (进回归，纯因果+独立噪声) / B 类潜变量画像 (不进回归，截断正态+联合约束) | xlsx sheet 9 | ✅ 冻结 |
| A9 | 五菱 SGMW 无独立报表 → Q4 锚点标 `provenance=estimated` | xlsx sheet 7/8 | ✅ 冻结 |
| A10 | 生命周期：不新增独立轴，用「象限基线(横向) × maturity_offset(纵向残差)」；Q2/Q4 不补资产负债表 | xlsx sheet 9 · §B4 | ✅ 冻结 |
| A11 | 自研力度拆三子项(batt_dev/adas_dev/chip_dev, 0–10)分别接入：电池→γ、智驾芯片→aᵢ；综合评分仅展示 | xlsx sheet 1/9 · §B5 | ✅ 冻结 |
| A12 | 表三扩多商品冲击(锂/镍钴/稀土/钢铝/半导体)+ upstream_policy_index；表五加 component_type 赋采购粒度 | xlsx sheet 3/5/10 | ✅ 冻结 |
| A13 | 表四加政府维度(gov_investment/local_fiscal_capacity/tax_incentive_index) | xlsx sheet 4/10 | ✅ 冻结 |
| A14 | 「静态/半静态」措辞改为「低频/事件驱动更新」(真实 SQL 皆随时更新，合成按各自频率) | xlsx sheet 1/4 标题 | ✅ 冻结 |
| A15 | 碳价保持外生随机过程(不被积分需求反向决定，避免内生污染回归)；换电合作(swap_partnership)在博弈层触发竞合(削弱 θ、存量溢出 α) | §C · sheet 10 | ✅ 冻结 |
| A16 | 复合主键保留(声明 PRIMARY KEY 多列)维持 3NF，不过度规范化；全字段满足 1NF | sheet 10 | ✅ 冻结 |
| A17 | 输入端三分工：SQL(结构化数值)/JSON(规则系数·话语权 aᵢ 分量)/RAG(话语权定性叙事)。用户画像、车速、碳价供需联动 → 延后 v0.3 | sheet 10 · checklist | ✅ 冻结 |
| A18 | `selling_expense` 单列(B画像，营收3–15%×maturity)→ 喂 aᵢ 心智分量：与降价并列的竞争手段 | xlsx sheet 6/9 | ✅ 冻结 |
| A19 | 市场三层天花板：①份额 logit 强制≤100%(免费) ②全国 M 用逻辑斯蒂饱和 ③本地 local_market_size=可服务天花板 TAM。防「无限降价拿无限量」 | xlsx sheet 9 | ✅ 冻结 |
| A20 | Notebook 六段工作流：生成→画像(落库前,DataFrame 自检)→建表→展示(SQL 复算交叉验证)→关系→验收，各独立成 cell | §H | ✅ 冻结 |

---

## B. 埋入的真值 (Ground Truth — 待恢复)

以下为**设计设定的真值**，写入 `ground_truth.json`，供标定环节回归恢复验证。**这是"设定并验证"，非"实证发现"。**

### B1. 行为系数 (A 类，进回归)

| 系数 | 含义 | 设定值 (按象限/区域) | 恢复方程 |
|---|---|---|---|
| `beta_demand` | 价格弹性 (own-price) | Q1 −1.3 · Q2 −1.1 · Q3 −1.8 · Q4 −2.4 | `ln Q = α + β·ln P + ε₁` |
| `gamma_cost` | 成本传导刚性(按 component_type 接不同上游指数) | 高电池集群区 0.35 · 低集群区 0.78（区间 0.35–0.8）；电池→锂/镍钴、电驱→稀土、芯片→半导体、车身→钢铝 | `C = α₂ + Σγ_k·Shock_k + ε₂` |
| `logit_b` | 份额价格敏感度 | 待 Phase 3 设定 (占位) | 多项 logit |
| `theta_q` | 竞争强度 (conduct) | Q1/Q2 0.4 · Q3 0.25 · Q4 0.1（趋 0） | 加成公式 |

### B2. 宏观随机过程 (A 类外生原语)

| 过程 | 设定 |
|---|---|
| `lithium_price_index` | AR(1) 均值回归，μ=100，φ=0.98，σ_shock 校准至真实锂价年波幅 |
| `macro_interest_rate` | GBM/随机游走，起点=当期真实基准利率，年漂移小 |
| `carbon_credit_price` | 均值回归，与 lithium 弱相关 |

### B3. 潜变量画像 (B 类，不进回归)

- `positioning_score ∈ [0,1]`：象限内抽取，驱动 ASP/毛利率/周转/研发率/杠杆/电池占比。
- 各比率的 (μ, σ, 下界, 上界) = xlsx sheet 8 区间；分布 = Truncated Normal。
- 时间漂移：毛利率/ASP 中枢按年缓慢下移（模拟价格战压薄），漂移率 = 可调旋钮，记入 config。

### B4. 生命周期 · 象限(横向基线) × maturity(纵向残差)

> 象限与生命周期**部分重合但方向不同**：象限=横向(选哪种仗，空间，主动选)；生命周期=纵向(走了多远，时间)。**不新增独立生命周期轴**（与象限冗余），只拆已有信息 + 加小残差。

- **① 象限基线(横向，已编码，免费)**：`maturity` 中枢由象限给定 — Q1 低(偏成长：薄毛利/高研发/权益被亏损侵蚀) · Q2 中偏成熟 · Q3/Q4 高(规模化正毛利高周转)。
- **② 单元残差(纵向，新增小量)**：`maturity_offset` — 同象限内先后差异(如蔚来 vs 小鹏，均 Q1 但小鹏更近拐点)。此为正交残差。
- **合成式**：`maturity = 象限基线 + maturity_offset + 时间推进(三年轨迹沿此爬升)`
- **驱动**：毛利率轨迹(成长陡升/成熟平稳/收割低平) · 账面权益(成长期薄) · 研发率(成长期高)。
- **与 positioning 区分**：`positioning_score`=横截面此刻站哪(高低)；`maturity`=时间轨迹形状(陡升/平稳/低平)。
- **scope**：静态漂移旋钮升级为分阶段轨迹，v0.1 即带上，几乎不增维度复杂度。

### B5. 自研力度 · 三子项分别接入 (拆而不合成)

> 三子项作用于**不同因果链**，故必须拆开、分别接入，不合成单一评分作计算输入。

| 子项 | 存储 | 接入 | 侧 |
|---|---|---|---|
| `batt_dev` 自研电池 | model_dim, 0–10 连续 | `γ_eff = γ_base × (1 − λ_b·batt_dev/10)`，**经设定 γ 真值一次性注入**（回归照常恢复被压低后的 γ，不在回归后乘系数，避免污染） | 成本侧 (A类 γ) |
| `adas_dev` 自研智驾 | model_dim, 0–10 连续 | `a_tech = w_a·adas_dev + w_c·chip_dev` → aᵢ 智能分量 | 需求侧 (B类 aᵢ) |
| `chip_dev` 自研芯片 | model_dim, 0–10 连续 | 同上 | 需求侧 (B类 aᵢ) |
| `rd_score_display` 综合评分 | model_dim, 派生 | 加权和，**仅作展示/RAG 标签，不进计算** | — |

- **连续 > 0/1**：区分自研深浅（比亚迪刀片 9 vs 新势力半自研 3），深浅映射 γ 压低/aᵢ 抬升幅度。
- **加权 > 均值**：三项杠杆不同（电池对 γ 影响最大），均值假设等权。
- **生成来源**：三子项由 `positioning_score × 象限 × maturity` 驱动（截断正态 0–10）。象限：Q3 电池高 · Q1/Q2 智驾芯片高 · Q4 近乎不自研；maturity：成熟期评分才上得来。
- **存储决定**：`model_dim` 存三子项 + `rd_score_display`；**不存单一自研评分作为计算输入**。

---

## C. 真实锚点溯源台账 (Provenance Ledger)

**已核 (2025 财报，来源见下)**：

| 公司 | 象限 | 关键锚点值 (2025) | 来源 |
|---|---|---|---|
| 蔚来 NIO | Q1 | 车辆毛利率 14.6% · 总营收 875 亿 · 交付 32.6 万 · 净亏 149 亿 · 权益 66 亿 · 有息 D/E 2.3 · 周转 0.88 | NIO FY2025 业绩 + 资产负债表 |
| 小鹏 XPeng | Q1 | 全年毛利率 18.9% · Q4 车辆毛利率 13.0% · 研发率 ~12% | XPeng FY2025 业绩 |
| 理想 Li Auto | Q2 | 车辆毛利率 17.9% · 营收 1123 亿 · 交付 40.6 万 · 净利 11 亿 · ASP ~25 万 | Li Auto FY2025 业绩 |
| 赛力斯 Seres | Q2 | NEV 毛利率 28.8% · 营收 1650 亿 · 净利 59.6 亿 · AITO ASP 39.1 万 · 研发率 7.6% | Seres FY2025 年报 |
| 比亚迪 BYD | Q3 | 汽车毛利率 20.5% · 营收 8040 亿 · 净利率 4.1% · 研发率 7.89% · 有息 D/E 0.3–0.5 · 周转 0.89 · 权益 2621 亿/资产 9021 亿 | BYD FY2025 年报 + 资产负债表 |
| 吉利 Geely | Q2/Q3 | 净利率 ~4.9% | 引自 BYD 年报行业对比 |

**估算 (无独立报表)**：

| 公司 | 象限 | 处理 |
|---|---|---|
| 五菱 SGMW | Q4 | 从上汽权益法 + 运营数据 (163.5 万辆、产值超千亿) 反推区间；`provenance=estimated` |
| 长安 Changan | Q3 | 辅锚，NEV 口径需从合并报表剥离；权益法合资收益单列 |

**已决定不补**：Q2 有息负债/权益、Q4 全列 — 属 B 类画像变量、不进回归，精确读数无增量价值；Q4 五菱本质无独立报表。当前近似/估算足够，**不补第二轮资产负债表**。

---

## D. 运行时日志字段 (Runtime Log Schema)

`generate_data.py` 每次运行须向本 audit_log 追加一条时间戳条目，含：

- `run_timestamp` · `rng_seed` · `config_hash` (DGP 参数哈希，保可复现)
- 各表生成行数：`sales_transactions` (≈1095×区域×车型)、`macro_shocks_log` (1095)、`supply_chain_costs`、`financial_snapshots`、`regional_infra`、`model_dim`
- 日期覆盖：起止日期、天数 = 1095 校验
- 埋入真值快照 (β/γ/θ per 象限区域)
- 全部验收检查 (见 E) 的 pass/fail

---

## E. 验收自检清单 (Acceptance Checks — 生成后必须全绿)

### E1. 参数恢复 (Parameter Recovery) — 项目立身之本
- [ ] OLS 恢复 `beta_demand`：各象限估计值的 95% CI **覆盖**设定真值
- [ ] OLS 恢复 `gamma_cost`：各区域估计值 95% CI 覆盖真值
- [ ] 回归 R² 合理 (0.7–0.95)，无完美拟合 (完美=共线性泄漏)
- [ ] 自变量条件数 (condition number) 不爆 → A 类未被潜变量污染

### E2. 会计恒等式 (Accounting Identities) — 财报自洽
- [ ] `收入 = P × Q` 逐行成立 (容差 <1e-6)
- [ ] `毛利 = 收入 − 汽车成本 − 折旧`；`净利 = 毛利 − 费用 − 税息`
- [ ] `投入资本 = 有息负债 + 权益 − 现金` 可算，无负分母
- [ ] 无负销量、无负价格、无负 BOM

### E3. 可行性 (Feasibility) — 联合约束
- [ ] 无"每项在区间内、组合却不现实"的行 (如 ASP 38 万 & 毛利 6%)
- [ ] 联合约束成立：电池占比↑→毛利↓；ASP↑→毛利↑/周转↓ (相关系数符号正确)
- [ ] 所有比率落在 sheet 8 硬约束边界内

### E4. 覆盖与可分 (Coverage & Separability)
- [ ] 每象限样本**充分散布** (截断正态 σ 未过小、未塌成点)
- [ ] 四象限在 ASP/毛利率/研发率上**统计可分** (分布分离，如均值差 > 合并标准差)

### E5. 落库门槛与完整性 (Integrity)
- [ ] SQL 中**无非人民币、非中国口径**行 (特斯拉绝对额未入库)
- [ ] 外键有效 (sales.model_id → model_dim)、主键唯一、复合主键无重
- [ ] `region`/`quadrant` 索引已建

---

## F. 可复现性 (Reproducibility)
- RNG 种子固定并记录；同种子 + 同 config → 同数据
- `ground_truth.json` 与 `nev.db` 同批产出、版本对齐
- DGP 参数集哈希入库，防止"数据与真值失配"

---

## G. 运行前待确认 (Open Items Before Run)

**已解决**：
- ~~Q2/Q4 补资产负债表~~ → **不补**（画像变量，不进回归，无增量价值）
- ~~生命周期是否加独立维度~~ → **不加独立轴**，用「象限基线 × maturity 残差」(§B4)，v0.1 即带

**仍待你点头 (2 项)**：
1. B1 行为系数真值 (β/γ/θ) 采用本文件设定值 (Q1 −1.3 / Q2 −1.1 / Q3 −1.8 / Q4 −2.4；γ 0.35–0.78；θ 0.4/0.25/0.1)？还是要调？
2. 时间漂移率 (毛利/ASP 逐年压薄) 取值？(默认 −1%/年，可调)；maturity 各阶段轨迹斜率是否用默认(成长陡升/成熟平稳/收割低平)？

> 以上 2 项确认后，Phase 0 即可运行；运行后按 §E 逐项打勾，全绿方视为 Phase 0 完成，打 tag `v0.1`。

---

## H. Notebook 工作流规范 (Cell 分块)

> **核心原则**：生成 / 画像 / 建表 / 展示 / 关系 / 验收 **六段彻底分离，每段独立成 cell、独立运行、独立输出**。目的：三类错误互不遮蔽——head 报错=建表问题，SQL 复算对不上=落库问题，JOIN 出孤儿行=关系问题，定位精确。**画像在落库之前**（作用于内存 DataFrame），是「生成层自检」；生成若错，到此为止，不浪费时间建表。

### H1. 六段顺序

| 段 | Cell 类型 | 内容 | 作用 |
|---|---|---|---|
| ① Synthetic Data 生成 | 代码 | DGP 生成六张 DataFrame + `ground_truth`（内存，未入库） | 生成 |
| ② 数据画像 / 总结展示 | 代码+输出 | 对重要列做分布摘要（mean/min/max/std，分类列 value_counts），**按 quadrant 分组** | 生成层自检：生成对否、四象限可分否、落可行域否 |
| ③ SQL 生成 | 代码 | 建表 DDL + DataFrame 写入 `nev.db` | 落库 |
| ④ SQL 初步展示 | 代码+输出 | 逐表 `SELECT * LIMIT 5` (head) + `COUNT(*)`；用 SQL **复算 ② 的同一批变量** | 落库自检 + 与 ② 交叉验证（数一致=落库无损） |
| ⑤ 关系完整性检验 | 代码+输出 | 外键、复合键、维度关联三类检查 | 关系搭建自检 |
| ⑥ 结果验收 | 代码+输出 | 参数恢复（回归 β/γ vs ground_truth）+ §E 清单逐项 assert → PASS | 最终验收 |

> ②③ 次序关键：画像在**落库之前**。②（DataFrame 侧）与 ④（SQL 侧）展示**同一批变量**，一致才证明落库无损——此交叉验证的价值正因 ② 在前、④ 在后才成立。

### H2. 重要列清单（②④ 两次展示同一批，覆盖 A因果 / B画像 / 禀赋 三类）

| 表 | 重要列 |
|---|---|
| `sales_transactions` | `unit_price` (P) · `quantity` (Q) |
| `macro_shocks_log` | `lithium_price_index` · `macro_interest_rate` |
| `supply_chain_costs` | `bom_cost_per_unit` · `battery_bom_share` |
| `financial_snapshots` | `automotive_sales_revenue` · `net_income` · `rd_ratio` · `selling_expense` |
| `model_dim` | `list_price` · `batt_dev` |
| `regional_infra` | `local_market_size` · `local_battery_cluster_index` |

- **全部按 `quadrant` 分组输出**：分组 mean 表（如 Q1 ASP 均值 vs Q4）一眼验证四象限被 DGP 拉开 → 呼应 §E Separability。

### H3. 关系检查三类（⑤）

- **外键**：`sales.model_id` LEFT JOIN `model_dim` 找孤儿行，应为 0。
- **复合键**：`financial_snapshots` 的 `(region,quadrant,period)` 唯一性、无重复、无空。
- **维度关联**：`sales`/`supply_chain` 里的 `region`/`quadrant` 取值是否全部落在 `regional_infra` / 枚举集内。

---

## Z. 未来阶段设计意图 (占位 · 待完善)

> 以下为对话中提出、但**不属于 Phase 0** 的设计想法，先存档占位，做到对应阶段再落地。**不影响 Phase 0 的 SQL/JSON/代码。**

### Z1. RAG 报告两段式输出框架 (Phase 4) — 🕗 待完善

诊断报告拆两段，语义分工 = 诊断(现状) + 处方(行动)：

- **第一部分 · 分析 (What happened)**：据本次**互动**(滑块/战略选择)生成「发生了什么」。数据源 = 轨道一确定性输出(ΔROE / ΔEVA / 份额变化 / 破线时点)。
- **第二部分 · 建议措施 (What to do)**：按两组索引生成对策——
  - `Δ + stage`(是什么处境)：变化量 × 生命周期阶段，决定「承受得起什么动作」。
  - `quadrant + 竞争类型`(为什么会这样)：竞技场 × 竞争性质(生态/销量/比较优势)，决定「什么打法有效」。

**据此核对的结论（本轮已确认）**：
- **SQL schema 不改**：四个键(Δ / stage / quadrant / 竞争类型)全部已存在——Δ 运行时算、stage 来自 maturity、quadrant 已在列、竞争类型由 θ_q+象限派生。
- **JSON 可加一小块（待 Phase 4）**：`competition_type_map`(象限→生态/销量/比较优势) + `stage_from_maturity` 分档规则(如 maturity<0.5→growth)。属规则常数，非数据。
- **RAG 语料元数据加标签（待 Phase 4，非 SQL）**：`corpus_meta` 除 region/quadrant 外，增 `applicable_stage` 与 `advice_type`(分析类/对策类)，供第二部分按 stage×竞争类型硬过滤对策文献。
- **实质工作在 prompt 模板**：两段 = 两个 prompt 模板 + 两次检索，属 Phase 4 实现。

**待完善项**：竞争类型的精确定义与边界、stage 分档阈值、两段 prompt 模板、对策语料的标注规范。
