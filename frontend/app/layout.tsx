import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Site Guard AI", template: "%s · Site Guard AI" },
  description: "Agentic AI-powered Construction Safety & Quality Decision-Support and Workflow Platform",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
