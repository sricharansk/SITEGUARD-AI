import type { Metadata } from "next";
import { Suspense } from "react";
import { HardHatIcon } from "@/components/icons";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-900 px-4 py-10">
      <main className="w-full max-w-sm">
        <div className="mb-5 flex items-center gap-3 text-white">
          <span className="flex h-10 w-10 items-center justify-center rounded bg-brand-400 text-slate-900">
            <HardHatIcon size={24} />
          </span>
          <div>
            <h1 className="text-lg font-bold text-white">Site Guard AI</h1>
            <p className="text-xs text-slate-300">Construction safety &amp; quality decision support</p>
          </div>
        </div>
        <div className="card border-t-4 border-t-brand-400">
          <div className="card-body">
            <h2 className="mb-3 text-base font-semibold">Sign in</h2>
            <Suspense fallback={null}>
              <LoginForm />
            </Suspense>
          </div>
        </div>
        <p className="mt-4 text-xs leading-relaxed text-slate-400">
          AI output in Site Guard AI is decision support and must be reviewed by a competent person. In an emergency,
          follow your site emergency procedure first.
        </p>
      </main>
    </div>
  );
}
