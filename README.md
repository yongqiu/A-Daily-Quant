# A-Daily-TradingAgents

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Backend-FastAPI-009688.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/Frontend-Vue_3_%2B_Vite-42b883.svg" alt="Vue">
  <img src="https://img.shields.io/badge/AI-Multi_Agent_Analysis-purple.svg" alt="AI">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
</div>

<div align="center">
  <h3>轻量级 A 股交易分析台：双评分、结构化决策、多 Agent 复盘</h3>
</div>

---

## 项目定位

`A-Daily-TradingAgents` 面向个人投资者和轻量研究场景，目标不是做一个重型量化交易基础设施，而是提供一个可以在本地快速跑起来的交易分析工作台：

- 用统一的数据工厂拉齐行情、技术面、分时和扩展上下文
- 用机器评分先给出可解释的量化判断
- 用多 Agent 或单专家分析对机器判断进行复核
- 在 Web 看板中集中查看候选股、持仓、评分和 AI 结论

它更像“分析与决策辅助系统”，不是自动下单系统。

## 当前核心能力

- 双评分体系
  - `entry_score`：偏候选筛选和买点质量
  - `holding_score`：偏持仓延续、破位风险和退出节奏
  - `holding_state`：把持仓评分映射为 `HOLD / OBSERVE / REDUCE_ALERT / EXIT`
- 统一分析快照
  - 通过 `analysis_snapshot` 把技术面、实时数据、市场上下文、机器偏向和风险标记收敛到同一个结构
  - 评分、Prompt、AI 分析、数据库存储、前端展示共用一套事实来源
- 结构化 AI 决策
  - 多 Agent 分析结果会被解析成结构化意见
  - 再由统一决策引擎给出 `final_action`、`risk_level`、`consensus_level`
- Web 看板
  - Dashboard 展示持仓、持仓评分、持仓状态、AI 结论
  - Screener 展示候选股、入场评分、详细评分卡和分析报告
- 轻量部署
  - 默认 SQLite，可直接本地运行
  - 同时保留对 MySQL 的兼容路径

## 界面与交互

- Dashboard
  - 持仓列表按 `holding_score` 和风险状态排序
  - 支持查看评分卡、AI 分析、结构化决策摘要
- Screener
  - 候选股按 `entry_score` 和旧综合分排序
  - 支持查看详情、刷新评分、生成分析报告
- 分析流
  - 支持单专家分析
  - 支持多 Agent 流式辩论和 CIO 汇总

## 技术架构

| 组件 | 作用 |
| :--- | :--- |
| `start.py` | 一键初始化配置、数据库并启动服务 |
| `web_server.py` | FastAPI 服务入口，负责 API、评分、分析流和前端静态资源 |
| `strategy_data_factory.py` | 统一数据工厂，负责上下文装配与缓存 |
| `stock_scoring.py` | 统一评分入口，返回前后端共用的评分结果 |
| `dual_score.py` | 双评分规则：入场评分、持仓评分、持仓状态 |
| `analysis_snapshot.py` | 统一快照结构，承载机器判断和风险提示 |
| `decision_engine.py` | 汇总机器判断与 Agent 输出，给出最终动作 |
| `agent_analyst.py` | 多 Agent 分析调度与流式输出 |
| `llm_analyst.py` | Prompt 生成、模型调用、分析格式化 |
| `database.py` | SQLite / MySQL 兼容的数据持久层和迁移逻辑 |
| `frontend/` | Vue 3 + Vite 前端界面 |

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/cyecho-io/A-Daily-TradingAgents.git
cd A-Daily-TradingAgents
```

### 2. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 准备配置

```bash
cp config.json.example config.json
```

至少需要检查这些配置项：

- `data_source.tushare_token`
  - 如果配置了 Tushare，部分数据路径会更完整
  - 未配置时，系统会尽量退化到免费数据源
- `api.provider`
- `api_<provider>.api_key`
- `api_<provider>.base_url`
- `api_<provider>.model`

### 4. 启动服务

```bash
python start.py
```

默认会在本地启动：

```text
http://127.0.0.1:8100
```

## 开发方式

如果只使用内置前端静态资源，直接运行：

```bash
python start.py
```

如果需要单独开发前端：

```bash
cd frontend
npm install
npm run dev
```

后端仍通过项目根目录运行：

```bash
python web_server.py
```

## 数据与存储说明

- 默认数据库为 SQLite
- `daily_metrics` 会保存每日评分结果，包括：
  - `composite_score`
  - `entry_score`
  - `holding_score`
  - `holding_state`
  - 各类 breakdown 和 detail 字段
- `holding_analysis` 会保存分析结果及结构化决策，包括：
  - `analysis_snapshot`
  - `final_action`
  - `risk_level`
  - `consensus_level`
  - `agent_outputs`

## 当前实现边界

- 项目重点是“分析辅助”和“决策复盘”，不是全自动交易执行
- 评分体系当前以规则驱动为主，不是完整机器学习信号平台
- 研究性质的离线实验目录默认不再保留在仓库主线中

## 免责声明

本项目仅供技术研究与学习交流使用。市场有风险，投资需谨慎。项目中的评分、分析和策略结论均不构成任何投资建议，也不应直接用于真实资金的自动化交易。

---

Powered by Cyecho
