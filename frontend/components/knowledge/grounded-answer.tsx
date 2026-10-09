// A grounded knowledge answer (POST /knowledge/answer), framed like every other AI output: dashed violet border and
// the "AI decision support, needs human review" label. Each statement points to the citation it comes from
// (document title, version, page, section); insufficient and conflicting evidence are stated plainly, and statements
// the API removed as unsupported are shown only as removed text, never as facts.
import { formatDate, formatPercent } from "@/lib/format";
import type { AnswerCitation, AnswerStatus, KnowledgeAnswer } from "@/lib/types";
import { AI_LABEL } from "../ai/ai-panel";
import { isFallback } from "../ai/refs";
import { Badge } from "../badges";
import { AlertIcon, CheckIcon, CrossIcon, FileIcon, SparkleIcon } from "../icons";

interface StatusStyle {
  label: string;
  tone: "emerald" | "amber" | "red";
  Icon: typeof CheckIcon;
  explanation: string;
}

export const ANSWER_STATUS: Record<AnswerStatus, StatusStyle> = {
  ANSWERED: {
    label: "Answered from cited sources",
    tone: "emerald",
    Icon: CheckIcon,
    explanation: "Every statement below is taken from the document section it cites. Check that it applies to this site.",
  },
  INSUFFICIENT_EVIDENCE: {
    label: "Insufficient evidence",
    tone: "amber",
    Icon: AlertIcon,
    explanation:
      "The documents you can access do not answer this question, so no answer was made up. Ask a competent person or add the controlling document.",
  },
  CONFLICTING_EVIDENCE: {
    label: "Conflicting evidence",
    tone: "red",
    Icon: CrossIcon,
    explanation:
      "The cited sources disagree. Do not act on either value until a competent person decides which document controls.",
  },
};

/** "Working at Height Procedure · v2 · page 3 · section 4 Guardrails" */
export function citationText(c: Pick<AnswerCitation, "document_title" | "version" | "page" | "section">): string {
  const parts = [c.document_title, `v${c.version}`, c.page === null ? "no page number" : `page ${c.page}`];
  if (c.section) parts.push(`section ${c.section}`);
  return parts.join(" · ");
}

export function GroundedAnswer({ result, question }: { result: KnowledgeAnswer; question: string }) {
  const status = ANSWER_STATUS[result.status] ?? ANSWER_STATUS.INSUFFICIENT_EVIDENCE;
  const { Icon } = status;
  const number = new Map(result.citations.map((c, i) => [c.ref, i + 1]));
  const fallback = isFallback(result.provider);
  const lowConfidence = result.confidence < 0.5;

  return (
    <section
      aria-labelledby="grounded-answer-title"
      data-kind="ai"
      data-status={result.status}
      className="rounded-md border-2 border-dashed border-violet-400 bg-violet-50/70"
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-dashed border-violet-300 px-3 py-2">
        <SparkleIcon size={14} className="text-violet-700" />
        <h3 id="grounded-answer-title" className="text-sm font-semibold text-violet-950">
          <span className="sr-only">AI output:</span> Grounded answer
        </h3>
        <span className="rounded bg-violet-700 px-1.5 py-0.5 text-[11px] font-semibold text-white">{AI_LABEL}</span>
        <span className="ml-auto flex flex-wrap items-center gap-1.5 text-xs">
          <Badge tone={fallback ? "amber" : "violet"} icon={fallback ? <AlertIcon size={12} /> : undefined}>
            {fallback ? `Fallback provider: ${result.provider}` : `Provider: ${result.provider}`}
          </Badge>
          <Badge tone={lowConfidence ? "amber" : "violet"} icon={lowConfidence ? <AlertIcon size={12} /> : undefined}>
            {`Confidence ${formatPercent(result.confidence)}${lowConfidence ? " (low)" : ""}`}
          </Badge>
          {result.needs_human_review ? (
            <Badge tone="amber" icon={<AlertIcon size={12} />}>
              Flagged for review
            </Badge>
          ) : null}
        </span>
      </header>

      <div className="space-y-3 px-3 py-3">
        <p className="text-xs text-slate-700">
          Question: <q className="text-slate-900">{question}</q>
        </p>
        <div className="rounded border border-slate-200 bg-white px-3 py-2">
          <Badge tone={status.tone} icon={<Icon size={12} />} label="Answer status">
            {status.label}
          </Badge>
          <p className="mt-1 text-sm text-slate-700">{status.explanation}</p>
        </div>

        {result.statements.length > 0 ? (
          <ol className="space-y-1.5" aria-label="Answer statements">
            {result.statements.map((s, i) => (
              <li key={i} className="text-slate-900">
                {s.text}{" "}
                {s.citations.map((ref) => (
                  <a
                    key={ref}
                    href={`#citation-${number.get(ref)}`}
                    className="link text-xs align-super"
                    aria-label={`Source ${number.get(ref)}`}
                  >
                    [{number.get(ref)}]
                  </a>
                ))}
              </li>
            ))}
          </ol>
        ) : (
          <p className="font-medium text-slate-900">{result.answer}</p>
        )}

        {result.conflicts.length > 0 ? (
          <div role="alert" className="rounded border border-red-300 bg-red-50 px-3 py-2 text-red-900">
            <p className="text-xs font-semibold">Where the sources disagree</p>
            <ul className="list-disc pl-5">
              {result.conflicts.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <div>
          <p className="kicker text-violet-900/80">Cited sources</p>
          {result.citations.length === 0 ? (
            <p className="text-amber-900">No sources cited: there is nothing here to act on.</p>
          ) : (
            <ol className="mt-1 space-y-1" aria-label="Cited sources">
              {result.citations.map((c, i) => (
                <li key={c.ref} id={`citation-${i + 1}`} className="flex flex-wrap items-baseline gap-1.5" data-testid="answer-citation">
                  <span className="font-semibold tabular-nums">[{i + 1}]</span>
                  <FileIcon size={12} className="self-center text-slate-600" />
                  <span>{citationText(c)}</span>
                  {c.effective_date ? <span className="text-xs text-slate-600">effective {formatDate(c.effective_date)}</span> : null}
                  <code className="mono text-slate-500">{c.ref}</code>
                </li>
              ))}
            </ol>
          )}
        </div>

        {result.unsupported_claims.length > 0 ? (
          <details className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-amber-950">
            <summary className="cursor-pointer text-xs font-semibold">
              {result.unsupported_claims.length} statement(s) removed: no retrieved source supports them
            </summary>
            <p className="mt-1 text-xs">These are not facts. They are listed only so a reviewer can see what was removed.</p>
            <ul className="mt-1 list-disc pl-5 text-sm line-through decoration-amber-700/60">
              {result.unsupported_claims.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </details>
        ) : null}

        {result.excluded_sources.length > 0 ? (
          <p className="text-xs text-amber-900">
            {result.excluded_sources.length} source(s) left out because they contain instruction-like text (treated as
            data, never as instructions): {result.excluded_sources.map((s) => s.ref).join(", ")}
          </p>
        ) : null}

        <dl className="grid gap-2 border-t border-dashed border-violet-300 pt-2 text-xs sm:grid-cols-2">
          <div>
            <dt className="kicker text-violet-900/80">Uncertainty</dt>
            <dd className="text-slate-800">{result.uncertainty || "—"}</dd>
          </div>
          <div>
            <dt className="kicker text-violet-900/80">Retrieval</dt>
            <dd className="text-slate-800">
              {result.retrieval.sources} authorized source(s) searched; best match covers{" "}
              {formatPercent(result.retrieval.question_coverage)} of the question.
            </dd>
          </div>
        </dl>
        <p className="text-xs text-slate-700 italic">{result.disclaimer}</p>
      </div>
    </section>
  );
}
