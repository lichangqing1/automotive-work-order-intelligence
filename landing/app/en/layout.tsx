import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Automotive AI Quality Engineering Platform",
  description: "A measured, human-reviewed automotive QA platform with deterministic execution, Jira traceability, and explicit AI quality gates.",
  alternates: { canonical: "/en", languages: { en: "/en", "zh-CN": "/zh" } },
  openGraph: { title: "Automotive AI Quality Engineering Platform", description: "Measured AI gains, regressions, and quality gates in a human-reviewed automotive QA workflow." },
  twitter: { title: "Automotive AI Quality Engineering Platform", description: "Measured AI gains, regressions, and quality gates in a human-reviewed automotive QA workflow." },
};

export default function EnglishLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
