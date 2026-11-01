import metrics from "../public/project-metrics.json";

type Language = "en" | "zh";

const pct = (value: number) => `${(value * 100).toFixed(2)}%`;

export default function EvidencePage({ language = "en" }: { language?: Language }) {
  const zh = language === "zh";
  const tr = (en: string, cn: string) => zh ? cn : en;
  const home = zh ? "/zh" : "/en";
  const alternate = zh ? "/en/evidence" : "/zh/evidence";
  const coverageNames: Record<string, string> = {
    "Requirement coverage": "需求覆盖率", "Negative coverage": "负向场景覆盖率",
    "Boundary coverage": "边界场景覆盖率", "Integration coverage": "集成场景覆盖率",
    "Data-quality coverage": "数据质量覆盖率",
  };
  const coverage = metrics.testGeneration.coverage.map(row => ({ ...row, label: zh ? coverageNames[row.label] : row.label }));

  return <main className="evidence-page" lang={language}>
    <nav className="evidence-nav">
      <a className="brand" href={home}><span>AQ</span> Quality Engineering</a>
      <div><a href={home}>← {tr("Project overview", "返回项目概览")}</a><a href={alternate}>{zh ? "EN" : "中文"}</a></div>
    </nav>

    <header className="evidence-hero">
      <p className="eyebrow">{tr("VERIFIABLE PROJECT EVIDENCE", "可验证的项目证据")}</p>
      <h1>{tr("Evidence, made", "让证据更易于")}<br/><em>{tr("readable.", "阅读与核验。")}</em></h1>
      <p>{tr("A browser-native guide to the project scope, measured AI results, architecture, limitations, and source artifacts. Headline claims remain linked to the underlying committed evidence.", "以适合浏览器阅读的方式展示项目范围、AI 量化结果、系统架构、局限与源文件；所有核心结论仍可追溯到仓库中已提交的证据。")}</p>
      <div className="evidence-summary"><span><b>60</b>{tr("curated AI cases", "个 AI 评估案例")}</span><span><b>3×</b>{tr("real-provider runs", "真实模型重复实验")}</span><span><b>2</b>{tr("quality policies: BLOCK", "项质量策略：BLOCK")}</span></div>
    </header>

    <div className="evidence-shell">
      <aside className="evidence-toc" aria-label={tr("Evidence contents", "证据目录")}>
        <p>{tr("On this page", "本页目录")}</p>
        <a href="#project-guide">01 {tr("Project guide", "项目说明")}</a>
        <a href="#ai-value">02 {tr("Evaluation design", "评估设计")}</a>
        <a href="#test-generation">03 {tr("Test generation", "测试生成")}</a>
        <a href="#rca">04 {tr("RCA results", "RCA 结果")}</a>
        <a href="#architecture">05 {tr("Architecture", "系统架构")}</a>
        <a href="#reproducibility">06 {tr("Reproducibility", "可复现性")}</a>
        <a href="#source-artifacts">07 {tr("Source artifacts", "源文件")}</a>
      </aside>

      <article className="evidence-document">
        <section id="project-guide">
          <p className="doc-index">01 / {tr("PROJECT GUIDE", "项目说明")}</p>
          <h2>{tr("A production-shaped quality engineering system.", "一个面向真实工程流程设计的质量工程系统。")}</h2>
          <p>{tr("The platform connects automotive work-order data quality, deterministic test execution, AI-assisted test design and RCA, Jira-based human review, and policy-driven AI evaluation in one traceable workflow.", "平台将汽车工单数据质量、确定性测试执行、AI 辅助测试生成与 RCA、Jira 人工审核和策略化 AI 评估连接为一条可追溯流程。")}</p>
          <div className="doc-callout"><strong>{tr("Control boundary", "控制边界")}</strong><p>{tr("AI proposes and assists. Python, SQL, assertions, human review, and quality policies retain authority over PASS / FAIL and release decisions.", "AI 负责提出建议与提供辅助；Python、SQL、断言、人工审核与质量策略保留 PASS / FAIL 和发布决策权。")}</p></div>
          <div className="fact-grid"><div><b>{metrics.benchmark.workOrders.toLocaleString()}</b><span>{tr("controlled work orders", "条受控工单")}</span></div><div><b>{metrics.benchmark.detectedDefects.toLocaleString()} / {metrics.benchmark.injectedDefects.toLocaleString()}</b><span>{tr("injected defects detected", "人工注入缺陷被检出")}</span></div><div><b>PostgreSQL</b><span>{tr("authoritative runtime", "唯一权威运行时")}</span></div><div><b>Human review</b><span>{tr("required before execution", "执行前必须完成")}</span></div></div>
          <p className="doc-note">{tr("The benchmark uses synthetic, controlled data and is not a claim of universal production accuracy.", "该基准使用合成与受控数据，不代表生产环境中的通用准确率。")}</p>
        </section>

        <section id="ai-value">
          <p className="doc-index">02 / {tr("EVALUATION DESIGN", "评估设计")}</p>
          <h2>{tr("Publication-complete does not mean production-approved.", "证据完整，不等于可自主上线。")}</h2>
          <p>{tr("Both experiments used OpenAI, prompt version v2, one fixed model, three runs, immutable rescoring, and complete human review. Publication eligibility confirms evidence completeness; predefined quality thresholds still determine promotion.", "两项实验均使用 OpenAI、v2 提示词、固定模型、三轮运行、不可变重评分和完整人工审核。可发布只表示证据完整，是否推广仍由预定义质量阈值决定。")}</p>
          <div className="inventory-table" role="table" aria-label={tr("Experiment inventory", "实验清单")}>
            <div className="inventory-head" role="row"><span>{tr("Experiment", "实验")}</span><span>{tr("Cases", "案例")}</span><span>{tr("Reviews", "审核")}</span><span>{tr("Gate", "门禁")}</span></div>
            <div role="row"><strong>{tr("Test generation", "测试生成")}</strong><span>30 × 3</span><span>1,122 / 1,122</span><b>BLOCK</b></div>
            <div role="row"><strong>RCA</strong><span>30 × 3</span><span>90 / 90</span><b>BLOCK</b></div>
          </div>
        </section>

        <section id="test-generation">
          <p className="doc-index">03 / {tr("TEST-GENERATION RESULTS", "测试生成结果")}</p>
          <div className="doc-heading-row"><h2>{tr("Coverage gains with material quality risk.", "覆盖提升，同时伴随显著质量风险。")}</h2><span className="doc-status">BLOCK<small>{zh ? "未通过质量门禁" : "quality gate"}</small></span></div>
          <div className="doc-metric-table"><div><b>{tr("Metric", "指标")}</b><b>{tr("Baseline", "基线")}</b><b>{tr("AI-assisted", "AI 辅助")}</b><b>{tr("Difference", "差值")}</b></div>{coverage.map(row => <div key={row.label}><span>{row.label}</span><span>{pct(row.baseline)}</span><strong>{pct(row.ai)}</strong><em>+{((row.ai-row.baseline)*100).toFixed(2)} pp</em></div>)}</div>
          <div className="result-cards"><div className="gain"><span>{tr("Human effort saved", "人工投入减少")}</span><b>{pct(metrics.testGeneration.humanEffortSaving)}</b></div><div className="risk"><span>{tr("AI rejection rate", "AI 用例拒绝率")}</span><b>{pct(metrics.testGeneration.rejectionRate)}</b></div><div><span>{tr("Human-only coverage", "纯人工覆盖率")}</span><b>{pct(metrics.testGeneration.humanOnlyCoverage)}</b></div><div><span>{tr("AI-assisted coverage", "AI 辅助覆盖率")}</span><b>{pct(metrics.testGeneration.aiCoverage)}</b></div></div>
          <p>{tr("AI outperformed the deterministic template baseline and reduced effort, but did not outperform human-only requirement coverage. The unsupported-assumption threshold also failed, so autonomous promotion remains blocked.", "AI 优于确定性模板基线并减少人工投入，但没有超过纯人工需求覆盖率；无依据假设指标也未通过阈值，因此系统继续阻断自主推广。")}</p>
        </section>

        <section id="rca">
          <p className="doc-index">04 / {tr("RCA RESULTS", "RCA 结果")}</p>
          <div className="doc-heading-row"><h2>{tr("Faster investigation, unreliable diagnosis.", "调查更快，但诊断不可靠。")}</h2><span className="doc-status">BLOCK<small>{zh ? "未通过质量门禁" : "quality gate"}</small></span></div>
          <div className="doc-metric-table rca-table"><div><b>{tr("Metric", "指标")}</b><b>{tr("Baseline", "基线")}</b><b>{tr("AI-assisted", "AI 辅助")}</b><b>{tr("Interpretation", "结论")}</b></div><div><span>{tr("Investigation time", "调查时间")}</span><span>{metrics.rca.baselineSeconds.toFixed(2)} s</span><strong>{metrics.rca.aiSeconds.toFixed(2)} s</strong><em className="good">-28.19 s</em></div><div><span>{tr("Evidence support", "证据支持率")}</span><span>100.00%</span><strong>{pct(metrics.rca.evidenceSupport)}</strong><em>-5.48 pp</em></div><div><span>{tr("Failure-class accuracy", "故障分类准确率")}</span><span>36.67%</span><strong>{pct(metrics.rca.failureClassAccuracy)}</strong><em className="bad">{tr("regression", "退化")}</em></div><div><span>{tr("Root-cause accuracy", "根因准确率")}</span><span>20.00%</span><strong>{pct(metrics.rca.rootCauseAccuracy)}</strong><em className="bad">{tr("failed", "未达标")}</em></div></div>
          <p>{tr("Recommended-check usefulness reached 75.56%, but accuracy, abstention, and unsupported-claim thresholds failed. AI is useful as an investigation assistant—not an autonomous diagnosis engine.", "建议检查项有效性达到 75.56%，但准确率、正确拒答和无依据结论指标未达阈值。AI 适合作为调查辅助工具，而不是自主诊断引擎。")}</p>
        </section>

        <section id="architecture">
          <p className="doc-index">05 / {tr("ARCHITECTURE", "系统架构")}</p>
          <h2>{tr("Traceability and vendor-neutral boundaries.", "可追溯且与具体供应商解耦。")}</h2>
          <div className="doc-flow" aria-label={tr("Traceability flow", "可追溯流程")}><span>RequirementVersion</span><b>→</b><span>TestCaseVersion</span><b>→</b><span>ReviewRequest</span><b>→</b><span>TestResult</span><b>→</b><span>Jira defect</span><b>→</b><span>RCA AIRun</span></div>
          <p>{tr("PostgreSQL, automotive_quality, and /api/v1 form the authoritative runtime. LLMProvider isolates AI workflows from vendors; IssueTracker isolates test and review logic from Jira. Deterministic test results commit before retryable external synchronization.", "PostgreSQL、automotive_quality 和 /api/v1 构成权威运行时。LLMProvider 将 AI 工作流与模型供应商解耦，IssueTracker 将测试与审核逻辑和 Jira 解耦。确定性测试结果会在可重试的外部同步之前提交。")}</p>
          <div className="boundary-grid"><div><strong>LLMProvider</strong><span>MockProvider</span><span>OpenAIProvider</span><span>{tr("future adapters", "未来适配器")}</span></div><div><strong>IssueTracker</strong><span>LocalIssueTracker</span><span>JiraIssueTracker</span><span>{tr("future adapters", "未来适配器")}</span></div></div>
        </section>

        <section id="reproducibility">
          <p className="doc-index">06 / {tr("REPRODUCIBILITY & PRIVACY", "可复现性与隐私")}</p>
          <h2>{tr("Auditable without exposing sensitive records.", "可核验，同时不暴露敏感记录。")}</h2>
          <ul className="doc-list"><li>{tr("Reports retain experiment, provider, model, prompt, dataset, hash, run-count, aggregate, and policy metadata.", "报告保留实验、提供方、模型、提示词、数据集、哈希、运行次数、汇总指标和策略元数据。")}</li><li>{tr("Raw outputs, reviewer identities, credentials, Jira configuration, and individual reviewer timings are excluded.", "原始输出、审核者身份、凭据、Jira 配置和个人审核耗时不会公开。")}</li><li>{tr("Synthetic and controlled data contains no real customer, vehicle, or personal information.", "合成与受控数据不包含真实客户、车辆或个人信息。")}</li><li>{tr("Thresholds remain proposed_until_calibrated and are not represented as business-approved.", "阈值仍标记为 proposed_until_calibrated，不会被描述为已经业务批准。")}</li></ul>
        </section>

        <section id="source-artifacts">
          <p className="doc-index">07 / {tr("SOURCE ARTIFACTS", "源文件")}</p>
          <h2>{tr("Need the machine-readable evidence?", "需要查看机器可读证据？")}</h2>
          <p>{tr("These source artifacts remain available for audit and download. The formatted sections above are the recommended browser-reading experience.", "以下源文件仍可用于审计和下载；浏览器阅读建议优先使用上方格式化内容。")}</p>
          <div className="artifact-links"><a href="/evidence/PROJECT_README.md" target="_blank" rel="noreferrer">README.md <span>↗</span></a><a href="/evidence/AI_VALUE_EVIDENCE.md" target="_blank" rel="noreferrer">AI_VALUE_EVIDENCE.md <span>↗</span></a><a href="/evidence/test_generation_report.json" target="_blank" rel="noreferrer">test_generation_report.json <span>↗</span></a><a href="/evidence/rca_report.json" target="_blank" rel="noreferrer">rca_report.json <span>↗</span></a><a href="/evidence/AUTOMOTIVE_ARCHITECTURE.md" target="_blank" rel="noreferrer">AUTOMOTIVE_ARCHITECTURE.md <span>↗</span></a></div>
        </section>
      </article>
    </div>
    <footer><div className="brand"><span>AQ</span> Quality Engineering</div><p>{tr("Readable evidence. Verifiable sources.", "易读证据，可核验来源。")}</p><small>Portfolio evidence · v2.0.0</small></footer>
  </main>;
}
