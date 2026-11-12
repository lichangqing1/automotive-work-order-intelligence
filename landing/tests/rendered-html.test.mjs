import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render(path = "/") {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request(`http://localhost${path}`, { headers: { accept: "text/html", host: "localhost" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the functional prototype overview", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>AI-Assisted Testing Platform — Interactive Prototype<\/title>/i);
  assert.match(html, /Automotive Work Order/);
  assert.match(html, /Data Quality &amp; AI-Assisted/);
  assert.match(html, /Start interactive demo/i);
  assert.match(html, /DEMO MODE/);
  assert.match(html, /30,000/);
  assert.match(html, /1,200/);
  assert.match(html, /Human-effort reduction/i);
  assert.match(html, />BLOCK</);
  assert.match(html, /AI never decides test PASS \/ FAIL/i);
});

test("keeps evidence links and avoids inflated claims", async () => {
  const page = await readFile(new URL("../app/LandingPage.tsx", import.meta.url), "utf8");
  const evidencePage = await readFile(new URL("../app/EvidencePage.tsx", import.meta.url), "utf8");
  const requiredEvidence = [
    "/evidence/AI_VALUE_EVIDENCE.md",
    "/evidence/test_generation_report.json",
    "/evidence/rca_report.json",
    "/evidence/AUTOMOTIVE_ARCHITECTURE.md",
  ];
  for (const href of requiredEvidence) assert.match(evidencePage, new RegExp(href.replaceAll("/", "\\/")));
  assert.match(page, /View measured evidence/);
  assert.equal(page.match(/href=\{t\("\/en\/evidence","\/zh\/evidence"\)\}/g)?.length, 2);
  assert.doesNotMatch(page, /href="\/evidence\/[^"]+\.(md|json)"/i);
  assert.doesNotMatch(page, /100% accuracy|enterprise-grade|approved for autonomous/i);
  assert.doesNotMatch(page, /SkeletonPreview|react-loading-skeleton|codex-preview/);
});

test("renders readable bilingual evidence hubs with navigation and source artifacts", async () => {
  const englishResponse = await render("/en/evidence");
  const chineseResponse = await render("/zh/evidence");
  assert.equal(englishResponse.status, 200);
  assert.equal(chineseResponse.status, 200);

  const english = await englishResponse.text();
  const chinese = await chineseResponse.text();
  assert.match(english, /Evidence, made/);
  assert.match(english, /On this page/);
  assert.match(english, /Publication-complete does not mean production-approved/);
  assert.match(english, /Need the machine-readable evidence/);
  assert.match(english, /13\.33% evidence support/);
  assert.match(english, /76\.67% unsupported claims/);
  assert.match(english, /historical provenance/);
  assert.match(chinese, /让证据更易于/);
  assert.match(chinese, /本页目录/);
  assert.match(chinese, /证据完整，不等于可自主上线/);
  assert.match(chinese, /需要查看机器可读证据/);
  assert.match(chinese, /证据支持率 13\.33%/);
  assert.match(chinese, /无依据结论率 76\.67%/);
  assert.match(chinese, /href="\/en\/evidence"/);
  for (const anchor of ["project-guide", "ai-value", "test-generation", "rca", "architecture", "reproducibility", "source-artifacts"]){
    assert.match(english, new RegExp(`id="${anchor}"`));
    assert.match(chinese, new RegExp(`id="${anchor}"`));
  }
});

test("supports a configured public repository without hard-coding a stale URL", async () => {
  const page = await readFile(new URL("../app/LandingPage.tsx", import.meta.url), "utf8");
  assert.match(page, /NEXT_PUBLIC_GITHUB_URL/);
  assert.match(page, /GitHub/);
  assert.doesNotMatch(page, /github\.com\/your-account/);
});

test("renders stable English and Chinese routes from one evidence source", async () => {
  const englishResponse = await render("/en");
  const chineseResponse = await render("/zh");
  assert.equal(englishResponse.status, 200);
  assert.equal(chineseResponse.status, 200);

  const english = await englishResponse.text();
  const chinese = await chineseResponse.text();
  assert.match(english, /<html[^>]*lang="en"/i);
  assert.match(chinese, /<html[^>]*lang="zh-CN"/i);
  assert.match(english, /FUNCTIONAL PROTOTYPE/i);
  assert.match(chinese, /功能原型/);
  assert.match(chinese, /AI 不直接决定测试通过或失败/);
  assert.match(chinese, /BLOCK[\s\S]*?当前 AI 质量门禁/);
  assert.match(english, /href="\/zh"/);
  assert.match(chinese, /href="\/en"/);
  assert.match(english, /href="\/en\/evidence"/);
  assert.match(chinese, /href="\/zh\/evidence"/);

  for (const value of ["30,000", "1,200", "48.98%"]){
    const pattern = new RegExp(value.replace(".", "\\."));
    assert.match(english, pattern);
    assert.match(chinese, pattern);
  }
});

test("implements the complete governed demo workflow", async () => {
  const page = await readFile(new URL("../app/LandingPage.tsx", import.meta.url), "utf8");
  for (const feature of [
    "Run DQ validation", "Generate test cases", "Human Review", "Approve",
    "Run test", "Generate AI RCA", "CURRENT RELEASE DECISION", "LIVE TRACE",
  ]) assert.match(page, new RegExp(feature, "i"));
  assert.match(page, /AIRUN-017-03/);
  assert.match(page, /RESULT-842/);
  assert.match(page, /AI never decides test PASS \/ FAIL/);
});

test("declares the correct document language on bilingual evidence routes", async () => {
  const english = await (await render("/en/evidence")).text();
  const chinese = await (await render("/zh/evidence")).text();
  assert.match(english, /<html[^>]*lang="en"/i);
  assert.match(chinese, /<html[^>]*lang="zh-CN"/i);
});
