import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI 辅助测试平台 — 交互式功能原型",
  description: "可复现的数据质量验证、AI 辅助测试、人工审核、确定性执行、RCA 与质量门禁功能演示。",
  alternates: { canonical: "/zh", languages: { en: "/en", "zh-CN": "/zh" } },
  openGraph: { title: "AI 辅助测试平台 — 交互式功能原型", description: "从数据质量验证到质量门禁，体验可复现、受治理的汽车 QA 流程。" },
  twitter: { title: "AI 辅助测试平台 — 交互式功能原型", description: "从数据质量验证到质量门禁，体验可复现、受治理的汽车 QA 流程。" },
};

export default function ChineseLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
