import { Children, type HTMLAttributes, type LabelHTMLAttributes, type ReactNode } from "react";

import { cn } from "./lib/cn";

/** Full technical values remain readable without imposing their length on the layout. */
export function TechnicalText({ className, ...properties }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("ui-technical-text", className)} {...properties} />;
}

/** Keep related human-readable values together, wrapping each group only when necessary. */
export function InlineValues({
  className,
  items,
  separator = "·",
  ...properties
}: Omit<HTMLAttributes<HTMLSpanElement>, "children"> & {
  items: readonly ReactNode[];
  separator?: string;
}) {
  return (
    <span className={cn("ui-inline-values", className)} {...properties}>
      {items.map((item, index) => (
        <span className="ui-inline-value" key={index}>
          {index > 0 ? <span className="ui-inline-separator">{separator} </span> : null}
          {typeof item === "string" ? item.replace(/\s+(\d+)$/u, "\u00a0$1") : item}
        </span>
      ))}
    </span>
  );
}

export function MetricGrid({ children, className, ...properties }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("ui-metric-grid", className)}
      data-count={Children.toArray(children).length}
      {...properties}
    >
      {children}
    </div>
  );
}

export function Metric({
  className,
  detail,
  emphasis = "default",
  label,
  value,
  ...properties
}: Omit<HTMLAttributes<HTMLDivElement>, "children"> & {
  detail?: ReactNode;
  emphasis?: "default" | "statistic";
  label: ReactNode;
  value: ReactNode;
}) {
  return (
    <div className={cn("ui-metric", className)} data-emphasis={emphasis} {...properties}>
      <dl className="ui-metric-definition">
        <dt className="ui-metric-label">{label}</dt>
        <dd className="ui-metric-value">{value}</dd>
        {detail ? <dd className="ui-metric-detail">{detail}</dd> : null}
      </dl>
    </div>
  );
}

export function SelectionItem({ className, ...properties }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("ui-selection-item", className)} {...properties} />;
}

export function ContextPanel({
  className,
  tone = "neutral",
  ...properties
}: HTMLAttributes<HTMLDivElement> & {
  tone?: "neutral" | "info" | "warning" | "success" | "danger";
}) {
  return <div className={cn("ui-context-panel", className)} data-tone={tone} {...properties} />;
}

export function Section({ className, ...properties }: HTMLAttributes<HTMLElement>) {
  return <section className={cn("ui-section", className)} {...properties} />;
}
