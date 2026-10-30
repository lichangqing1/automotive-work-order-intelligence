import Image from "next/image";

import metrics from "../public/project-metrics.json";

const githubUrl = process.env.NEXT_PUBLIC_GITHUB_URL ?? "https://github.com/lichangqing1/automotive-work-order-intelligence";

const capabilities = [
  { tag: "01", title: "Data quality", items: ["Configurable DQ rules", "Cross-table validation", "Source–target reconciliation", "Controlled defect injection", "Dataset versioning"] },
  { tag: "02", title: "Test engineering", items: ["Requirement-driven tests", "Persistent test versions", "Deterministic execution", "Result evidence", "Automated regression"] },
  { tag: "03", title: "AI for testing", items: ["Requirement analysis", "Test generation", "RCA assistance", "Prompt/model audit trail", "Human approval"] },
  { tag: "04", title: "Platform workflow", items: ["PostgreSQL + Alembic", "FastAPI services", "Jira integration", "CI and testing", "End-to-end traceability"] },
];

const architecture = [
  ["Jira", "Requirement"], ["Versioned", "Requirement"], ["AI-assisted", "Test design"],
  ["Human", "Review"], ["Deterministic", "Execution"], ["Evidence-rich", "Test result"],
  ["AI-assisted", "RCA"], ["Jira", "Defect"], ["Policy", "Quality gates"],
];

const workflow = ["Jira requirement", "AI analysis", "Test generation", "Schema validation", "Human review", "Approved test", "Deterministic run", "RCA + Jira evidence"];

function pct(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}

export default function Home() {
  return (
    <main>
      <nav className="nav" aria-label="Primary navigation">
        <a className="brand" href="#top" aria-label="Automotive Quality Engineering home"><span>AQ</span> Quality Engineering</a>
        <div className="nav-links">
          <a href="#architecture">Architecture</a><a href="#ai-value">Evidence</a><a href="#contribution">Contribution</a>
        </div>
      </nav>

      <section className="hero section" id="top">
        <div className="hero-copy">
          <p className="eyebrow">PORTFOLIO CASE STUDY · QA / TEST DEVELOPMENT</p>
          <h1>Automotive Work Order<br/><em>AI Quality Engineering</em> Platform</h1>
          <p className="lede">A production-shaped QA platform combining automotive data-quality validation, deterministic test automation, AI-assisted test design and RCA, Jira-based human review, and measured AI quality evaluation.</p>
          <div className="actions">
            {githubUrl && <a className="button primary" href={githubUrl} target="_blank" rel="noreferrer">View source on GitHub <span>↗</span></a>}
            <a className="button primary" href="/evidence/AI_VALUE_EVIDENCE.md" target="_blank" rel="noreferrer">View evaluation evidence <span>↗</span></a>
            <a className="button secondary" href="#architecture">Explore architecture</a>
          </div>
          <p className="hero-note"><span className="pulse"/> AI proposes. Deterministic controls and people decide.</p>
        </div>
        <div className="hero-panel" aria-label="Project headline metrics">
          <div className="panel-label"><span>CONTROLLED BENCHMARK</span><span>v2.0.0</span></div>
          <div className="hero-metrics">
            <article><strong>{metrics.benchmark.workOrders.toLocaleString()}</strong><span>synthetic work orders</span></article>
            <article><strong>{metrics.benchmark.injectedDefects.toLocaleString()}</strong><span>injected defect rows</span></article>
            <article className="wide"><strong>{metrics.benchmark.detectedDefects.toLocaleString()} / {metrics.benchmark.injectedDefects.toLocaleString()}</strong><span>deliberately injected rows detected</span></article>
            <article><strong>{metrics.benchmark.aiEvaluationCases}</strong><span>curated AI cases</span></article>
            <article><strong>{metrics.testGeneration.runs}×</strong><span>real-provider runs</span></article>
          </div>
          <div className="signal-line"><span>DQ</span><i/><span>TEST</span><i/><span>REVIEW</span><i/><span>GATE</span></div>
        </div>
      </section>

      <section className="problem section ruled">
        <div><p className="section-index">01 / THE PROBLEM</p><h2>Operational data fails<br/>in connected ways.</h2></div>
        <div className="problem-copy">
          <p>Automotive work-order platforms combine API data, relational records, OTA versions, diagnostic events, state transitions, timestamps, and downstream workflows.</p>
          <p>Quality failures surface as missing data, invalid transitions, cross-table inconsistencies, unsupported software versions, and temporal defects. This project explores where AI can assist—without making the LLM the final authority.</p>
        </div>
      </section>

      <section className="section" id="capabilities">
        <header className="section-heading"><p className="section-index">02 / WHAT I BUILT</p><h2>One platform. Four engineering disciplines.</h2><p>Built as a cohesive quality system rather than a collection of disconnected demos.</p></header>
        <div className="capability-grid">
          {capabilities.map((capability) => <article className="capability" key={capability.title}><span className="cap-tag">{capability.tag}</span><h3>{capability.title}</h3><ul>{capability.items.map(item => <li key={item}>{item}</li>)}</ul></article>)}
        </div>
      </section>

      <section className="section dark" id="architecture">
        <header className="section-heading inverse"><p className="section-index">03 / SYSTEM ARCHITECTURE</p><h2>Traceability from requirement<br/>to release decision.</h2></header>
        <div className="architecture" aria-label="System architecture flow">
          {architecture.map((node, index) => <div className="arch-wrap" key={node.join("-")}><article className={index === architecture.length - 1 ? "arch-node gate-node" : "arch-node"}><span>{String(index + 1).padStart(2, "0")}</span><strong>{node[0]}</strong><small>{node[1]}</small></article>{index < architecture.length - 1 && <b aria-hidden="true">→</b>}</div>)}
        </div>
        <p className="authority-rule"><span>CONTROL BOUNDARY</span> AI proposes and assists; Python, SQL, assertions, human review, and quality policies retain authority over execution and release decisions.</p>
      </section>

      <section className="section benchmark">
        <div className="benchmark-copy"><p className="section-index">04 / CONTROLLED DATA QUALITY</p><h2>Known defects in.<br/>Evidence out.</h2><p>All <strong>{metrics.benchmark.injectedDefects.toLocaleString()}</strong> deliberately injected defect rows were detected in the controlled <strong>{metrics.benchmark.workOrders.toLocaleString()}-record</strong> synthetic benchmark.</p><div className="checks">{metrics.benchmark.checks.map(check => <span key={check}>{check}</span>)}</div></div>
        <div className="benchmark-visual"><div className="ring"><div><strong>{metrics.benchmark.detectedDefects.toLocaleString()}</strong><span>detected</span></div></div><div className="benchmark-foot"><span><b>{metrics.benchmark.falseNegatives}</b> missed</span><span><b>{metrics.benchmark.falsePositives}</b> false positives</span></div><p>Controlled benchmark result—not a claim of universal accuracy.</p></div>
      </section>

      <section className="section workflow-section">
        <header className="section-heading"><p className="section-index">05 / AI-ASSISTED WORKFLOW</p><h2>Useful automation.<br/>Explicit human control.</h2></header>
        <div className="workflow">{workflow.map((step, index) => <div className="workflow-step" key={step}><span>{String(index + 1).padStart(2, "0")}</span><strong>{step}</strong>{index < workflow.length - 1 && <b>↓</b>}</div>)}</div>
        <div className="never-rule"><span>NON-NEGOTIABLE</span><strong>AI never decides test PASS / FAIL.</strong><p>Approved tests execute through deterministic assertions and evidence-producing services.</p></div>
      </section>

      <section className="section evidence" id="ai-value">
        <header className="section-heading"><p className="section-index">06 / MEASURED AI VALUE</p><h2>Measured gains.<br/>Measured regressions.</h2><p>Three real-provider runs per experiment, complete human review, versioned inputs, and policy-based release gates.</p></header>
        <div className="evidence-grid">
          <article className="evidence-card">
            <div className="evidence-title"><span>TEST GENERATION</span><b className="status blocked">BLOCK</b></div>
            <h3>AI improved the baseline—not human-only quality.</h3>
            <div className="metric-table"><div className="table-head"><span>Metric</span><span>Deterministic</span><span>AI-assisted</span></div>{metrics.testGeneration.coverage.map(row => <div className="table-row" key={row.label}><span>{row.label}</span><span>{pct(row.baseline)}</span><strong>{pct(row.ai)}</strong></div>)}</div>
            <div className="callout-row"><div className="positive"><span>Human effort saved</span><strong>{pct(metrics.testGeneration.humanEffortSaving)}</strong></div><div className="warning"><span>AI rejection rate</span><strong>{pct(metrics.testGeneration.rejectionRate)}</strong></div></div>
            <div className="comparison-note"><span>Human-only coverage <b>{pct(metrics.testGeneration.humanOnlyCoverage)}</b></span><span>AI-assisted <b>{pct(metrics.testGeneration.aiCoverage)}</b></span></div>
          </article>

          <article className="evidence-card rca-card">
            <div className="evidence-title"><span>ROOT-CAUSE ANALYSIS</span><b className="status blocked">BLOCK</b></div>
            <h3>Faster investigation—not autonomous diagnosis.</h3>
            <div className="time-shift"><div><span>Deterministic</span><strong>{metrics.rca.baselineSeconds.toFixed(2)} s</strong></div><b>→</b><div><span>AI-assisted</span><strong>{metrics.rca.aiSeconds.toFixed(2)} s</strong></div></div>
            <div className="rca-metrics"><div><span>Recommended-check usefulness</span><strong>{pct(metrics.rca.checkUsefulness)}</strong><i className="good-bar" style={{"--value": `${metrics.rca.checkUsefulness * 100}%`} as React.CSSProperties}/></div><div><span>Evidence support</span><strong>{pct(metrics.rca.evidenceSupport)}</strong><i className="good-bar" style={{"--value": `${metrics.rca.evidenceSupport * 100}%`} as React.CSSProperties}/></div><div className="failed-metric"><span>Root-cause accuracy</span><strong>{pct(metrics.rca.rootCauseAccuracy)} — failed threshold</strong><i className="bad-bar"/><small>Quality regression</small></div><div className="failed-metric"><span>Failure-class accuracy</span><strong>{pct(metrics.rca.failureClassAccuracy)} — failed threshold</strong><i className="bad-bar"/><small>Quality regression</small></div></div>
            <p className="card-conclusion">Useful as an <strong>investigation assistant</strong>; not reliable enough to operate as an autonomous diagnosis engine.</p>
          </article>
        </div>
      </section>

      <section className="section gates">
        <div className="gate-intro"><p className="section-index">07 / QUALITY GATES</p><h2>The system knows<br/>when to say no.</h2><p>Both configurations produced measurable benefits, but failed predefined thresholds. The platform blocks autonomous promotion rather than averaging failures away.</p></div>
        <div className="gate-cards"><article><span>TEST GENERATION</span><strong>BLOCK</strong><p>Coverage, unsupported assumptions, and approval thresholds failed.</p></article><article><span>ROOT-CAUSE ANALYSIS</span><strong>BLOCK</strong><p>Accuracy, abstention, and unsupported-claim thresholds failed.</p></article></div>
      </section>

      <section className="section contribution" id="contribution">
        <div><p className="section-index">08 / MY CONTRIBUTION</p><h2>Designed and built<br/>end to end.</h2></div>
        <div><p>Independently designed and implemented the platform architecture, PostgreSQL data model, configurable DQ framework, SQL validation, automated test workflow, FastAPI services, Jira integration, AI provider abstraction, human-review path, RCA pipeline, evaluation framework, quality policies, and controlled benchmark experiments.</p><div className="stack">{metrics.technology.map(item => <span key={item}>{item}</span>)}</div></div>
      </section>

      <section className="section product-evidence" id="product-evidence">
        <header className="section-heading"><p className="section-index">09 / SELECTED SYSTEM EVIDENCE</p><h2>Implemented workflows,<br/>not presentation mockups.</h2><p>Authentic captures from the FastAPI-backed Streamlit engineering console using the project’s local runtime and committed evaluation evidence.</p></header>
        <div className="screenshot-grid">
          <figure><a href="/screenshots/engineering-overview.png" target="_blank" rel="noreferrer"><Image src="/screenshots/engineering-overview.png" width={1280} height={720} sizes="(max-width: 640px) 100vw, 50vw" alt="Engineering console overview with work-order metrics"/></a><figcaption><span>01</span><strong>Engineering overview</strong><small>Live work-order and backlog metrics</small></figcaption></figure>
          <figure><a href="/screenshots/test-runs.png" target="_blank" rel="noreferrer"><Image src="/screenshots/test-runs.png" width={1280} height={720} sizes="(max-width: 640px) 100vw, 50vw" alt="Persistent test run records in the engineering console"/></a><figcaption><span>02</span><strong>Test execution records</strong><small>Persistent deterministic run evidence</small></figcaption></figure>
          <figure><a href="/screenshots/case-retrieval.png" target="_blank" rel="noreferrer"><Image src="/screenshots/case-retrieval.png" width={1280} height={720} sizes="(max-width: 640px) 100vw, 50vw" alt="Authoritative case evidence retrieval interface"/></a><figcaption><span>03</span><strong>Evidence retrieval</strong><small>Dataset-bound historical case search</small></figcaption></figure>
          <figure><a href="/screenshots/ai-value-gates.png" target="_blank" rel="noreferrer"><Image src="/screenshots/ai-value-gates.png" width={1280} height={720} sizes="(max-width: 640px) 100vw, 50vw" alt="AI value dashboard with BLOCK quality gate results"/></a><figcaption><span>04</span><strong>AI value and gates</strong><small>Measured gains, failures, and BLOCK decisions</small></figcaption></figure>
        </div>
      </section>

      <section className="section evidence-links" id="evidence">
        <header><p className="section-index">10 / EVIDENCE</p><h2>Inspect the files,<br/>not just the claims.</h2></header>
        <div className="link-grid">{githubUrl && <a href={githubUrl} target="_blank" rel="noreferrer"><span>00</span><strong>GitHub source</strong><small>Browse the implementation and test suite</small><b>↗</b></a>}<a href="/evidence/PROJECT_README.md" target="_blank" rel="noreferrer"><span>01</span><strong>Repository guide</strong><small>Project scope, setup, and implementation</small><b>↗</b></a><a href="/evidence/AI_VALUE_EVIDENCE.md" target="_blank" rel="noreferrer"><span>02</span><strong>AI evaluation evidence</strong><small>Design, limitations, and reproducibility</small><b>↗</b></a><a href="/evidence/test_generation_report.json" target="_blank" rel="noreferrer"><span>03</span><strong>Test-generation report</strong><small>Sanitized measured results</small><b>↗</b></a><a href="/evidence/rca_report.json" target="_blank" rel="noreferrer"><span>04</span><strong>RCA report</strong><small>Accuracy, support, and policy results</small><b>↗</b></a><a href="/evidence/AUTOMOTIVE_ARCHITECTURE.md" target="_blank" rel="noreferrer"><span>05</span><strong>Architecture document</strong><small>Runtime and system boundaries</small><b>↗</b></a><a href="#product-evidence"><span>06</span><strong>Workflow captures</strong><small>Selected implemented product evidence</small><b>↑</b></a></div>
      </section>

      <footer><div className="brand"><span>AQ</span> Quality Engineering</div><p>Measured evidence over marketing claims.</p><small>Automotive Work Order Intelligence · Portfolio release v2.0.0</small></footer>
    </main>
  );
}
