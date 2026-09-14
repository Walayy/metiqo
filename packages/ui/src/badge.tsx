import type { HTMLAttributes } from "react";

import { cn } from "./lib/cn";

export function Badge({ className, ...properties }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("ui-badge", className)} {...properties} />;
}
