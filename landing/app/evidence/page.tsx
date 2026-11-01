import type { Metadata } from "next";
import EvidencePage from "../EvidencePage";

export const metadata: Metadata = {
  title: "Project Evidence | Automotive AI Quality Engineering",
  description: "Readable project evidence covering measured AI results, architecture, limitations, reproducibility, and source artifacts.",
};

export default function Evidence() {
  return <EvidencePage language="en" />;
}
