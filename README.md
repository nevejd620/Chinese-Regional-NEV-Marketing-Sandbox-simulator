# NEV 区域博弈沙盘 · Regional NEV Commercial Sandbox

> 博弈驱动的动态定价决策系统 —— 计量经济学微观行为模型 × 公司金融杜邦/ROIC-WACC，缝合成一个参数化数字孪生仿真系统。
> 场景：中国新能源汽车（NEV）产业的区域选址 × 象限战略博弈。

**🔗 在线演示**：https://chinese-regional-nev-marketing-sandbox-simulator-3lpxhv6sebdda.streamlit.app/
（Phase 4 已上线，**两 tab**：**象限地图** + **沙盘**（A 财务双线 · B 定价博弈双散点 · C 商业分析简报））

---

## 这是什么

一个把**选址禀赋 → 象限战略 → 定价博弈 → 财务价值裁决**串成一条因果链的决策支持沙盘。用户在**同一页**上拨动 3 个动作旋钮，看三段连续的后果：**A · 你自己**——单企业 180 天的 **ROE（赚得多不多）+ spread = ROIC − WACC（这份回报值不值）** 双线联动；**B · 你和对手**——全国定价博弈，你定价、对手用 Nash 最优反应还手，双散点给出四态裁决；**C · 商业分析**——由你刚才的动作触发的 RAG 简报，配一段有地方产业政策与车企战略材料支撑的解释，并可导出 Word。

**核心分析视角**：赢销量 ≠ 赢价值。价格战把 ROE 拨高的同时，常把 spread 拨到零轴下——**赢了销量，毁了价值**。

Phase 3 把它推进了一层：**价格可复制、生态位不可复制**，所以价格战里几乎没有价值上的赢家——即便靠规模打赢，也常是同象限里回报最差的那个（裁决 `CREATE_TRAIL`）。真正拉开 spread 的是换电联盟、垂直整合这类不可复制的结构性壁垒。

**一条时间轴主线**：生产前选址（Phase 0–1）→ 生产后独自结算（Phase 2）→ 生产后互搏（Phase 3）→ 后说·解释与简报（Phase 4，本阶段）。

> Phase 3 已推翻旧推论「区域内不博弈」：现冻结 **城市 ⊥ 象限解耦**——城市是选址候选地、非归属象限，同一城市可承载多象限企业。

## 诚实声明（务必先读）

- SQL 原子数据由 **DGP（数据生成过程）合成**，非真实市场数据。
- 行为系数 β（价格弹性）、γ（成本传导）为**「设定并经回归恢复验证」**，是**参数恢复（parameter recovery）**方法演示，非实证研究。
- 九家真实车企（蔚来/理想/比亚迪/小鹏/赛力斯等）仅作**锚点参照**校准可行域；沙盘里一个点是"某区域×象限的**代表性企业**"，非某家真公司、非"市场"。
- 沙盘引擎的数字是**确定性、可复现**的；RAG 只解释数字、绝不生产数字（LLM 幻觉够不到财务计算）。
- Phase 4 RAG 层：**LLM 只解释数字、绝不生产数字**。所有数值由引擎算好后以定值字符串填入模板，模型只做措辞组织；成文后还要过一道**出口对账**（数字白名单 + 口算词黑名单），不合格的句子直接丢弃并回退模板句。语料为地方产业政策与车企战略公开材料的摘编，向量在构建期离线算好随仓库走。
- Phase 3 博弈层：**你＝外生价格领导者**，对手对你的价做 Nash 最优反应。这是**比较静态**（「你的决策后果」），**非「先手优势」**。规模效应用常弹性幂律近似，未建 MES 拐点，会高估高产量端收益——参数取产业常识设定值，非实测标定。

## 架构一览

| 层 | 职责 | 载体 |
|---|---|---|
| SQL（数值资产层） | 带时间戳/区位·象限标签的原子流水 | `nev.db`（6 表 + 车型维度） |
| JSON（规则系数层） | β/γ/θ、CAPM 常数、象限定价带等 | `config.py`（真值） → `simulation_config.json`（回归恢复后，引擎输入） |
| 模型 | 离线标定（`calibration.py`）+ 在线推演（`simulate.py`）+ 价值后处理（`financials.py`）+ **博弈引擎（`game.py`）** | 见下 |
| RAG（解释层） | 语料切片 + 离线预嵌入 → 动作触发检索 → 生成 → 出口对账 → 简报/导出 | `triggers.py` · `build_corpus.py`（构建期） · `brief.py`（运行期） · `corpus/` |
| 文案（显示层） | 术语→人话翻译，两层交互，改它不重跑 | `copy_cn.py` |

详见 `PHASE0_audit_log.md` ~ `PHASE4_audit_log.md`、`NEV_architecture.svg`、`phase4_rag_dataflow_offline_and_runtime.svg`（RAG 双通道数据流）、ER 图。范围护栏见 `0PROJECT_CHARTER_scope.md`。

**RAG 的两条通道**（Phase 4 的核心设计，见数据流图）：数字走 `引擎 → 定值字符串 → 模板占位符`，文字走 `检索 → LLM`，二者**只在渲染层汇合**。财务数字从头到尾不进提示词——够不到，就编不出。

## 阶段路线

- **Phase 0 · 数据地基** ✅（v0.1）
- **Phase 1 · 单城市引擎 + 上线** ✅（v0.2）
- **Phase 2 · 财务解剖与价值裁决** ✅（v0.3）：杜邦 + ROIC/WACC + **ROE/spread 双线动态联动**
- **Phase 3 · 全国定价博弈与竞合** ✅（v0.4）：Logit-Bertrand + Nash 最优反应 + 四象限竞技场 + 换电联盟 + 跨象限外溢 + 规模效应 + 四态裁决 + 评判指标切换
- **Phase 4 · 合页 + Action-triggered RAG**（当前）✅（v0.5）：三 tab 合为两 tab + 动作触发检索（锚定 + 语义补位）+ 一次调用生成 + **出口对账** + Word 导出 + 仪表盘视觉
- Phase 5：收尾与叙事

## 快速开始

**本地运行沙盘**
```bash
pip install -r requirements.txt      # 需 pandas>=2.2；Phase 4 另需 openai / python-docx
python calibration.py     # 读 nev.db → 回归恢复 β/γ → 写含 Phase2 字段的 simulation_config.json + 恢复表
python game.py            # Phase 3 博弈引擎冒烟（方向性断言 + §E 自检）
python brief.py           # Phase 4 简报冒烟（检索 + 出口对账 + 降级 + docx）
streamlit run app.py      # 起沙盘：两 tab（象限地图 / 沙盘 A·B·C）
```

**重建语料向量（仅在改动 `corpus/*.md` 后需要，需 embedding key）**
```bash
python build_corpus.py --dry-run     # 只切片与质量自检，不花额度
export ZHIPU_API_KEY=xxxx            # Colab：os.environ[...] = getpass(...)
python build_corpus.py               # 切片 → 嵌入 → 写 vecs.npz → 三项检索诊断
```
> 产物 `corpus/chunks.jsonl` + `corpus/vecs.npz` **必须进 Git**：Cloud 上没有 embedding key，重算不了。
> 这与 `simulation_config.json` 相反——判据是"部署环境能否自力再生"，不是"是不是产物"。

**用自己的 Key 生成简报**：沙盘 C 段填入智谱 BigModel API Key（`open.bigmodel.cn` 注册免费获得）。留空也能看——会显示预生成的演示版。Key 只存在本次会话，不落盘、不进 Git。
换供应商只改 `config.py` 三行（`LLM_BASE_URL` / `LLM_MODEL` / `EMBED_MODEL`），国内主流平台均兼容 OpenAI 接口。

**Google Colab**
```python
!git clone https://github.com/nevejd620/Chinese-Regional-NEV-Marketing-Sandbox-simulator.git
%cd Chinese-Regional-NEV-Marketing-Sandbox-simulator
!pip install -r requirements.txt -q
!python calibration.py    # 验证参数恢复 + 生成 config（非重跑 Phase 0，不动 nev.db）
```

**改文案（不重跑）**：只需编辑 `copy_cn.py`，Streamlit 热重载即生效。

**复跑 Phase 0 数据地基**
```bash
jupyter notebook NEV_Phase0.ipynb
```

## 文件说明

| 文件 | 说明 | 进 Git |
|---|---|---|
| **Phase 0** | | |
| `generate_data.py` / `config.py` / `ground_truth.json` | DGP / 真值常数(含 CAPM) / 埋入真值台账 | ✅ |
| `NEV_Phase0.ipynb` / `PHASE0_audit_log.md` | 六段工作流 / 数据地基设计 | ✅ |
| **Phase 1** | | |
| `calibration.py` | 读 nev.db → 恢复 β/γ → 参数恢复表 → 写 config（Phase 2 起 +6 baseline 字段） | ✅ |
| `simulate.py` | 180 天引擎：ROE 射线 + 蒙特卡洛带（Phase 2 起 +EBIT 线） | ✅ |
| `app.py` | Streamlit：城市 + 3 滑块 + ROE/spread 双线 + 动态裁决 + 恢复表 | ✅ |
| `ensure_db.py` / `.streamlit/config.toml` | 部署自举 / 主题 | ✅ |
| `PHASE1_audit_log.md` | 引擎方法 / 验收 / 部署 | ✅ |
| **Phase 2** | | |
| `financials.py` | 杜邦 + ROIC + 市值加权 WACC + spread；静态/动态共用单一 WACC | ✅ |
| `copy_cn.py` | 人话文案层（纯显示，两层交互） | ✅ |
| `PHASE2_audit_log.md` / `RELEASE_v0.3.md` | 价值裁决设计 / 发布说明 | ✅ |
| **Phase 3** | | |
| `game.py` | 博弈引擎：Logit 份额 + Nash/Bertrand 最优反应 + 生态/联盟 + 跨象限外溢 + 规模效应；纯 python 无 LLM | ✅ |
| `config.py` | +17 预设企业 / 换电联盟 / 竞争类型映射 / Logit·生态·联盟旋钮 / `SIGMA_CROSS` / `SCALE_ELASTICITY` | ✅ |
| `app.py` | 三 tab：象限地图 · Phase 2 双线 · Phase 3 双散点（3 动作旋钮 + 评判指标 + 预设战略）→ **Phase 4 已合为两 tab** | ✅ |
| `PHASE3_audit_log.md` | 博弈层设计 / 冻结决策 / §E 验收 | ✅ |
| **Phase 4** | | |
| `triggers.py` | 触发枚举与检索 query 模板（纯常量）：policy 用 `城市×裁决态`、strategy 用 `象限×裁决态` | ✅ |
| `build_corpus.py` | **构建期**：切片 → 离线嵌入 → 写 `vecs.npz` → 有效分辨率/锚点命中/语料利用率三项诊断 | ✅ |
| `brief.py` | **运行期**：触发 → 检索（锚定+补位）→ 生成 → **出口对账** → 屏上两段 + docx 四章 | ✅ |
| `corpus/policy.md` · `strategy.md` | 语料源：地方产业政策 22 条 + 车企战略 9 条（摘编，带来源） | ✅ |
| `corpus/chunks.jsonl` · `vecs.npz` | 切片与向量产物（**必须入库**，Cloud 无 embedding key） | ✅ |
| `cache/*.json` | 演示缓存：断网/限流也能演示 | ✅ |
| `app.py` | 两 tab：象限地图 · 沙盘（A 财务双线 / B 博弈双散点 / C 简报）+ 仪表盘视觉 | ✅ |
| `PHASE4_audit_log.md` | 合页与 RAG 设计 / 决策演变 / 红线落地 / §F 验收 | ✅ |
| **通用** | | |
| `requirements.txt` | 依赖（pandas>=2.2 / numpy / statsmodels / plotly / streamlit / scipy / openai / python-docx） | ✅ |
| `0PROJECT_CHARTER_scope.md` | 范围护栏（刹车片） | ✅ |
| `nev.db` | 生成产物 | ❌（`.gitignore`；部署 `git add -f nev.db`） |
| `simulation_config.json` | `calibration.py` 现算产物 | ❌ |

## 验收

**Phase 0**：β 4/4 CI 覆盖真值 · 会计恒等式 · 四象限 ASP 可分(>2×) · 落库无损。

**Phase 1**：β OLS+车型 FE、γ delta-method 无衰减；t0 无滑块 ROE ≡ net_income/equity；公网 URL（Python 3.11）。

**Phase 2**：
- 杜邦恒等式（重构后仍精确）· WACC 单一实现（静态/动态一致）· IC≤0 容错
- t0 EBIT ≡ ebit_base · **spread 随滑块动**（真库：基线 +5.1% → 价格战 −22%，穿零轴）
- 裁决四态选句正确 · 文案全走 `copy_cn`
- 参数恢复 β 4/4 全绿；γ 8/10（Shanghai/Xian 两区待优化，见 `PHASE2_audit_log.md` §G）

**Phase 3**：
- 图一：拨定价打价格战 → 你被卷入价格战漩涡、对手坚守利润空间，你被打到**价值利差末位**（尺子翻转）
- 图二：生态/联盟 → aᵢ 上浮、联盟连边；Q2/Q4/Q3 内部无联盟边（换电门控：Tesla/比亚迪原型不入盟）
- 回扣 P2 价值机器（单一 WACC 实现一致）· 四态裁决（含 `WIN_ALONE` 独赢群输 / `CREATE_TRAIL` 创造价值但垫底）
- 评判指标切换即**两图**纵轴重排 · 三动作旋钮守 ≤3 · 术语全进 `copy_cn`
- v2：规模效应 e=0 时逐位回归 v1；长期口径自洽（资本随产量等比调整）；外溢 σ=0 时需求乘数恒为 1

**Phase 4**：
- 构建诊断：切片 31 条（policy 22 + strategy 9）· 锚点覆盖 **裁决态 5/5、象限 4/4** · 有效分辨率 **120 组合 → 90 组不同结果** · 裁决态命中 **120/120** · 视角隔离 **0/120** · 语料利用率 24/31
- 红线落地：定性标签进提示词、数值不进；**出口对账**冒烟三句中正确丢弃 2 句（口算词「腰斩」+ 白名单外数字），真实生成 `dropped` 为空、无误杀
- 简报中每个数字均可在引擎输出**逐字对上**；屏上与 docx 同源同字，导出不二次调用 LLM
- 四条降级路径（无 Key / 调用失败 / 段落被清空 / 缺检索产物）均能出简报——断网可演示
- 合页：定价滑块由两根合一、动作旋钮仍守 ≤3；四象限色板单一真相源，地图卡片与图二散点一一对应

## 已知事项

税 bug 降级 open item（数值层、不脏 spread、偏保守，搭车下次 Phase 0 重跑修；`game.py` 已用正式式）· γ 8/10（Shanghai/Xian 待优化）· `ensure_db()` 判据建议改为「存在**且有表**」（仓库内 `nev.db` 可能为空壳）· schema 中自研分 / 换电网络 / BOM 成本链**有意未接入引擎**（17 家为表外合成企业，接入属数值层求准；Phase 4 的 RAG 可用作叙事素材，但不得据此改动引擎数字）· Phase 4：`glm-4-flash` 仍会写少量套话（小模型上限，不再调提示词）· 象限地图在窄屏下中轴线列会被挤没。详见 `PHASE2_audit_log.md` §G、`PHASE3_audit_log.md`、`PHASE4_audit_log.md` §G。
