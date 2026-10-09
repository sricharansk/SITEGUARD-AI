import type { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  actions,
  kicker,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  kicker?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {kicker ? <p className="kicker">{kicker}</p> : null}
        <h1 className="text-xl font-bold tracking-tight">{title}</h1>
        {subtitle ? <div className="mt-0.5 text-slate-600">{subtitle}</div> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Card({
  title,
  actions,
  children,
  id,
  className = "",
  bodyClassName = "card-body",
  headingLevel = 2,
}: {
  title: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  id?: string;
  className?: string;
  bodyClassName?: string;
  headingLevel?: 2 | 3;
}) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  const headingId = id ? `${id}-title` : undefined;
  return (
    <section className={`card ${className}`} aria-labelledby={headingId} id={id}>
      <div className="card-header">
        <Heading id={headingId} className="card-title">
          {title}
        </Heading>
        {actions}
      </div>
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}
