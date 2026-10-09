"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { login } from "@/lib/api";
import { ErrorBox } from "@/components/ui";

const DEMO = ["hse", "pm", "safety", "qa", "site", "auditor"];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("hse@demo.siteguard.local");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      router.replace("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
      <h1 className="text-2xl font-bold text-brand-dark">Site Guard AI</h1>
      <p className="mb-6 text-sm text-ink-soft">Construction safety and quality incident resolution</p>
      <form onSubmit={submit} className="space-y-4 rounded-lg border border-surface-line bg-surface p-5 shadow-sm">
        {error && <ErrorBox message={error} />}
        <label className="block text-sm font-medium">
          Email
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username"
            className="mt-1 w-full rounded border border-surface-line px-3 py-2" />
        </label>
        <label className="block text-sm font-medium">
          Password
          <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password"
            className="mt-1 w-full rounded border border-surface-line px-3 py-2" />
        </label>
        <button disabled={busy} className="w-full rounded bg-brand px-4 py-2 font-semibold text-white hover:bg-brand-dark disabled:opacity-60">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="mt-4 text-xs text-ink-soft">
        Pilot demo data is synthetic. Demo accounts: {DEMO.map((d) => `${d}@demo.siteguard.local`).join(", ")}. See the README for the demo password.
      </p>
    </main>
  );
}
