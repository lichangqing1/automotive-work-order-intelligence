import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "汽车工单 AI 质量工程平台",
  description: "一个采用确定性执行、Jira 可追溯链路、完整人工审核和明确 AI 质量门禁的汽车 QA 平台。",
  alternates: { canonical: "/zh", languages: { en: "/en", "zh-CN": "/zh" } },
  openGraph: { title: "汽车工单 AI 质量工程平台", description: "在包含完整人工审核的汽车 QA 流程中，量化 AI 收益、退化与质量门禁结果。" },
  twitter: { title: "汽车工单 AI 质量工程平台", description: "在包含完整人工审核的汽车 QA 流程中，量化 AI 收益、退化与质量门禁结果。" },
};

export default function ChineseLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
