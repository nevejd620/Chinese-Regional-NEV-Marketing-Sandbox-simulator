# NEV 区域博弈沙盘 · Regional NEV Commercial Sandbox

> 博弈驱动的动态定价决策系统 —— 计量经济学微观行为模型 × 公司金融杜邦/ROIC-WACC，缝合成一个参数化数字孪生仿真系统。
> 场景：中国新能源汽车（NEV）产业的区域选址 × 象限战略博弈。

---

## 这是什么

一个把**选址禀赋 → 象限战略 → 定价博弈 → 财务价值裁决**串成一条因果链的决策支持沙盘。用户拨动战术/战略旋钮，系统即时推演 180 天、并给出 **ROIC − WACC 价值创造**判断；RAG 层再配一段有地方产业文献支撑的诊断简报。

**核心分析视角**：赢销量 ≠ 赢价值。价格战的胜利者常是价值的失败者。

## 诚实声明（务必先读）

- SQL 原子数据由 **DGP（数据生成过程）合成**，非真实市场数据。
- 行为系数 β（价格弹性）、γ（成本传导）为**「设定并经回归恢复验证」**，不是从真实市场实证发现——本项目做的是**参数恢复（parameter recovery）**方法演示，不是实证研究。
- 九家真实车企（蔚来/理想/比亚迪/小鹏/赛力斯等）仅作**锚点参照**：其无量纲比率用于校准可行域，绝对额（尤其特斯拉美元口径）**不入库**。

## 架构一览

| 层 | 职责 | 载体 |
|---|---|---|
| SQL（数值资产层） | 带时间戳/区位·象限标签的原子流水 | `nev.db`（6 表 + 车型维度） |
| JSON（规则系数层） | β/γ/θ、CAPM 常数、象限定价带等 | `config.py` |
| 模型 | 离线标定（回归恢复系数）+ 在线推演（180 天引擎） | `generate_data.py` 等 |

详见 `PHASE0_audit_log.md`（设计冻结/真值/验收）与 `NEV_architecture.svg`、ER 图。

## 阶段路线

- **Phase 0 · 数据地基**（当前）：合成数据 + SQLite + 参数恢复验收 ✅
- Phase 1：单城市引擎 + Streamlit 上线
- Phase 2：杜邦 + ROIC/WACC 价值创造前沿
- Phase 3：全国定价博弈（Logit-Bertrand，四象限竞技场）
- Phase 4：Action-triggered RAG + 总裁办简报
- Phase 5：收尾与叙事

## 快速开始

```bash
pip install -r requirements.txt
jupyter notebook NEV_Phase0.ipynb    # 或在 Google Colab 打开
```

Colab：上传 `NEV_Phase0.ipynb` + `generate_data.py` + `config.py` 到同目录，或直接
```python
!git clone https://github.com/<your-username>/nev-sandbox.git
%cd nev-sandbox && pip install -r requirements.txt -q
```

运行 notebook 即按六段工作流：① 生成 → ② 数据画像 → ③ 建表 → ④ SQL 展示 → ⑤ 关系检查 → ⑥ 验收。
`nev.db` 与 `ground_truth.json` 会自动生成（`nev.db` 不入 Git，靠代码重造）。

## 文件说明

| 文件 | 说明 | 进 Git |
|---|---|---|
| `NEV_Phase0.ipynb` | 六段工作流 notebook | ✅ |
| `generate_data.py` | DGP 生成模块（A 类因果 / B 类画像分层） | ✅ |
| `config.py` | 真值、可行域、象限/区域设定 | ✅ |
| `ground_truth.json` | 埋入真值台账（验收对照） | ✅ |
| `requirements.txt` | 依赖 | ✅ |
| `PHASE0_audit_log.md` | 设计冻结 / 验收清单 | ✅ |
| `nev.db` | 生成产物 | ❌（`.gitignore` 忽略；部署时可 force-add） |

## 验收（Phase 0 全绿）

- β 参数恢复：4/4 象限 95% CI 覆盖真值（model fixed effects，R² 0.87–0.97）
- 会计恒等式成立、无负销量
- 四象限 ASP 可分（高低差 >2×）
- 落库无损（SQL 复算 = DataFrame 画像）
