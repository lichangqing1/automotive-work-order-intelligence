import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html", host: "localhost" } }),
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
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
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
  const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /NEXT_PUBLIC_GITHUB_URL/);
  assert.match(page, /View source on GitHub/);
  assert.doesNotMatch(page, /github\.com\/your-account/);
});
