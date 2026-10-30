import Image from "next/image";

import metrics from "../public/project-metrics.json";

const githubUrl = process.env.NEXT_PUBLIC_GITHUB_URL ?? "https://github.com/lichangqing1/automotive-work-order-intelligence";

const capabilitiesEn = [
  { tag: "01", title: "Data quality", items: ["Configurable DQ rules", "Cross-table validation", "Source–target reconciliation", "Controlled defect injection", "Dataset versioning"] },
  { tag: "02", title: "Test engineering", items: ["Requirement-driven tests", "Persistent test versions", "Deterministic execution", "Result evidence", "Automated regression"] },
  { tag: "03", title: "AI for testing", items: ["Requirement analysis", "Test generation", "RCA assistance", "Prompt/model audit trail", "Human approval"] },
  { tag: "04", title: "Platform workflow", items: ["PostgreSQL + Alembic", "FastAPI services", "Jira integration", "CI and testing", "End-to-end traceability"] },
];

const capabilitiesZh = [
  { tag: "01", title: "数据质量", items: ["可配置 DQ 规则", "跨表验证", "源端与目标端对账", "受控缺陷注入", "数据集版本管理"] },
  { tag: "02", title: "测试工程", items: ["需求驱动测试", "持久化测试版本", "确定性执行", "结果证据", "自动化回归"] },
  { tag: "03", title: "AI 辅助测试", items: ["需求分析", "测试生成", "RCA 辅助", "提示词与模型审计链", "人工审批"] },
  { tag: "04", title: "平台流程", items: ["PostgreSQL + Alembic", "FastAPI 服务", "Jira 集成", "CI 与测试", "端到端可追溯性"] },
];

const architectureEn = [
  ["Jira", "Requirement"], ["Versioned", "Requirement"], ["AI-assisted", "Test design"],
  ["Human", "Review"], ["Deterministic", "Execution"], ["Evidence-rich", "Test result"],
  ["AI-assisted", "RCA"], ["Jira", "Defect"], ["Policy", "Quality gates"],
];

const architectureZh = [
  ["Jira", "需求"], ["版本化", "需求"], ["AI 辅助", "测试设计"],
  ["人工", "审核"], ["确定性", "执行"], ["证据化", "测试结果"],
  ["AI 辅助", "RCA"], ["Jira", "缺陷"], ["策略", "质量门禁"],
];

const workflowEn = ["Jira requirement", "AI analysis", "Test generation", "Schema validation", "Human review", "Approved test", "Deterministic run", "RCA + Jira evidence"];
const workflowZh = ["Jira 需求", "AI 分析", "测试生成", "结构验证", "人工审核", "审批后的测试", "确定性执行", "RCA + Jira 证据"];

function pct(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}

export default function LandingPage({ language = "en" }: { language?: "en" | "zh" }) {
  const zh = language === "zh";
  const tr = (english: string, chinese: string) => zh ? chinese : english;
  const capabilities = zh ? capabilitiesZh : capabilitiesEn;
  const architecture = zh ? architectureZh : architectureEn;
  const workflow = zh ? workflowZh : workflowEn;
  const metricLabel = (label: string) => zh ? ({
    "Requirement coverage": "需求覆盖率", "Negative coverage": "负向场景覆盖率",
    "Boundary coverage": "边界场景覆盖率", "Integration coverage": "集成场景覆盖率",
    "Data-quality coverage": "数据质量覆盖率",
  }[label] ?? label) : label;
  const checkLabel = (label: string) => zh ? ({
    completeness: "完整性", validity: "有效性", "temporal consistency": "时间一致性",
    "cross-table integrity": "跨表完整性", "source-target reconciliation": "源端与目标端对账", reconciliation: "源端与目标端对账",
    "business rules": "业务规则",
  }[label] ?? label) : label;
  return (
    <main lang={language}>
      <nav className="nav" aria-label={tr("Primary navigation", "主导航") }>
        <a className="brand" href="#top" aria-label={tr("Automotive Quality Engineering home", "汽车质量工程首页")}><span>AQ</span> Quality Engineering</a>
        <div className="nav-links">
          <a href="#architecture">{tr("Architecture", "系统架构")}</a><a href="#ai-value">{tr("Evidence", "实验结果")}</a><a href="#contribution">{tr("Contribution", "个人贡献")}</a>
          <span className="language-switch" aria-label={tr("Language", "语言")}><a className={!zh ? "active" : ""} href="/en" lang="en">EN</a><i>/</i><a className={zh ? "active" : ""} href="/zh" lang="zh-CN">中文</a></span>
        </div>
      </nav>

      <section className="hero section" id="top">
        <div className="hero-copy">
          <p className="eyebrow">{tr("PORTFOLIO CASE STUDY · QA / TEST DEVELOPMENT", "作品集案例 · QA / 测试开发")}</p>
          <h1>{tr("Automotive Work Order", "汽车工单")}<br/><em>{tr("AI Quality Engineering", "AI 质量工程")}</em> {tr("Platform", "平台")}</h1>
          <p className="lede">{tr("A production-shaped QA platform combining automotive data-quality validation, deterministic test automation, AI-assisted test design and RCA, Jira-based human review, and measured AI quality evaluation.", "一个面向汽车工单场景的生产化 QA 平台，结合数据质量验证、确定性自动化测试、AI 辅助测试设计与根因分析（RCA）、Jira 人工审核流程，以及可量化的 AI 质量评估。")}</p>
          <div className="actions">
            {githubUrl && <a className="button primary" href={githubUrl} target="_blank" rel="noreferrer">{tr("View source on GitHub", "查看 GitHub 源码")} <span>↗</span></a>}
            <a className="button primary" href="/evidence/AI_VALUE_EVIDENCE.md" target="_blank" rel="noreferrer">{tr("View evaluation evidence", "查看 AI 评估证据")} <span>↗</span></a>
            <a className="button secondary" href="#architecture">{tr("Explore architecture", "查看系统架构")}</a>
          </div>
          <p className="hero-note"><span className="pulse"/> {tr("AI proposes. Deterministic controls and people decide.", "AI 提供辅助建议，最终决策仍由确定性规则与人工审核完成。")}</p>
        </div>
        <div className="hero-panel" aria-label={tr("Project headline metrics", "项目核心指标")}>
          <div className="panel-label"><span>{tr("CONTROLLED BENCHMARK", "受控基准")}</span><span>v2.0.0</span></div>
          <div className="hero-metrics">
            <article><strong>{metrics.benchmark.workOrders.toLocaleString()}</strong><span>{tr("synthetic work orders", "受控合成工单")}</span></article>
            <article><strong>{metrics.benchmark.injectedDefects.toLocaleString()}</strong><span>{tr("injected defect rows", "人工注入缺陷记录")}</span></article>
            <article className="wide"><strong>{metrics.benchmark.detectedDefects.toLocaleString()} / {metrics.benchmark.injectedDefects.toLocaleString()}</strong><span>{tr("deliberately injected rows detected", "受控 DQ 基准中成功识别")}</span></article>
            <article><strong>{metrics.benchmark.aiEvaluationCases}</strong><span>{tr("curated AI cases", "AI 评估案例")}</span></article>
            <article><strong>{metrics.testGeneration.runs}×</strong><span>{tr("real-provider runs", "真实模型实验轮次")}</span></article>
          </div>
          <div className="signal-line"><span>DQ</span><i/><span>TEST</span><i/><span>REVIEW</span><i/><span>GATE</span></div>
        </div>
      </section>

      <section className="problem section ruled">
        <div><p className="section-index">01 / {tr("THE PROBLEM", "问题背景")}</p><h2>{tr("Operational data fails", "运营数据问题往往")}<br/>{tr("in connected ways.", "相互关联。")}</h2></div>
        <div className="problem-copy">
          <p>{tr("Automotive work-order platforms combine API data, relational records, OTA versions, diagnostic events, state transitions, timestamps, and downstream workflows.", "汽车工单平台连接 API 数据、关系型记录、OTA 版本、诊断事件、状态流转、时间戳与下游业务流程。")}</p>
          <p>{tr("Quality failures surface as missing data, invalid transitions, cross-table inconsistencies, unsupported software versions, and temporal defects. This project explores where AI can assist—without making the LLM the final authority.", "质量问题可能表现为数据缺失、无效状态流转、跨表不一致、不受支持的软件版本或时间逻辑缺陷。本项目探索 AI 可以在哪些环节提供辅助，但不会让 LLM 成为最终裁决者。")}</p>
        </div>
      </section>

      <section className="section" id="capabilities">
        <header className="section-heading"><p className="section-index">02 / {tr("WHAT I BUILT", "项目能力")}</p><h2>{tr("One platform. Four engineering disciplines.", "一个平台，四类工程能力。")}</h2><p>{tr("Built as a cohesive quality system rather than a collection of disconnected demos.", "这是一个连贯的质量工程系统，而非彼此割裂的演示集合。")}</p></header>
        <div className="capability-grid">
          {capabilities.map((capability) => <article className="capability" key={capability.title}><span className="cap-tag">{capability.tag}</span><h3>{capability.title}</h3><ul>{capability.items.map(item => <li key={item}>{item}</li>)}</ul></article>)}
        </div>
      </section>

      <section className="section dark" id="architecture">
        <header className="section-heading inverse"><p className="section-index">03 / {tr("SYSTEM ARCHITECTURE", "系统架构")}</p><h2>{tr("Traceability from requirement", "从需求到发布决策的")}<br/>{tr("to release decision.", "端到端可追溯链路。")}</h2></header>
        <div className="architecture" aria-label={tr("System architecture flow", "系统架构流程")}>
          {architecture.map((node, index) => <div className="arch-wrap" key={node.join("-")}><article className={index === architecture.length - 1 ? "arch-node gate-node" : "arch-node"}><span>{String(index + 1).padStart(2, "0")}</span><strong>{node[0]}</strong><small>{node[1]}</small></article>{index < architecture.length - 1 && <b aria-hidden="true">→</b>}</div>)}
        </div>
        <p className="authority-rule"><span>{tr("CONTROL BOUNDARY", "控制边界")}</span> {tr("AI proposes and assists; Python, SQL, assertions, human review, and quality policies retain authority over execution and release decisions.", "AI 负责提出建议与提供辅助；Python、SQL、确定性断言、人工审核与质量策略继续掌握执行和发布决策权。")}</p>
      </section>

      <section className="section benchmark">
        <div className="benchmark-copy"><p className="section-index">04 / {tr("CONTROLLED DATA QUALITY", "受控数据质量基准")}</p><h2>{tr("Known defects in.", "注入已知缺陷，")}<br/>{tr("Evidence out.", "输出可验证证据。")}</h2><p>{tr("All", "在受控合成基准中，全部")} <strong>{metrics.benchmark.injectedDefects.toLocaleString()}</strong> {tr("deliberately injected defect rows were detected in the controlled", "条人工注入缺陷记录均被识别，基准数据共")} <strong>{metrics.benchmark.workOrders.toLocaleString()}</strong>{tr("-record synthetic benchmark.", " 条。")}</p><div className="checks">{metrics.benchmark.checks.map(check => <span key={check}>{checkLabel(check)}</span>)}</div></div>
        <div className="benchmark-visual"><div className="ring"><div><strong>{metrics.benchmark.detectedDefects.toLocaleString()}</strong><span>{tr("detected", "已识别")}</span></div></div><div className="benchmark-foot"><span><b>{metrics.benchmark.falseNegatives}</b> {tr("missed", "漏检")}</span><span><b>{metrics.benchmark.falsePositives}</b> {tr("false positives", "误报")}</span></div><p>{tr("Controlled benchmark result—not a claim of universal accuracy.", "这是受控基准结果，并非对通用准确率的宣称。")}</p></div>
      </section>

      <section className="section workflow-section">
        <header className="section-heading"><p className="section-index">05 / {tr("AI-ASSISTED WORKFLOW", "AI 辅助测试流程")}</p><h2>{tr("Useful automation.", "让自动化创造价值，")}<br/>{tr("Explicit human control.", "同时保留明确的人工控制。")}</h2></header>
        <div className="workflow">{workflow.map((step, index) => <div className="workflow-step" key={step}><span>{String(index + 1).padStart(2, "0")}</span><strong>{step}</strong>{index < workflow.length - 1 && <b>↓</b>}</div>)}</div>
        <div className="never-rule"><span>{tr("NON-NEGOTIABLE", "不可妥协原则")}</span><strong>{tr("AI never decides test PASS / FAIL.", "AI 不直接决定测试通过或失败。")}</strong><p>{tr("Approved tests execute through deterministic assertions and evidence-producing services.", "通过审核的测试由确定性断言和证据生成服务执行。")}</p></div>
      </section>

      <section className="section evidence" id="ai-value">
        <header className="section-heading"><p className="section-index">06 / {tr("MEASURED AI VALUE", "量化 AI 价值")}</p><h2>{tr("Measured gains.", "量化收益，")}<br/>{tr("Measured regressions.", "也量化风险。")}</h2><p>{tr("Three real-provider runs per experiment, complete human review, versioned inputs, and policy-based release gates.", "每项实验包含三轮真实模型运行、完整人工审核、版本化输入，以及基于策略的发布门禁。")}</p></header>
        <div className="evidence-grid">
          <article className="evidence-card">
            <div className="evidence-title"><span>{tr("TEST GENERATION", "测试生成（Test Generation）")}</span><b className="status blocked">BLOCK<span>{zh ? " · 阻断" : ""}</span></b></div>
            <h3>{tr("AI improved the baseline—not human-only quality.", "AI 优于确定性基线，但未超过纯人工设计质量。")}</h3>
            <div className="metric-table"><div className="table-head"><span>{tr("Metric", "指标")}</span><span>{tr("Deterministic", "确定性基线")}</span><span>{tr("AI-assisted", "AI 辅助")}</span></div>{metrics.testGeneration.coverage.map(row => <div className="table-row" key={row.label}><span>{metricLabel(row.label)}</span><span>{pct(row.baseline)}</span><strong>{pct(row.ai)}</strong></div>)}</div>
            <div className="callout-row"><div className="positive"><span>{tr("Human effort saved", "人工投入减少")}</span><strong>{pct(metrics.testGeneration.humanEffortSaving)}</strong></div><div className="warning"><span>{tr("AI rejection rate", "AI 用例拒绝率")}</span><strong>{pct(metrics.testGeneration.rejectionRate)}</strong></div></div>
            <div className="comparison-note"><span>{tr("Human-only coverage", "纯人工需求覆盖率")} <b>{pct(metrics.testGeneration.humanOnlyCoverage)}</b></span><span>{tr("AI-assisted", "AI 辅助")} <b>{pct(metrics.testGeneration.aiCoverage)}</b></span></div>
          </article>

          <article className="evidence-card rca-card">
            <div className="evidence-title"><span>{tr("ROOT-CAUSE ANALYSIS", "根因分析（RCA）")}</span><b className="status blocked">BLOCK<span>{zh ? " · 阻断" : ""}</span></b></div>
            <h3>{tr("Faster investigation—not autonomous diagnosis.", "调查更高效，但不能自动诊断。")}</h3>
            <div className="time-shift"><div><span>{tr("Deterministic", "确定性基线")}</span><strong>{metrics.rca.baselineSeconds.toFixed(2)} s</strong></div><b>→</b><div><span>{tr("AI-assisted", "AI 辅助")}</span><strong>{metrics.rca.aiSeconds.toFixed(2)} s</strong></div></div>
            <div className="rca-metrics"><div><span>{tr("Recommended-check usefulness", "建议检查项有效性")}</span><strong>{pct(metrics.rca.checkUsefulness)}</strong><i className="good-bar" style={{"--value": `${metrics.rca.checkUsefulness * 100}%`} as React.CSSProperties}/></div><div><span>{tr("Evidence support", "证据支持率")}</span><strong>{pct(metrics.rca.evidenceSupport)}</strong><i className="good-bar" style={{"--value": `${metrics.rca.evidenceSupport * 100}%`} as React.CSSProperties}/></div><div className="failed-metric"><span>{tr("Root-cause accuracy", "根因准确率")}</span><strong>{pct(metrics.rca.rootCauseAccuracy)} — {tr("failed threshold", "未达阈值")}</strong><i className="bad-bar"/><small>{tr("Quality regression", "质量退化")}</small></div><div className="failed-metric"><span>{tr("Failure-class accuracy", "故障分类准确率")}</span><strong>{pct(metrics.rca.failureClassAccuracy)} — {tr("failed threshold", "未达阈值")}</strong><i className="bad-bar"/><small>{tr("Quality regression", "质量退化")}</small></div></div>
            <p className="card-conclusion">{tr("Useful as an", "适合作为")} <strong>{tr("investigation assistant", "调查辅助工具")}</strong>{tr("; not reliable enough to operate as an autonomous diagnosis engine.", "，但可靠性不足以支持自主诊断。")}</p>
          </article>
        </div>
      </section>

      <section className="section gates">
        <div className="gate-intro"><p className="section-index">07 / {tr("QUALITY GATES", "质量门禁（Quality Gate）")}</p><h2>{tr("The system knows", "系统知道")}<br/>{tr("when to say no.", "何时必须拒绝。")}</h2><p>{tr("Both configurations produced measurable benefits, but failed predefined thresholds. The platform blocks autonomous promotion rather than averaging failures away.", "两种配置都带来了可量化收益，但未通过预设阈值。平台会阻断自主上线，而不是用平均值掩盖失败指标。")}</p></div>
        <div className="gate-cards"><article><span>{tr("TEST GENERATION", "测试生成")}</span><strong>BLOCK{zh ? " · 阻断" : ""}</strong><p>{tr("Coverage, unsupported assumptions, and approval thresholds failed.", "覆盖率、无依据假设和审批率未达到门禁要求。")}</p></article><article><span>{tr("ROOT-CAUSE ANALYSIS", "根因分析")}</span><strong>BLOCK{zh ? " · 阻断" : ""}</strong><p>{tr("Accuracy, abstention, and unsupported-claim thresholds failed.", "准确率、正确拒答率和无依据结论指标未达到门禁要求。")}</p></article></div>
      </section>

      <section className="section contribution" id="contribution">
        <div><p className="section-index">08 / {tr("MY CONTRIBUTION", "个人贡献")}</p><h2>{tr("Designed and built", "独立完成设计与")}<br/>{tr("end to end.", "端到端实现。")}</h2></div>
        <div><p>{tr("Independently designed and implemented the platform architecture, PostgreSQL data model, configurable DQ framework, SQL validation, automated test workflow, FastAPI services, Jira integration, AI provider abstraction, human-review path, RCA pipeline, evaluation framework, quality policies, and controlled benchmark experiments.", "独立设计并实现平台架构、PostgreSQL 数据模型、可配置 DQ 框架、SQL 验证、自动化测试流程、FastAPI 服务、Jira 集成、AI 提供方抽象、人工审核路径、RCA 流程、评估框架、质量策略与受控基准实验。")}</p><div className="stack">{metrics.technology.map(item => <span key={item}>{item}</span>)}</div></div>
      </section>

      <section className="section product-evidence" id="product-evidence">
        <header className="section-heading"><p className="section-index">09 / {tr("SELECTED SYSTEM EVIDENCE", "系统证据节选")}</p><h2>{tr("Implemented workflows,", "展示真实实现流程，")}<br/>{tr("not presentation mockups.", "而非演示原型。")}</h2><p>{tr("Authentic captures from the FastAPI-backed Streamlit engineering console using the project’s local runtime and committed evaluation evidence.", "以下截图来自由 FastAPI 支撑的 Streamlit 工程控制台，使用项目本地运行时和已提交的评估证据。")}</p></header>
        <div className="screenshot-grid">
          <figure><a href="/screenshots/engineering-overview.png" target="_blank" rel="noreferrer"><Image src="/screenshots/engineering-overview.png" width={1280} height={720} sizes="(max-width: 640px) 100vw, 50vw" alt={tr("Engineering console overview with work-order metrics", "包含工单指标的工程控制台概览")}/></a><figcaption><span>01</span><strong>{tr("Engineering overview", "工程概览")}</strong><small>{tr("Live work-order and backlog metrics", "实时工单与待处理指标")}</small></figcaption></figure>
          <figure><a href="/screenshots/test-runs.png" target="_blank" rel="noreferrer"><Image src="/screenshots/test-runs.png" width={1280} height={720} sizes="(max-width: 640px) 100vw, 50vw" alt={tr("Persistent test run records in the engineering console", "工程控制台中的持久化测试执行记录")}/></a><figcaption><span>02</span><strong>{tr("Test execution records", "测试执行记录")}</strong><small>{tr("Persistent deterministic run evidence", "持久化确定性执行证据")}</small></figcaption></figure>
          <figure><a href="/screenshots/case-retrieval.png" target="_blank" rel="noreferrer"><Image src="/screenshots/case-retrieval.png" width={1280} height={720} sizes="(max-width: 640px) 100vw, 50vw" alt={tr("Authoritative case evidence retrieval interface", "权威案例证据检索界面")}/></a><figcaption><span>03</span><strong>{tr("Evidence retrieval", "证据检索")}</strong><small>{tr("Dataset-bound historical case search", "绑定数据集版本的历史案例搜索")}</small></figcaption></figure>
          <figure><a href="/screenshots/ai-value-gates.png" target="_blank" rel="noreferrer"><Image src="/screenshots/ai-value-gates.png" width={1280} height={720} sizes="(max-width: 640px) 100vw, 50vw" alt={tr("AI value dashboard with BLOCK quality gate results", "显示 BLOCK 质量门禁结果的 AI 价值仪表板")}/></a><figcaption><span>04</span><strong>{tr("AI value and gates", "AI 价值与质量门禁")}</strong><small>{tr("Measured gains, failures, and BLOCK decisions", "量化收益、失败指标与 BLOCK 决策")}</small></figcaption></figure>
        </div>
      </section>

      <section className="section evidence-links" id="evidence">
        <header><p className="section-index">10 / {tr("EVIDENCE", "项目证据")}</p><h2>{tr("Inspect the files,", "查看真实文件，")}<br/>{tr("not just the claims.", "而不只是项目结论。")}</h2></header>
        <div className="link-grid">{githubUrl && <a href={githubUrl} target="_blank" rel="noreferrer"><span>00</span><strong>{tr("GitHub source", "GitHub 源码")}</strong><small>{tr("Browse the implementation and test suite", "查看实现代码与测试套件")}</small><b>↗</b></a>}<a href="/evidence/PROJECT_README.md" target="_blank" rel="noreferrer"><span>01</span><strong>{tr("Repository guide", "项目说明")}</strong><small>{tr("Project scope, setup, and implementation", "项目范围、运行方式与实现说明")}</small><b>↗</b></a><a href="/evidence/AI_VALUE_EVIDENCE.md" target="_blank" rel="noreferrer"><span>02</span><strong>{tr("AI evaluation evidence", "AI 评估证据")}</strong><small>{tr("Design, limitations, and reproducibility", "实验设计、局限与可复现性")}</small><b>↗</b></a><a href="/evidence/test_generation_report.json" target="_blank" rel="noreferrer"><span>03</span><strong>{tr("Test-generation report", "测试生成报告")}</strong><small>{tr("Sanitized measured results", "脱敏后的量化结果")}</small><b>↗</b></a><a href="/evidence/rca_report.json" target="_blank" rel="noreferrer"><span>04</span><strong>{tr("RCA report", "RCA 报告")}</strong><small>{tr("Accuracy, support, and policy results", "准确率、证据支持与策略结果")}</small><b>↗</b></a><a href="/evidence/AUTOMOTIVE_ARCHITECTURE.md" target="_blank" rel="noreferrer"><span>05</span><strong>{tr("Architecture document", "架构文档")}</strong><small>{tr("Runtime and system boundaries", "运行时与系统边界")}</small><b>↗</b></a><a href="#product-evidence"><span>06</span><strong>{tr("Workflow captures", "流程截图")}</strong><small>{tr("Selected implemented product evidence", "已实现产品流程的证据节选")}</small><b>↑</b></a></div>
      </section>

      <footer><div className="brand"><span>AQ</span> Quality Engineering</div><p>{tr("Measured evidence over marketing claims.", "以量化证据取代营销式宣称。")}</p><small>{tr("Automotive Work Order Intelligence · Portfolio release v2.0.0", "汽车工单智能平台 · 作品集版本 v2.0.0")}</small></footer>
    </main>
  );
}
