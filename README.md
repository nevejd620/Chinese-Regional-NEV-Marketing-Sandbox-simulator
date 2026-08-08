# NEV 区域博弈沙盘 · Regional NEV Commercial Sandbox

> 博弈驱动的动态定价决策系统 —— 计量经济学微观行为模型 × 公司金融杜邦/ROIC-WACC，缝合成一个参数化数字孪生仿真系统。
> 场景：中国新能源汽车（NEV）产业的区域选址 × 象限战略博弈。

**🔗 在线演示**：https://chinese-regional-nev-marketing-sandbox-simulator-3lpxhv6sebdda.streamlit.app/
（Phase 2 已上线：拨滑块看 **ROE 射线 + 价值 spread 双线联动** + 动态裁决 + 参数恢复表）

---

## 这是什么

一个把**选址禀赋 → 象限战略 → 定价博弈 → 财务价值裁决**串成一条因果链的决策支持沙盘。用户拨动战术/战略旋钮，系统即时推演 180 天，**上看 ROE（赚得多不多）、下看 spread = ROIC − WACC（这份回报值不值）**，两条线同步迁移给出价值裁决；RAG 层（Phase 4）再配一段有地方产业文献支撑的诊断简报。

**核心分析视角**：赢销量 ≠ 赢价值。价格战把 ROE 拨高的同时，常把 spread 拨到零轴下——**赢了销量，毁了价值**。

**一条时间轴主线**：生产前选址（Phase 0–1）→ 生产后独自结算（Phase 2，本阶段）→ 生产后互搏（Phase 3）。区域内不博弈（选址先于博弈 + 禀赋近似垄断），竞争只在全国·同象限。

## 诚实声明（务必先读）

- SQL 原子数据由 **DGP（数据生成过程）合成**，非真实市场数据。
- 行为系数 β（价格弹性）、γ（成本传导）为**「设定并经回归恢复验证」**，是**参数恢复（parameter recovery）**方法演示，非实证研究。
- 九家真实车企（蔚来/理想/比亚迪/小鹏/赛力斯等）仅作**锚点参照**校准可行域；沙盘里一个点是"某区域×象限的**代表性企业**"，非某家真公司、非"市场"。
- 沙盘引擎的数字是**确定性、可复现**的；RAG 只解释数字、绝不生产数字（LLM 幻觉够不到财务计算）。

## 架构一览

| 层 | 职责 | 载体 |
|---|---|---|
| SQL（数值资产层） | 带时间戳/区位·象限标签的原子流水 | `nev.db`（6 表 + 车型维度） |
| JSON（规则系数层） | β/γ/θ、CAPM 常数、象限定价带等 | `config.py`（真值） → `simulation_config.json`（回归恢复后，引擎输入） |
| 模型 | 离线标定（`calibration.py`）+ 在线推演（`simulate.py`）+ 价值后处理（`financials.py`） | 见下 |
| 文案（显示层） | 术语→人话翻译，两层交互，改它不重跑 | `copy_cn.py` |

详见 `PHASE0_audit_log.md`、`PHASE1_audit_log.md`、`PHASE2_audit_log.md`、`NEV_architecture.svg`、ER 图。范围护栏见 `0PROJECT_CHARTER_scope.md`。

## 阶段路线

- **Phase 0 · 数据地基** ✅（v0.1）
- **Phase 1 · 单城市引擎 + 上线** ✅（v0.2）
- **Phase 2 · 财务解剖与价值裁决**（当前）✅（v0.3）：杜邦 + ROIC/WACC + **ROE/spread 双线动态联动**
- Phase 3：全国定价博弈（Logit-Bertrand，四象限竞技场，相对排名回归）
- Phase 4：Action-triggered RAG + 总裁办简报
- Phase 5：收尾与叙事

## 快速开始

**本地运行沙盘**
```bash
pip install -r requirements.txt      # 需 pandas>=2.2
python calibration.py     # 读 nev.db → 回归恢复 β/γ → 写含 Phase2 字段的 simulation_config.json + 恢复表
streamlit run app.py      # 起沙盘：城市 + 3 滑块 + ROE/spread 双线 + 动态裁决 + 恢复表
```

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
| **通用** | | |
| `requirements.txt` | 依赖（pandas>=2.2 / numpy / statsmodels / plotly / streamlit / scipy） | ✅ |
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

## 已知事项

税 bug 降级 open item（数值层、不脏 spread、偏保守，搭车下次 Phase 0 重跑修）· γ 8/10 · 前沿散点/相对排名归 Phase 3（博弈层）。详见 `PHASE2_audit_log.md` §G。
