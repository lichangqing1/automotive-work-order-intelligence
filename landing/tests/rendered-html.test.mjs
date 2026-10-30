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

test("server-renders the recruiter evidence page", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<title>Automotive AI Quality Engineering Platform<\/title>/i);
  assert.match(html, /Automotive Work Order/);
  assert.match(html, /AI Quality Engineering/);
  assert.match(html, /30,000/);
  assert.match(html, /1,200/);
  assert.match(html, /Measured AI Value/i);
  assert.match(html, /Human effort saved/i);
  assert.match(html, />BLOCK</);
  assert.match(html, /AI never decides test PASS \/ FAIL/i);
});

test("links to real evidence and avoids inflated claims", async () => {
  const page = await readFile(new URL("../app/LandingPage.tsx", import.meta.url), "utf8");
  const requiredEvidence = [
    "/evidence/AI_VALUE_EVIDENCE.md",
    "/evidence/test_generation_report.json",
    "/evidence/rca_report.json",
    "/evidence/AUTOMOTIVE_ARCHITECTURE.md",
  ];
  for (const href of requiredEvidence) assert.match(page, new RegExp(href.replaceAll("/", "\\/")));
  assert.match(page, /\/screenshots\/ai-value-gates\.png/);
  assert.doesNotMatch(page, /100% accuracy|enterprise-grade|approved for autonomous/i);
  assert.doesNotMatch(page, /SkeletonPreview|react-loading-skeleton|codex-preview/);
});

test("supports a configured public repository without hard-coding a stale URL", async () => {
  const page = await readFile(new URL("../app/LandingPage.tsx", import.meta.url), "utf8");
  assert.match(page, /NEXT_PUBLIC_GITHUB_URL/);
  assert.match(page, /View source on GitHub/);
  assert.doesNotMatch(page, /github\.com\/your-account/);
});

test("renders stable English and Chinese routes from one evidence source", async () => {
  const englishResponse = await render("/en");
  const chineseResponse = await render("/zh");
  assert.equal(englishResponse.status, 200);
  assert.equal(chineseResponse.status, 200);

  const english = await englishResponse.text();
  const chinese = await chineseResponse.text();
  assert.match(english, /Measured AI Value/i);
  assert.match(chinese, /量化 AI 价值/);
  assert.match(chinese, /AI 不直接决定测试通过或失败/);
  assert.match(chinese, /BLOCK[\s\S]*?阻断/);
  assert.match(english, /href="\/zh"/);
  assert.match(chinese, /href="\/en"/);

  for (const value of ["30,000", "1,200", "48.98%", "60.42%", "75.56%", "94.52%"]){
    const pattern = new RegExp(value.replace(".", "\\."));
    assert.match(english, pattern);
    assert.match(chinese, pattern);
  }
});
