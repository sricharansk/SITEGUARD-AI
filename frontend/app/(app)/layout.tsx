import type { ReactNode } from "react";
import { AppProvider } from "@/components/app-context";
import { AppShell } from "@/components/app-shell";

export default function AuthenticatedLayout({ children }: { children: ReactNode }) {
  return (
    <AppProvider>
      <AppShell>{children}</AppShell>
    </AppProvider>
  );
}
