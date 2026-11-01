import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("host") ?? "localhost:3000";
  const protocol = host.startsWith("localhost") ? "http" : "https";
  const image = `${protocol}://${host}/og.png`;
  const title = "Automotive AI Quality Engineering Platform";
  const description = "A measured, human-reviewed automotive QA platform with deterministic execution, Jira traceability, and explicit AI quality gates.";
  return {
    title, description,
    icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
    openGraph: { title, description, images: [{ url: image, width: 1728, height: 909 }] },
    twitter: { card: "summary_large_image", title, description, images: [image] },
  };
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <LocalizedDocument>{children}</LocalizedDocument>;
}

async function LocalizedDocument({ children }: Readonly<{ children: React.ReactNode }>) {
  const requestHeaders = await headers();
  const language = requestHeaders.get("x-page-language") === "zh-CN" ? "zh-CN" : "en";
  return <html lang={language}><body>{children}</body></html>;
}
