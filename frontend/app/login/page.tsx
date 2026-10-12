"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api, setToken } from "@/lib/api";
import { Button, ErrorBanner, Field, inputCls } from "@/components/ui";

const DEMO = ["hse", "pm", "safety", "qa", "site", "auditor", "admin"];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("hse@demo.siteguard.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ access_token: string }>("/auth/login", { email, password });
      setToken(r.access_token);
      router.replace("/");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md rounded-xl border border-line bg-surface p-6">
        <div className="mb-5 flex items-center gap-2">
          <span aria-hidden className="inline-flex h-9 w-9 items-center justify-center rounded bg-accent font-semibold text-accent-ink">SG</span>
          <div>
            <h1 className="text-lg font-semibold">Site Guard AI</h1>
            <p className="text-xs text-ink-2">Multi-Agent Construction Safety &amp; Quality Incident Resolution System</p>
          </div>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Email">
            <input className={inputCls} type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </Field>
          <Field label="Password">
            <input className={inputCls} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </Field>
          <ErrorBanner error={error} />
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <div className="mt-5 border-t border-line pt-3 text-xs text-ink-2">
          <p className="mb-1">Demo accounts (synthetic data; password set by SITEGUARD_DEMO_PASSWORD):</p>
          <div className="flex flex-wrap gap-1">
            {DEMO.map((d) => (
              <button key={d} type="button" className="rounded border border-line px-1.5 py-0.5 hover:bg-surface-2" onClick={() => setEmail(`${d}@demo.siteguard.local`)}>
                {d}@
              </button>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
