import type { HTMLAttributes } from "react";

import { cn } from "./lib/cn";

export function Badge({ className, ...properties }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex min-h-6 w-fit items-center rounded-full border border-border-subtle bg-surface-muted px-2.5 text-xs font-semibold tracking-wide text-ink-secondary",
        className,
      )}
      {...properties}
    />
  );
}
