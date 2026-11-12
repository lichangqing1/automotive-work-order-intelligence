# 汽车工单数据质量与 AI 辅助测试工程平台

[English](README.md) | 简体中文

这是一个以证据为核心的工程作品集项目，将汽车工单数据质量、测试开发、受控 AI 辅助、人工审核与发布门禁整合为一条可追溯的 PostgreSQL 权威链路。

**快速入口：** [双语在线展示](https://automotive-ai-quality-engineering.p154820.chatgpt.site/zh) · [作品集证据导航](docs/portfolio/README.md) · [架构图](docs/portfolio/ARCHITECTURE.md) · [可复现演示](docs/portfolio/DEMO_GUIDE.md) · [GitHub 源码](https://github.com/lichangqing1/automotive-work-order-intelligence)

## 已验证的工程亮点

- 在 **30,000 条受控合成工单**中注入 1,200 条已知缺陷，并在该限定基准内检出 1,200/1,200；这不是生产环境准确率声明。
- 版本化 DQ 规则、隔离区、源目标对账、SQL mart、API 契约、测试证据与不可变数据集身份共用 PostgreSQL 权威运行时。
- AI 生成测试保持 `REVIEW_REQUIRED`；待审核或已拒绝版本不能执行。测试运行接口验证调用方提交的结果证据，不会假装自动执行人工测试步骤。
- API 已实现 Bearer 认证、RBAC、操作者归因、请求大小限制、Redis 配额与并发租约、PostgreSQL 持久化 AI 操作幂等和安全恢复。
- [GitHub Actions 运行 43178347023](https://github.com/lichangqing1/automotive-work-order-intelligence/actions/runs/43178347023) 在提交 `719a0bc` 上通过：PostgreSQL 12 项、Redis 4 项均零跳过；完整 pytest 为 246 通过、1 项有意跳过的真实 Jira 测试。
- 两项历史 AI 质量策略都保持 **BLOCK**。受控合成 staging 为 **CONDITIONAL GO**；共享与生产部署仍为 **NO-GO**。

## 当前架构

项目采用模块化单体：FastAPI `/api/v1`、领域/应用服务、SQLAlchemy/Alembic 和 PostgreSQL 构成权威工程运行时；Streamlit 是仅通过 API 访问的工程控制台；双语 Landing 是独立只读的招聘展示层。

Redis 已实际用于限流和 AI 并发租约，但**不是**后台任务工作器。Celery 类任务架构与 pgvector 检索仍未实现。完整边界与 AI 操作生命周期见[作品集架构图](docs/portfolio/ARCHITECTURE.md)。

## 核心能力

| 领域 | 已实现能力 |
|---|---|
| 数据质量 | 完整性、唯一性、枚举、比较、条件、外键、范围、正则、新鲜度与聚合对账 |
| 数据生命周期 | 不可变数据集版本、内容指纹、重复安全导入、隔离与独立失败审计 |
| 测试工程 | 版本化用例、审核、运行、预期/实际值、证据、缺陷与需求追踪 |
| AI 辅助 | 提供方解耦的需求分析、测试生成、DQ 草案、RCA、提示词哈希和 AI Run 审计 |
| AI 治理 | 人工审核、证据 ID 验证、完整性检查、确定性策略与 BLOCK 决策 |
| 安全 | 认证、RBAC、限流、并发保护、输入边界、Jira DLP、错误脱敏与安全日志 |
| 交付 | Alembic、Docker、真实 PostgreSQL/Redis CI、pytest、Ruff、pip-audit 与 Landing 构建 |

## 三个工程案例

1. [数据质量：受控缺陷、隔离与对账](docs/portfolio/CASE_DATA_QUALITY.md)
2. [RCA 指标完整性：为什么 94.52% 被修正为 13.33%](docs/portfolio/CASE_RCA_METRIC_INTEGRITY.md)
3. [AI 重试安全：解决租约丢失后 503 的重复执行风险](docs/portfolio/CASE_AI_RETRY_SAFETY.md)

## RCA 指标修正

保留的 `ai-value-v1` 历史报告记录了 94.52% 的证据支持率和 5.48% 的无依据结论率。后续指标完整性审查发现，v1 将“引用正确”与“结论真正被证据支持”混为一谈，并对遗漏或错误识别的结论给出过高分数。

| RCA 指标 | 保留的历史 v1 | 修正后的 `rca-metrics-v2` | 当前有效解释 |
|---|---:|---:|---|
| 证据支持率 | 94.52% | **13.33%** | v1 明显高估 |
| 无依据结论率 | 5.48% | **76.67%** | 风险不可接受 |
| 根因准确率 | 0% | **0%** | 禁止自主诊断 |
| 质量门禁 | BLOCK | **BLOCK** | 决策不变 |

当前作品集使用[修正对比报告](docs/reports/RCA_METRIC_INTEGRITY_V2_COMPARISON.md)和[版本化派生记录](docs/portfolio/data/rca_metrics_v2.json)中的 v2 指标。历史 JSON、人工审核、数据集、阈值和 manifest 均保持不变。

测试生成也只支持“具体指标”的结论：AI 需求覆盖率为 49.35%，高于 5.83% 的确定性模板基线，并减少 48.98% 的人工投入；但低于 63.78% 的纯人工覆盖率，且无依据假设率为 100%，因此策略仍为 `BLOCK`。

## 可复现演示

[演示指南](docs/portfolio/DEMO_GUIDE.md)仅使用合成 fixture、`MockProvider`、`LocalIssueTracker` 和隔离测试基础设施，不需要付费模型、真实 Jira、客户数据、数据库重置或 Redis flush。

```bash
source .venv/bin/activate
pytest -q tests/test_automotive_generator_quality.py
pytest -q tests/test_api_authentication.py tests/test_api_authorization.py
pytest -q tests/test_ai_operation_idempotency.py tests/test_rca_metric_integrity.py
python scripts/export_landing_data.py
pytest -q tests/test_landing_data.py
```

## AI 操作安全恢复

共享、staging 与生产配置下的提供方操作必须携带 8–128 字符的 `Idempotency-Key`。成功请求可重放已保存响应；冲突、执行中和歧义状态会被拒绝。认证后的调用方可查询：

```text
GET /api/v1/ai-operations/{operation_id}
```

`RUNNING` 和 `AMBIGUOUS` 不会被自动重新执行。任意崩溃场景下的外部提供方执行或计费仍不保证绝对 exactly-once。

## 技术栈与开发

Python 3.12 · FastAPI · PostgreSQL 16 · SQLAlchemy 2 · Alembic · Redis 7 · Pydantic · pytest · Ruff · OpenAI Structured Outputs · Jira REST · Streamlit · Docker · GitHub Actions · React/Vinext

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,security]'
docker compose up -d postgres redis
alembic upgrade head
pytest -q
ruff check .
```

本地 Compose 会暴露开发端口并使用占位凭据，不是生产部署规范。更多信息见[本地运行手册](docs/runbooks/local-development.md)、[API 认证](docs/API_AUTHENTICATION.md)、[授权模型](docs/API_AUTHORIZATION.md)、[限流与并发](docs/API_RATE_LIMITING.md)、[幂等设计](docs/AI_OPERATION_IDEMPOTENCY.md)和[C1 发布门禁](docs/reports/C1_SECURITY_RELEASE_GATE.md)。

## 范围与限制

- 所有基准数据均为合成或受控数据，不能外推到未观察的生产数据。
- Prompt injection 只能通过边界和 Schema 降低风险，不能被宣称完全消除。
- Celery worker、语义/pgvector 检索和专用 React 工程控制台尚未实现。
- 生产 Redis HA/TLS、应用 TLS、Secret Manager、网络隔离、备份恢复和安全事件运营仍未验证。
- 本地开发与隔离工程验证为 `GO`；受控合成 staging 为 `CONDITIONAL GO`；共享与生产部署为 `NO-GO`。

本项目的重点不是只展示 AI 的“成功”，而是用可复现证据同时衡量收益、缺陷与发布阻断条件。
