# NEV 区域博弈沙盘 · Regional NEV Commercial Sandbox

> 博弈驱动的动态定价决策系统 —— 计量经济学微观行为模型 × 公司金融杜邦/ROIC-WACC，缝合成一个参数化数字孪生仿真系统。
> 场景：中国新能源汽车（NEV）产业的区域选址 × 象限战略博弈。

**🔗 在线演示**：`https://chinese-regional-nev-marketing-sandbox-simulator-3lpxhv6sebdda.streamlit.app/`　（Phase 1 骨架已上线；拖滑块看 ROE 射线 + 参数恢复表）

---

## 这是什么

一个把**选址禀赋 → 象限战略 → 定价博弈 → 财务价值裁决**串成一条因果链的决策支持沙盘。用户拨动战术/战略旋钮，系统即时推演 180 天、并给出 **ROIC − WACC 价值创造**判断；RAG 层再配一段有地方产业文献支撑的诊断简报。

**核心分析视角**：赢销量 ≠ 赢价值。价格战的胜利者常是价值的失败者。

## 诚实声明（务必先读）

- SQL 原子数据由 **DGP（数据生成过程）合成**，非真实市场数据。
- 行为系数 β（价格弹性）、γ（成本传导）为**「设定并经回归恢复验证」**，不是从真实市场实证发现——本项目做的是**参数恢复（parameter recovery）**方法演示，不是实证研究。
- 九家真实车企（蔚来/理想/比亚迪/小鹏/赛力斯等）仅作**锚点参照**：其无量纲比率用于校准可行域，绝对额（尤其特斯拉美元口径）**不入库**。
- 沙盘引擎的数字是**确定性、可复现**的；RAG 只解释数字、绝不生产数字（LLM 幻觉够不到财务计算）。

## 架构一览

| 层 | 职责 | 载体 |
|---|---|---|
| SQL（数值资产层） | 带时间戳/区位·象限标签的原子流水 | `nev.db`（6 表 + 车型维度） |
| JSON（规则系数层） | β/γ/θ、CAPM 常数、象限定价带等 | `config.py`（真值） → `simulation_config.json`（回归恢复后，引擎输入） |
| 模型 | 离线标定（`calibration.py` 回归恢复系数）+ 在线推演（`simulate.py` 180 天引擎） | 见下 |

详见 `PHASE0_audit_log.md`（数据地基）、`PHASE1_audit_log.md`（引擎与部署）、`NEV_architecture.svg`、ER 图。

## 阶段路线

- **Phase 0 · 数据地基**：合成数据 + SQLite + 参数恢复验收 ✅
- **Phase 1 · 单城市引擎 + 上线**（当前）：`calibration.py` 参数恢复 + `simulate.py` 180 天引擎 + Streamlit 公网 URL ✅
- Phase 2：杜邦 + ROIC/WACC 价值创造前沿
- Phase 3：全国定价博弈（Logit-Bertrand，四象限竞技场）
- Phase 4：Action-triggered RAG + 总裁办简报
- Phase 5：收尾与叙事

## 快速开始

**本地运行沙盘（Phase 1）**
```bash
pip install -r requirements.txt
python calibration.py     # 读 nev.db → 回归恢复 β/γ → 写 simulation_config.json + 打印恢复表
python simulate.py        # 引擎冒烟：打印 baseline / t0 / t180 ROE
streamlit run app.py      # 起沙盘：城市选择 + 3 滑块 + ROE 射线 + 恢复表
```

**Google Colab**
```python
!git clone https://github.com/<your-username>/Chinese-Regional-NEV-Marketing-Sandbox-simulator.git
%cd Chinese-Regional-NEV-Marketing-Sandbox-simulator
!pip install -r requirements.txt -q
!python calibration.py    # 验证参数恢复
```
（若 `nev.db` 不在，`ensure_db.py` 会重生成；Colab 里预览 Streamlit 需 pyngrok 隧道，详见 `PHASE1_audit_log.md` §H。）

**复跑 Phase 0 数据地基**
```bash
jupyter notebook NEV_Phase0.ipynb   # 六段工作流：① 生成 → ② 画像 → ③ 建表 → ④ SQL 展示 → ⑤ 关系 → ⑥ 验收
```

## 文件说明

| 文件 | 说明 | 进 Git |
|---|---|---|
| **Phase 0** | | |
| `NEV_Phase0.ipynb` | 六段工作流 notebook | ✅ |
| `generate_data.py` | DGP 生成模块（A 类因果 / B 类画像分层） | ✅ |
| `config.py` | 真值、可行域、象限/区域设定 | ✅ |
| `ground_truth.json` | 埋入真值台账（验收对照） | ✅ |
| `PHASE0_audit_log.md` | 数据地基设计冻结 / 验收清单 | ✅ |
| **Phase 1** | | |
| `calibration.py` | 读 nev.db → OLS 恢复 β/γ → 参数恢复表 → 写 `simulation_config.json` | ✅ |
| `simulate.py` | 180 天向量化引擎：冲击衰减 + 蒙特卡洛置信带 + maturity 轨迹 | ✅ |
| `app.py` | 极薄 Streamlit：城市 + 3 滑块 + Plotly ROE 射线 + 恢复表 | ✅ |
| `ensure_db.py` | 部署自举：Cloud 首boot 若缺库则重生成 | ✅ |
| `.streamlit/config.toml` | Streamlit 主题/服务器设置 | ✅ |
| `test/make_mock_db.py` | 测试台：按文档 schema 造 mock 库（非 `generate_data.py`） | ✅ |
| `PHASE1_audit_log.md` | 引擎方法 / 验收 / 部署清单 | ✅ |
| **通用** | | |
| `requirements.txt` | 依赖（pandas/numpy/statsmodels/plotly/streamlit） | ✅ |
| `nev.db` | 生成产物 | ❌（`.gitignore` 忽略；部署时 `git add -f nev.db`） |
| `simulation_config.json` | `calibration.py` 现算产物 | ❌ |

## 验收

**Phase 0 · 数据地基（全绿）**
- β 参数恢复：4/4 象限 95% CI 覆盖真值（model fixed effects，R² 0.87–0.97）
- 会计恒等式成立、无负销量
- 四象限 ASP 可分（高低差 >2×）
- 落库无损（SQL 复算 = DataFrame 画像）

**Phase 1 · 引擎与上线**
- β OLS + 车型固定效应恢复；γ 用 delta-method（`γ=slope/(slope+intercept)`）无衰减偏差
- 引擎恒等：`t0` 无滑块 ROE ≡ `net_income/equity`；弹性方向、冲击衰减方向正确
- Streamlit 本地干净启动；`ensure_db.py` 删库可自愈
- Streamlit Community Cloud 公网 URL 可访问（Python 3.11，与 Colab 对齐）
