// Incident header, the reported facts (human-entered, shown as the verified record) and the lifecycle stepper.
import { formatDateTime, humanize } from "@/lib/format";
import { INCIDENT_STATUSES, type Incident, type IncidentEvent, type Project } from "@/lib/types";
import { DomainBadge, SeverityBadge, StatusBadge, SyntheticBadge } from "../badges";
import { CheckIcon, ClockIcon, RingIcon, UserIcon } from "../icons";
import { personName, type People } from "./people";

export function LifecycleStepper({ status }: { status: Incident["status"] }) {
  const currentIndex = INCIDENT_STATUSES.indexOf(status);
  return (
    <ol aria-label="Incident lifecycle" className="flex flex-wrap gap-1 text-xs">
      {INCIDENT_STATUSES.map((s, i) => {
        const state = i < currentIndex ? "done" : i === currentIndex ? "current" : "todo";
        return (
          <li
            key={s}
            aria-current={state === "current" ? "step" : undefined}
            className={`flex items-center gap-1 rounded border px-2 py-1 ${
              state === "current"
                ? "border-slate-900 bg-slate-900 font-semibold text-white"
                : state === "done"
                  ? "border-slate-300 bg-white text-slate-700"
                  : "border-dashed border-slate-300 bg-slate-50 text-slate-500"
            }`}
          >
            {state === "done" ? <CheckIcon size={12} /> : state === "current" ? <ClockIcon size={12} /> : <RingIcon size={12} />}
            <span>
              {humanize(s)}
              {state === "current" ? <span className="sr-only"> (current)</span> : state === "done" ? <span className="sr-only"> (done)</span> : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function IncidentSummary({ incident, project, people }: { incident: Incident; project?: Project; people: People }) {
  const site = project?.sites.find((s) => s.id === incident.site_id)?.name;
  const facts: [string, string][] = [
    ["Occurred", formatDateTime(incident.occurred_at)],
    ["Reported", `${formatDateTime(incident.reported_at)} by ${personName(people, incident.reporter_id)}`],
    ["Site", site ?? "Not specified"],
    ["Location", incident.location ?? "—"],
    ["Activity", incident.activity ?? "—"],
    ["Category", incident.category ?? "—"],
    ["People involved", String(incident.people_involved)],
    ["Last updated", formatDateTime(incident.updated_at)],
  ];
  if (incident.closed_at) facts.push(["Closed", formatDateTime(incident.closed_at)]);
  return (
    <section aria-labelledby="facts-title" className="card border-l-4 border-l-emerald-600">
      <div className="card-header">
        <h2 id="facts-title" className="card-title flex items-center gap-1.5">
          <UserIcon size={14} /> Reported facts
        </h2>
        <span className="text-xs text-slate-600">Entered by people; the record AI output is checked against</span>
      </div>
      <div className="card-body space-y-3">
        <div className="flex flex-wrap gap-1.5">
          <SeverityBadge severity={incident.severity} />
          <StatusBadge status={incident.status} />
          <DomainBadge domain={incident.domain} />
          {incident.is_synthetic ? <SyntheticBadge /> : null}
        </div>
        <p className="whitespace-pre-line text-slate-900">{incident.description}</p>
        {incident.immediate_actions ? (
          <div>
            <p className="kicker">Immediate actions taken</p>
            <p className="whitespace-pre-line">{incident.immediate_actions}</p>
          </div>
        ) : null}
        <dl className="grid gap-x-4 gap-y-1.5 text-xs sm:grid-cols-2 lg:grid-cols-4">
          {facts.map(([k, v]) => (
            <div key={k}>
              <dt className="kicker">{k}</dt>
              <dd className="text-slate-900">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

export function Timeline({ history, people }: { history: IncidentEvent[]; people: People }) {
  if (history.length === 0) return <p className="text-slate-600">No lifecycle events yet.</p>;
  return (
    <ol className="relative space-y-3 border-l-2 border-slate-200 pl-4" aria-label="Lifecycle history">
      {history.map((e) => (
        <li key={e.id} className="relative">
          <span className="absolute top-1 -left-[1.4rem] h-3 w-3 rounded-full border-2 border-white bg-slate-600" aria-hidden="true" />
          <p className="flex flex-wrap items-center gap-1.5 text-xs">
            {e.from_status ? (
              <>
                <StatusBadge status={e.from_status} />
                <span aria-label="to">→</span>
              </>
            ) : null}
            <StatusBadge status={e.to_status} />
          </p>
          <p className="mt-0.5 text-xs text-slate-600">
            {formatDateTime(e.created_at)} · {personName(people, e.actor_id)}
          </p>
          {e.note ? <p className="text-sm text-slate-800">{e.note}</p> : null}
        </li>
      ))}
    </ol>
  );
}
