import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "./lib/cn";

export type CardProperties = HTMLAttributes<HTMLElement> & { variant?: "default" | "flat" };

export function Card({ className, variant = "default", ...properties }: CardProperties) {
  return <section className={cn("ui-card", className)} data-variant={variant} {...properties} />;
}

export function CardHeader({ className, ...properties }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("ui-card-header", className)} {...properties} />;
}

export function CardTitle({ className, ...properties }: HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("ui-card-title", className)} {...properties} />;
}

export function CardContent({ className, ...properties }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("ui-card-content", className)} {...properties} />;
}

export type TitledCardProperties = CardProperties & { title: string; icon?: ReactNode };

export function TitledCard({ children, icon, title, ...properties }: TitledCardProperties) {
  return (
    <Card aria-label={title} {...properties}>
      <CardHeader>
        <CardTitle className="ui-titled-card-title">
          {icon ? (
            <span aria-hidden="true" className="ui-titled-card-icon">
              {icon}
            </span>
          ) : null}
          <span>{title}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="ui-titled-card-content">{children}</CardContent>
    </Card>
  );
}
