# 汽车工单数据质量与 AI 辅助测试工程平台

[English](README.md) | 简体中文

**版本：** [`v2.0.0 — Measured AI Quality Platform`](docs/releases/v2.0.0.md)

**在线项目网站：** [English](https://automotive-ai-quality-engineering.p154820.chatgpt.site/en) · [简体中文](https://automotive-ai-quality-engineering.p154820.chatgpt.site/zh) · [GitHub 源码](https://github.com/lichangqing1/automotive-work-order-intelligence)

> 本项目构建了一个面向汽车售后、OTA 与诊断工单场景的生产化质量工程平台，将数据质量验证、自动化测试、AI 辅助测试生成、根因分析（Root Cause Analysis, RCA）、Jira 人工审核以及可量化的 AI 评估整合到同一条可追溯流程中。

> 实验结果表明，AI 相比确定性基线提高了多个测试覆盖指标并减少了人工投入，但未超过纯人工测试设计的需求覆盖率，同时仍存在无依据假设和 RCA 准确率问题。因此，当前测试生成和 RCA 两项 AI 质量策略均保持 `BLOCK`（未通过质量门禁）。

English README 是完整技术文档和项目事实的权威来源。本中文文档面向中文招聘人员与技术面试官，提供更精炼的项目概览。完整 API、运行命令和开发细节请参阅 [English README](README.md)。

## 1. 项目简介

汽车工单平台通常同时涉及 API 数据、关系型记录、OTA 软件版本、诊断事件、状态流转、时间戳和下游运营流程。标识缺失、状态异常、版本不兼容、跨表不一致或分析结果与源系统不一致，都会降低工单系统的可靠性。

本项目将这些问题作为一个完整的**数据测试与测试工程系统**处理，并将 AI 放在确定性控制之后：

1. **数据质量（Data Quality）**：关系型数据、Python 处理、SQL 验证、隔离与源目标对账。
2. **测试开发（Test Development）**：版本化测试资产、持久化执行结果、证据和 API 契约。
3. **AI 辅助测试（AI for Testing）**：结构化需求分析、测试生成、DQ 规则草拟和证据约束 RCA。
4. **AI 质量工程（AI Quality Engineering）**：可执行基准、人工审核和策略化质量门禁。

核心原则是：

> **AI 提供建议和辅助；Python、SQL、确定性断言、人工审核与质量策略保留最终执行和发布决策权。AI 不直接决定测试 PASS / FAIL。**

## 2. 核心能力

| 领域 | 已实现能力 |
|---|---|
| 平台运行时 | PostgreSQL 16、SQLAlchemy 2、Alembic、FastAPI `/api/v1`，单一权威数据链路 |
| 数据质量 | 唯一性、空值、枚举、比较、条件、外键、范围、正则、聚合对账与新鲜度规则 |
| 数据对账 | Raw − quarantined = clean；SQL mart、API 与分组指标对比及差异证据 |
| 测试管理 | 测试用例、版本、执行、预期值、实际值、受影响数据、证据和状态汇总 |
| AI 测试流程 | Mock/OpenAI 提供方抽象、提示词版本与哈希、结构化输出、人工审核和 AI 运行审计 |
| Jira 集成 | 需求导入、评审同步、缺陷创建、RCA 评论、幂等外部 ID 和失败重试 |
| 可追溯性 | RequirementVersion → TestCaseVersion → TestRun/TestResult → Jira defect → RCA AIRun |
| 质量门禁 | YAML 配置的通用指标、运算符和阈值策略，指标退化时阻断推广 |

## 3. 系统架构

仓库采用模块化单体架构：Streamlit 工程控制台与 FastAPI `/api/v1` 调用应用和领域服务；工单、数据质量、对账与测试管理共享 SQLAlchemy 2、Alembic 和 PostgreSQL 16。PostgreSQL、`automotive_quality` 和 `/api/v1` 构成唯一权威运行时，生产检索与工程控制台不会读取 SQLite、生成的 CSV 或回退数据。完整图示请参阅[系统架构文档](docs/AUTOMOTIVE_ARCHITECTURE.md)。

## 4. 端到端 AI 辅助测试流程

`Jira 需求 → RequirementVersion → AI 分析与测试生成 → Schema/证据验证 → 人工审核 → APPROVED TestCaseVersion → 确定性执行 → TestResult → Jira 缺陷与 AI 辅助 RCA → 质量门禁`

Jira 不可用时，已经产生的确定性 `TestResult` 不会被回滚。外部同步会记录 `PENDING`、`SUCCEEDED` 或 `FAILED` 状态并支持重试。

## 5. 受控数据质量基准

在受控合成数据基准中：

| 指标 | 结果 |
|---|---:|
| 汽车工单记录 | 30,000 |
| 人工注入缺陷记录 | 1,200 |
| 成功识别的注入缺陷 | 1,200 / 1,200 |
| 漏检 | 0 |
| 误报 | 0 |

该结果表示：**在 30,000 条受控合成工单数据中，成功识别全部 1,200 条人工注入的缺陷记录。** 它不是对所有生产数据场景“准确率 100%”的宣称。

验证范围包括完整性、有效性、时间一致性、跨表完整性、源目标对账和业务规则。

## 6. AI 价值评估结果

已完成的 `ai-value-v1` 测试生成与 RCA 实验均使用 OpenAI，分别执行三轮真实模型运行，完成全部人工审核，并通过不可变结果重新评分。脱敏后的汇总证据位于 [`artifacts/ai_value/`](artifacts/ai_value/README.md)。

### 测试生成（Test Generation）

| 指标 | 确定性基线 | AI 辅助 |
|---|---:|---:|
| 需求覆盖率 | 5.83% | 49.35% |
| 负向场景覆盖率 | 20.00% | 47.96% |
| 边界场景覆盖率 | 50.00% | 66.67% |
| 集成场景覆盖率 | 46.67% | 60.00% |
| 数据质量覆盖率 | 66.67% | 81.67% |

- 人工投入减少：**48.98%**
- 端到端时间减少：**19.00%**
- 纯人工需求覆盖率：**63.78%**
- AI 辅助需求覆盖率：**49.35%**
- AI 用例拒绝率：**60.42%**
- 无依据假设率：**100%**

结论：AI 明显优于确定性模板基线，并减少人工投入，但没有超过纯人工设计质量，而且产生了不可接受的无依据假设。因此测试生成质量门禁为 `BLOCK`。

### 根因分析（RCA）

| 指标 | 结果 |
|---|---:|
| 确定性基线平均调查时间 | 77.60 秒 |
| AI 辅助平均调查时间 | 49.41 秒 |
| 建议检查项有效性 | 75.56% |
| 证据支持率 | 94.52% |
| 无依据结论率 | 5.48% |
| 正确拒答率 | 13.33% |
| AI 根因准确率 | 0% |

结论：AI 在缩短调查时间和提供排查建议方面具有价值，但当前实验结果不足以支持其作为自主根因诊断引擎，因此 RCA 质量门禁保持 `BLOCK`。

## 7. 为什么质量门禁是 `BLOCK`

`BLOCK` 是评估报告记录的真实系统状态，不代表项目失败。它说明平台能够：

- 同时量化 AI 的收益与退化；
- 将效率提升与质量可靠性分开评估；
- 在覆盖率、准确率、证据支持、正确拒答或无依据结论未达阈值时阻断自主推广；
- 保留人工审核和确定性测试作为最终控制边界。

相比只展示成功案例，这种机制更能体现 AI QA/Test Development 的工程成熟度。

## 8. 技术栈

```text
Python · FastAPI · PostgreSQL · SQLAlchemy · Alembic · SQL
pytest · Pydantic · OpenAI · Jira REST API · Streamlit
Docker · GitHub Actions · React / Vinext（招聘展示页）
```

## 9. 快速启动

### Docker

```bash
cp .env.example .env
docker compose up --build
```

启动后可访问：

- API 文档：`http://localhost:8000/docs`
- 存活检查：`http://localhost:8000/health/live`
- 就绪检查：`http://localhost:8000/health/ready`

本地开发、数据库迁移、测试、AI 实验、Jira 配置和完整 API 清单请参阅 [English README](README.md)。

## 10. 项目结构

主要目录包括：`src/automotive_quality/`（权威平台）、`migrations/`、`sql/`、`evaluation/`、`artifacts/ai_value/`、`tests/`、`dashboard/`（工程控制台）、`landing/`（双语招聘展示页）和 `docs/`。详细目录说明见 [English README](README.md)。

## 11. 证据与技术文档

- [完整英文技术 README](README.md)
- [在线英文项目网站](https://automotive-ai-quality-engineering.p154820.chatgpt.site/en)
- [在线中文项目网站](https://automotive-ai-quality-engineering.p154820.chatgpt.site/zh)
- [AI 价值证据](artifacts/ai_value/README.md)
- [AI 价值评估方法](docs/AI_VALUE_EVALUATION.md)
- [系统架构](docs/AUTOMOTIVE_ARCHITECTURE.md)
- [v2.0.0 发布说明](docs/releases/v2.0.0.md)

## 12. 当前范围与后续计划

已完成权威 PostgreSQL 运行时、提供方无关的 AI 测试层、Jira 端到端审核与缺陷流程、版本化 AI 价值评估以及双语招聘展示页。CI 使用 `MockProvider`，真实 OpenAI 实验的完整人工审核结果以脱敏汇总证据发布。

后续阶段包括 Celery 工作进程、语义/pgvector 检索，以及专用 React 工程控制台。当前 React 页面仅用于招聘展示，Streamlit 仍是工程控制台；Redis 已为后续工作进程准备，但项目不会将其描述为已启用的任务执行系统。

本项目只支持针对具体指标的收益与退化结论，不宣称 AI 在所有测试任务中普遍优于人工。
