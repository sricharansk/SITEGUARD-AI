"use client";

import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { InlineError } from "@/components/states";
import { login, safeNextPath, toApiError, type ApiError } from "@/lib/api";

export function LoginForm() {
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | undefined>();

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(undefined);
    try {
      await login(email, password);
      // Full navigation so the app shell loads fresh with the new session cookie.
      window.location.assign(safeNextPath(params.get("next")));
    } catch (err) {
      setError(toApiError(err));
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate={false} className="space-y-3">
      <div>
        <label htmlFor="email" className="field-label">
          Work email
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          required
          className="input"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div>
        <label htmlFor="password" className="field-label">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          className="input"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      <button type="submit" className="btn-primary w-full" disabled={pending}>
        {pending ? "Signing in…" : "Sign in"}
      </button>
      <InlineError error={error} />
    </form>
  );
}
