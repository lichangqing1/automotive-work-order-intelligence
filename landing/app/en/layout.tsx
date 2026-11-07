import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI-Assisted Testing Platform — Interactive Prototype",
  description: "A functional, reproducible demo of data-quality validation, AI-assisted testing, human review, deterministic execution, RCA, and quality gates.",
  alternates: { canonical: "/en", languages: { en: "/en", "zh-CN": "/zh" } },
  openGraph: { title: "AI-Assisted Testing Platform — Interactive Prototype", description: "Run a reproducible, governed automotive QA workflow from data validation through quality gates." },
  twitter: { title: "AI-Assisted Testing Platform — Interactive Prototype", description: "Run a reproducible, governed automotive QA workflow from data validation through quality gates." },
};

export default function EnglishLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
