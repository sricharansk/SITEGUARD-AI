// AI output panel. Everything an agent produced is framed the same way: a dashed violet border, a visible
// "AI decision support, needs human review" label, and the provider, confidence, open questions, flags and
// cited evidence refs, so it is never mistaken for verified evidence or a human decision.
import type { ReactNode } from "react";
import { evidenceDownloadUrl } from "@/lib/api";
import { formatPercent, humanize, roleLabel } from "@/lib/format";
import type { AgentRun } from "@/lib/types";
import { Badge, RiskBadge, SeverityBadge } from "../badges";
import { AlertIcon, CheckIcon, CrossIcon, InfoIcon, SparkleIcon } from "../icons";
import { describeRef, isFallback, reviewReasons, type RefIndex } from "./refs";

export const AI_LABEL = "AI decision support, needs human review";

export const AGENT_TITLES: Record<string, string> = {
  triage: "Triage",
  safety: "Safety investigation",
  quality: "Quality investigation",
  rca: "Root cause analysis (5 Whys)",
  compliance: "Compliance evidence mapping",
  capa: "Corrective and preventive action proposals",
};

type Output = Record<string, unknown>;

const str = (o: Output, key: string): string | null => (typeof o[key] === "string" ? (o[key] as string) : null);
const num = (o: Output, key: string): number | null => (typeof o[key] === "number" ? (o[key] as number) : null);
const list = (o: Output, key: string): string[] =>
  Array.isArray(o[key]) ? (o[key] as unknown[]).filter((v): v is string => typeof v === "string") : [];
const objects = (o: Output, key: string): Output[] =>
  Array.isArray(o[key]) ? (o[key] as unknown[]).filter((v): v is Output => typeof v === "object" && v !== null) : [];

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="kicker text-violet-900/80">{label}</dt>
      <dd className="mt-0.5 text-slate-900">{children}</dd>
    </div>
  );
}

function Bullets({ items, empty = "None identified." }: { items: string[]; empty?: string }) {
  if (items.length === 0) return <span className="text-slate-500">{empty}</span>;
  return (
    <ul className="list-disc space-y-0.5 pl-5">
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  );
}

function SuggestedRisk({ o }: { o: Output }) {
  const l = num(o, "likelihood");
  const c = num(o, "consequence");
  if (l === null || c === null) return null;
  return (
    <Field label="Suggested risk inputs">
      Likelihood {l}/5 × consequence {c}/5. The band comes from the deterministic risk matrix, not the AI.
    </Field>
  );
}

function TriageBody({ o }: { o: Output }) {
  const severity = str(o, "severity_candidate");
  return (
    <dl className="grid gap-3 sm:grid-cols-2">
      <Field label="Incident class">{str(o, "incident_class") ?? "—"}</Field>
      <Field label="Suggested severity and priority">
        <span className="flex flex-wrap items-center gap-1.5">
          {severity ? <SeverityBadge severity={severity} /> : "—"}
          <Badge>{str(o, "priority") ?? "—"}</Badge>
          <span className="text-slate-600">Domain: {humanize(str(o, "domain"))}</span>
        </span>
      </Field>
      <Field label="Hazards">
        <Bullets items={list(o, "hazards")} />
      </Field>
      <Field label="Missing information">
        <Bullets items={list(o, "missing_information")} empty="Nothing flagged as missing." />
      </Field>
      <Field label="Next agents">{list(o, "recommended_next_agents").map(humanize).join(", ") || "—"}</Field>
      <Field label="Rationale">{str(o, "rationale") ?? "—"}</Field>
    </dl>
  );
}

function SafetyBody({ o }: { o: Output }) {
  return (
    <dl className="grid gap-3 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <Field label="Summary">{str(o, "summary") ?? "—"}</Field>
      </div>
      <Field label="Hazards">
        <Bullets items={list(o, "hazards")} />
      </Field>
      <Field label="Failed or missing controls">
        <Bullets items={list(o, "failed_or_missing_controls")} />
      </Field>
      <Field label="Unsafe acts">
        <Bullets items={list(o, "unsafe_acts")} />
      </Field>
      <Field label="Unsafe conditions">
        <Bullets items={list(o, "unsafe_conditions")} />
      </Field>
      <SuggestedRisk o={o} />
    </dl>
  );
}

function QualityBody({ o }: { o: Output }) {
  return (
    <dl className="grid gap-3 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <Field label="Summary">{str(o, "summary") ?? "—"}</Field>
      </div>
      <Field label="Defects">
        <Bullets items={list(o, "defects")} />
      </Field>
      <Field label="Requirement vs observed">
        <Bullets items={list(o, "requirement_vs_observed")} />
      </Field>
      <Field label="Probable stage">{humanize(str(o, "probable_stage"))}</Field>
      <Field label="Recommended tests">
        <Bullets items={list(o, "recommended_tests")} />
      </Field>
      <SuggestedRisk o={o} />
    </dl>
  );
}

function RcaBody({ o }: { o: Output }) {
  const causes = objects(o, "root_causes");
  return (
    <dl className="grid gap-3">
      <Field label="Problem statement">{str(o, "problem_statement") ?? "—"}</Field>
      <Field label={`${str(o, "method") ?? "5-WHYS"} chain`}>
        <ol className="list-decimal space-y-0.5 pl-5">
          {list(o, "whys").map((why, i) => (
            <li key={i}>{why}</li>
          ))}
        </ol>
      </Field>
      <Field label="Root-cause hypotheses">
        <ul className="space-y-1">
          {causes.map((c, i) => (
            <li key={i} className="flex flex-wrap items-baseline gap-2">
              <Badge>{humanize(str(c, "category"))}</Badge>
              <span>{str(c, "statement")}</span>
              <span className="text-xs text-slate-600">confidence {formatPercent(num(c, "confidence"))}</span>
            </li>
          ))}
        </ul>
      </Field>
      <Field label="Contributing factors">
        <Bullets items={list(o, "contributing_factors")} empty="None listed." />
      </Field>
    </dl>
  );
}

interface FindingStyle {
  text: string;
  tone: "red" | "emerald" | "slate";
  Icon: typeof CrossIcon;
}
const UNCLEAR_FINDING: FindingStyle = { text: "Unclear, check on site", tone: "slate", Icon: InfoIcon };
const FINDING_STATUS: Record<string, FindingStyle> = {
  LIKELY_NOT_MET: { text: "Possible gap", tone: "red", Icon: AlertIcon },
  LIKELY_MET: { text: "Likely met", tone: "emerald", Icon: CheckIcon },
  UNCLEAR: UNCLEAR_FINDING,
};

function ComplianceBody({ o }: { o: Output }) {
  const findings = objects(o, "findings");
  return (
    <div className="space-y-2">
      {findings.length === 0 ? (
        <p className="text-slate-600">No requirements were matched in the retrieved documents.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="table bg-white/60">
            <thead>
              <tr>
                <th scope="col">Requirement (retrieved text)</th>
                <th scope="col">Source</th>
                <th scope="col">Assessment</th>
              </tr>
            </thead>
            <tbody>
              {findings.map((f, i) => {
                const status = FINDING_STATUS[str(f, "status") ?? ""] ?? UNCLEAR_FINDING;
                const { Icon } = status;
                return (
                  <tr key={i}>
                    <td>{str(f, "requirement")}</td>
                    <td>
                      <span className="block">{str(f, "source_title")}</span>
                      <code className="mono text-slate-500">{str(f, "source_ref")}</code>
                    </td>
                    <td>
                      <Badge tone={status.tone} icon={<Icon size={12} />}>
                        {status.text}
                      </Badge>
                      <p className="mt-1 text-xs text-slate-600">{str(f, "note")}</p>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-slate-700 italic">{str(o, "disclaimer")}</p>
    </div>
  );
}

function CapaBody({ o }: { o: Output }) {
  const actions = objects(o, "actions");
  return (
    <div>
      <p className="mb-2 text-slate-700">
        {actions.length} proposed action(s). Each one is listed under Corrective and preventive actions, where a
        reviewer approves, modifies or rejects it.
      </p>
      <ul className="space-y-1">
        {actions.map((a, i) => (
          <li key={i}>
            <span className="font-medium">{str(a, "title")}</span>{" "}
            <span className="text-slate-600">
              ({humanize(str(a, "action_type"))}, owner {roleLabel(str(a, "owner_role"))}, due in {num(a, "due_in_days")}{" "}
              days) addresses: {str(a, "addresses")}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const BODIES: Record<string, (props: { o: Output }) => ReactNode> = {
  triage: TriageBody,
  safety: SafetyBody,
  quality: QualityBody,
  rca: RcaBody,
  compliance: ComplianceBody,
  capa: CapaBody,
};

export function AiPanel({ run, refIndex }: { run: AgentRun; refIndex: RefIndex }) {
  const title = AGENT_TITLES[run.agent] ?? humanize(run.agent);
  const output = run.output ?? {};
  const confidence = num(output, "confidence");
  const lowConfidence = confidence !== null && confidence < 0.5;
  const openQuestions = list(output, "open_questions");
  const refs = list(output, "evidence_refs");
  const reasons = reviewReasons(run);
  const fallback = isFallback(run.provider);
  const failed = run.status !== "SUCCEEDED";
  const Body = BODIES[run.agent];
  const headingId = `ai-${run.id}`;

  return (
    <section
      aria-labelledby={headingId}
      data-kind="ai"
      data-agent={run.agent}
      className="rounded-md border-2 border-dashed border-violet-400 bg-violet-50/70"
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-dashed border-violet-300 px-3 py-2">
        <SparkleIcon size={14} className="text-violet-700" />
        <h3 id={headingId} className="text-sm font-semibold text-violet-950">
          <span className="sr-only">AI output:</span> {title}
        </h3>
        <span className="rounded bg-violet-700 px-1.5 py-0.5 text-[11px] font-semibold text-white">{AI_LABEL}</span>
        <span className="ml-auto flex flex-wrap items-center gap-1.5 text-xs">
          <Badge tone={fallback ? "amber" : "violet"} icon={fallback ? <AlertIcon size={12} /> : undefined}>
            {fallback ? `Fallback provider: ${run.provider}` : `Provider: ${run.provider}`}
          </Badge>
          {confidence !== null ? (
            <Badge tone={lowConfidence ? "amber" : "violet"} icon={lowConfidence ? <AlertIcon size={12} /> : undefined}>
              {`Confidence ${formatPercent(confidence)}${lowConfidence ? " (low)" : ""}`}
            </Badge>
          ) : null}
          {run.needs_human_review ? (
            <Badge tone="amber" icon={<AlertIcon size={12} />}>
              Flagged for review
            </Badge>
          ) : null}
        </span>
      </header>

      <div className="space-y-3 px-3 py-3">
        {failed ? (
          <div role="alert" className="flex gap-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-red-900">
            <CrossIcon size={16} className="mt-0.5 shrink-0" />
            <p>
              This agent failed{run.error ? ` (${run.error})` : ""}. The incident and its evidence are kept; continue
              with the manual workflow and human-authored actions.
            </p>
          </div>
        ) : Body ? (
          <Body o={output} />
        ) : (
          <pre className="mono overflow-x-auto whitespace-pre-wrap">{JSON.stringify(output, null, 2)}</pre>
        )}

        {reasons.length > 0 ? (
          <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-amber-950">
            <p className="text-xs font-semibold">Why this needs extra review</p>
            <Bullets items={reasons} />
          </div>
        ) : null}

        {!failed ? (
          <dl className="grid gap-3 border-t border-dashed border-violet-300 pt-2 sm:grid-cols-2">
            <Field label="Open questions for the investigator">
              <Bullets items={openQuestions} empty="None raised." />
            </Field>
            <Field label="Cited evidence">
              {refs.length === 0 ? (
                <span className="text-amber-900">No citations: treat this output as unsupported.</span>
              ) : (
                <ul className="space-y-0.5">
                  {refs.map((ref) => {
                    const c = describeRef(ref, refIndex);
                    return (
                      <li key={ref} className="flex flex-wrap items-baseline gap-1.5">
                        {c.evidenceId ? (
                          <a className="link" href={evidenceDownloadUrl(c.evidenceId)}>
                            {c.label}
                          </a>
                        ) : (
                          <span>{c.label}</span>
                        )}
                        <code className="mono text-slate-500">{ref}</code>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Field>
          </dl>
        ) : null}
      </div>
    </section>
  );
}

/** Risk produced from AI-suggested inputs is labelled as such; a human assessment replaces it. */
export function AiSuggestedRiskNote({ band, score }: { band: string; score: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-violet-900">
      <SparkleIcon size={12} /> AI-suggested inputs scored on the matrix: <RiskBadge band={band} score={score} />
    </span>
  );
}
