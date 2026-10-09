// Shared screen states (docs/DESIGN_SYSTEM.md "State rules"): loading, empty, error, partial result,
// success and unauthorized. Errors always show the API message and correlation ID.
import type { ReactNode } from "react";
import type { ApiError } from "@/lib/api";
import { AlertIcon, CheckIcon, InfoIcon, LockIcon, SpinnerIcon } from "./icons";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-2 px-4 py-6 text-slate-600">
      <SpinnerIcon size={16} />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 px-4 py-6">
      <p className="font-semibold text-slate-800">{title}</p>
      {children ? <div className="text-slate-600">{children}</div> : null}
      {action}
    </div>
  );
}

export function CorrelationId({ id }: { id: string | null | undefined }) {
  if (!id) return null;
  return (
    <p className="mt-1 text-xs text-slate-600">
      Correlation ID: <code className="mono rounded bg-white/70 px-1 select-all">{id}</code>
    </p>
  );
}

export function UnauthorizedState({ error, what = "this" }: { error?: ApiError; what?: string }) {
  return (
    <div role="alert" className="m-4 flex gap-3 rounded border border-slate-300 bg-slate-50 p-4" data-state="unauthorized">
      <LockIcon size={18} className="mt-0.5 shrink-0 text-slate-600" />
      <div>
        <p className="font-semibold text-slate-900">Not authorized</p>
        <p className="text-slate-700">
          Your role does not allow you to view or change {what}. Ask an administrator if you need access.
        </p>
        {error ? <p className="mt-1 text-xs text-slate-600">Server message: {error.message}</p> : null}
        <CorrelationId id={error?.correlationId} />
      </div>
    </div>
  );
}

export function ErrorState({ error, onRetry, what }: { error: ApiError; onRetry?: () => void; what?: string }) {
  if (error.isForbidden) return <UnauthorizedState error={error} what={what} />;
  const title = error.isNotFound
    ? "Not found"
    : error.isUnauthenticated
      ? "Your session has ended"
      : "Something went wrong";
  const hint = error.isNotFound
    ? "It does not exist or is outside the projects you can access."
    : error.isUnauthenticated
      ? "Sign in again to continue."
      : null;
  return (
    <div role="alert" className="m-4 flex gap-3 rounded border border-red-300 bg-red-50 p-4" data-state="error">
      <AlertIcon size={18} className="mt-0.5 shrink-0 text-red-700" />
      <div className="min-w-0">
        <p className="font-semibold text-red-900">{title}</p>
        <p className="text-red-900">{error.message}</p>
        {hint ? <p className="text-sm text-red-800">{hint}</p> : null}
        <p className="mt-1 text-xs text-red-800">Code: {error.code}</p>
        <CorrelationId id={error.correlationId} />
        {onRetry && !error.isNotFound ? (
          <button type="button" className="btn-secondary btn-sm mt-2" onClick={onRetry}>
            Try again
          </button>
        ) : null}
      </div>
    </div>
  );
}

/** Inline error for a form or action; keeps the user's input in place. */
export function InlineError({ error }: { error: ApiError | undefined }) {
  if (!error) return null;
  return (
    <div role="alert" className="mt-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900">
      <p className="font-medium">
        {error.isForbidden ? "Not authorized: " : ""}
        {error.message}
      </p>
      <p className="text-xs text-red-800">
        Code: {error.code}
        {error.correlationId ? (
          <>
            {" "}
            · Correlation ID: <code className="mono select-all">{error.correlationId}</code>
          </>
        ) : null}
      </p>
    </div>
  );
}

export function SuccessNote({ message }: { message: string | null }) {
  return (
    <div role="status" aria-live="polite">
      {message ? (
        <p className="mt-2 inline-flex items-center gap-1 rounded border border-emerald-300 bg-emerald-50 px-2 py-1 text-sm text-emerald-900">
          <CheckIcon size={14} /> {message}
        </p>
      ) : null}
    </div>
  );
}

/** Some of the screen loaded and some did not: say what is missing instead of hiding it. */
export function PartialNotice({ title = "Partial result", items }: { title?: string; items: ReactNode[] }) {
  if (items.length === 0) return null;
  return (
    <div role="status" className="flex gap-2 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950" data-state="partial">
      <InfoIcon size={16} className="mt-0.5 shrink-0" />
      <div>
        <p className="font-semibold">{title}</p>
        <ul className="list-disc pl-5">
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
