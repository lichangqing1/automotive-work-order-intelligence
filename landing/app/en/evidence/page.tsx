import type { Metadata } from "next";
import EvidencePage from "../../EvidencePage";

export const metadata: Metadata = {
  title: "Project Evidence | Automotive AI Quality Engineering",
  description: "Readable project evidence covering measured AI results, architecture, limitations, reproducibility, and source artifacts.",
  alternates: { canonical: "/en/evidence", languages: { en: "/en/evidence", "zh-CN": "/zh/evidence" } },
};

export default function EnglishEvidence() {
  return <EvidencePage language="en" />;
}
