import type { Metadata } from "next";
import Shell from "@/components/Shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Site Guard AI",
  description: "Multi-Agent Construction Safety & Quality Incident Resolution System — decision support and workflow.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
