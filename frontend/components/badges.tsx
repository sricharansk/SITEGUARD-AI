// Status, severity and risk badges. Each one shows text plus a shape icon so meaning never depends on color.
import type { ReactNode } from "react";
import { humanize } from "@/lib/format";
import type { ApprovalStatus, IncidentStatus, RiskBand, Severity, WorkStatus } from "@/lib/types";
import {
  CheckIcon,
  CircleShape,
  ClockIcon,
  CrossIcon,
  DashIcon,
  DiamondShape,
  DotIcon,
  OctagonShape,
  PencilIcon,
  RingIcon,
  SparkleIcon,
  TriangleShape,
  UserIcon,
} from "./icons";

type Tone = "slate" | "emerald" | "amber" | "orange" | "red" | "sky" | "violet" | "solidRed";

const TONES: Record<Tone, string> = {
  slate: "border-slate-300 bg-slate-50 text-slate-700",
  emerald: "border-emerald-300 bg-emerald-50 text-emerald-800",
  amber: "border-amber-300 bg-amber-50 text-amber-900",
  orange: "border-orange-300 bg-orange-50 text-orange-900",
  red: "border-red-300 bg-red-50 text-red-800",
  sky: "border-sky-300 bg-sky-50 text-sky-900",
  violet: "border-violet-300 bg-violet-50 text-violet-800",
  solidRed: "border-red-800 bg-red-700 text-white",
};

export function Badge({
  tone = "slate",
  icon,
  children,
  label,
  className = "",
}: {
  tone?: Tone;
  icon?: ReactNode;
  children: ReactNode;
  /** Context read before the visible text by screen readers and shown as a tooltip, e.g. "Severity". */
  label?: string;
  className?: string;
}) {
  // `relative` anchors the absolutely positioned sr-only label, so it stays inside a scrolling table.
  return (
    <span
      className={`relative inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs font-semibold whitespace-nowrap ${TONES[tone]} ${className}`}
      title={label}
    >
      {icon}
      {label ? <span className="sr-only">{label}: </span> : null}
      <span>{children}</span>
    </span>
  );
}

const LEVEL: Record<RiskBand, { tone: Tone; shape: string; Icon: (p: { size?: number }) => ReactNode }> = {
  LOW: { tone: "emerald", shape: "circle", Icon: CircleShape },
  MEDIUM: { tone: "amber", shape: "diamond", Icon: DiamondShape },
  HIGH: { tone: "orange", shape: "triangle", Icon: TriangleShape },
  CRITICAL: { tone: "solidRed", shape: "octagon", Icon: OctagonShape },
};

function LevelBadge({ kind, level }: { kind: "Severity" | "Risk"; level: RiskBand | string }) {
  const spec = LEVEL[level as RiskBand] ?? { tone: "slate" as Tone, shape: "dash", Icon: DashIcon };
  const { Icon } = spec;
  return (
    <span data-shape={spec.shape} data-level={level} className="inline-flex">
      <Badge tone={spec.tone} icon={<Icon size={12} />} label={kind}>
        {level}
      </Badge>
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: Severity | string }) {
  return <LevelBadge kind="Severity" level={severity} />;
}

export function RiskBadge({ band, score }: { band: RiskBand | string; score?: number }) {
  const spec = LEVEL[band as RiskBand] ?? { tone: "slate" as Tone, shape: "dash", Icon: DashIcon };
  const { Icon } = spec;
  const text = score === undefined ? band : `${band} · ${score}`;
  return (
    <span data-shape={spec.shape} data-level={band} className="inline-flex">
      <Badge
        tone={spec.tone}
        icon={<Icon size={12} />}
        label={score === undefined ? "Risk" : "Risk (band and score)"}
      >
        {text}
      </Badge>
    </span>
  );
}

const STATUS_TONE: Record<IncidentStatus, Tone> = {
  REPORTED: "amber",
  TRIAGED: "amber",
  UNDER_INVESTIGATION: "sky",
  PENDING_APPROVAL: "violet",
  ACTION_IN_PROGRESS: "sky",
  PENDING_VERIFICATION: "sky",
  CLOSED: "emerald",
};

export function StatusBadge({ status }: { status: IncidentStatus | string }) {
  const tone = STATUS_TONE[status as IncidentStatus] ?? "slate";
  const icon =
    status === "CLOSED" ? (
      <CheckIcon size={12} />
    ) : status.startsWith("PENDING") ? (
      <ClockIcon size={12} />
    ) : (
      <DotIcon size={12} />
    );
  return (
    <Badge tone={tone} icon={icon} label="Status">
      {humanize(status)}
    </Badge>
  );
}

export function ApprovalBadge({ status }: { status: ApprovalStatus | string }) {
  const map: Record<string, [Tone, ReactNode]> = {
    DRAFT: ["slate", <RingIcon key="i" size={12} />],
    PENDING_REVIEW: ["amber", <ClockIcon key="i" size={12} />],
    APPROVED: ["emerald", <CheckIcon key="i" size={12} />],
    MODIFIED: ["sky", <PencilIcon key="i" size={12} />],
    REJECTED: ["red", <CrossIcon key="i" size={12} />],
    SUPERSEDED: ["slate", <DashIcon key="i" size={12} />],
  };
  const [tone, icon] = map[status] ?? ["slate", null];
  return (
    <Badge tone={tone} icon={icon} label="Approval">
      {humanize(status)}
    </Badge>
  );
}

export function WorkBadge({ status }: { status: WorkStatus | string }) {
  const map: Record<string, [Tone, ReactNode]> = {
    NOT_STARTED: ["slate", <RingIcon key="i" size={12} />],
    IN_PROGRESS: ["sky", <ClockIcon key="i" size={12} />],
    COMPLETED: ["amber", <CheckIcon key="i" size={12} />],
    VERIFIED: ["emerald", <CheckIcon key="i" size={12} />],
    VERIFICATION_FAILED: ["red", <CrossIcon key="i" size={12} />],
  };
  const [tone, icon] = map[status] ?? ["slate", null];
  const text = status === "COMPLETED" ? "Completed, awaiting verification" : humanize(status);
  return (
    <Badge tone={tone} icon={icon} label="Work">
      {text}
    </Badge>
  );
}

export function DomainBadge({ domain }: { domain: string }) {
  return <Badge label="Domain">{humanize(domain)}</Badge>;
}

export function AiBadge({ children = "AI proposed" }: { children?: ReactNode }) {
  return (
    <Badge tone="violet" icon={<SparkleIcon size={12} />}>
      {children}
    </Badge>
  );
}

export function HumanBadge({ children = "Human authored" }: { children?: ReactNode }) {
  return (
    <Badge tone="sky" icon={<UserIcon size={12} />}>
      {children}
    </Badge>
  );
}

export function SyntheticBadge() {
  return (
    <Badge tone="slate" label="Demo data">
      Synthetic
    </Badge>
  );
}

export function CriticalBadge() {
  return (
    <span data-shape="octagon" className="inline-flex">
      <Badge tone="solidRed" icon={<OctagonShape size={12} />} label="Needs HSE manager approval">
        Critical
      </Badge>
    </span>
  );
}
