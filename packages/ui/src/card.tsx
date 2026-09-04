import type { HTMLAttributes } from "react";

import { cn } from "./lib/cn";

export function Card({ className, ...properties }: HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={cn(
        "rounded-xl border border-border-subtle bg-surface-raised text-ink-primary shadow-panel",
        className,
      )}
      {...properties}
    />
  );
}

export function CardHeader({ className, ...properties }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("grid gap-3 p-6 pb-3", className)} {...properties} />;
}

export function CardTitle({ className, ...properties }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn("text-balance text-2xl font-semibold tracking-tight", className)}
      {...properties}
    />
  );
}

export function CardContent({ className, ...properties }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-6 pt-3", className)} {...properties} />;
}
