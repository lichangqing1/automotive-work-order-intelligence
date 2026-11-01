import type { Metadata } from "next";
import EvidencePage from "../../EvidencePage";

export const metadata: Metadata = {
  title: "项目证据 | 汽车工单 AI 质量工程平台",
  description: "以适合浏览器阅读的方式展示 AI 量化结果、系统架构、局限、可复现性与源文件。",
  alternates: { canonical: "/zh/evidence", languages: { en: "/en/evidence", "zh-CN": "/zh/evidence" } },
};

export default function ChineseEvidence() {
  return <EvidencePage language="zh" />;
}
