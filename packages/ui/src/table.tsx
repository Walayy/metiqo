import type {
  HTMLAttributes,
  ReactNode,
  TableHTMLAttributes,
  TdHTMLAttributes,
  ThHTMLAttributes,
} from "react";

import { cn } from "./lib/cn";

export type TableColumnVariant =
  "text" | "identity" | "number" | "date" | "status" | "detail" | "technical" | "action";

export type TableColumn = Readonly<{
  label: string;
  variant?: TableColumnVariant;
  /** Relative share of available space; defaults follow the content type. */
  weight?: number;
}>;

const columnWeights: Record<TableColumnVariant, number> = {
  text: 1.3,
  identity: 2.2,
  number: 0.8,
  date: 1.3,
  status: 1.1,
  detail: 2.2,
  technical: 1.8,
  action: 1.3,
};

export type TableProperties = TableHTMLAttributes<HTMLTableElement> & {
  columns?: readonly TableColumn[];
  density?: "default" | "compact";
};

/**
 * A content-sized table that becomes labelled records in a narrow container.
 * Supply a label on every TableCell so the same information remains scannable
 * without horizontal scrolling at small widths.
 */
export function Table({
  children,
  className,
  columns,
  density = "default",
  ...properties
}: TableProperties) {
  const totalWeight = columns?.reduce(
    (total, column) => total + (column.weight ?? columnWeights[column.variant ?? "text"]),
    0,
  );

  return (
    <div
      aria-label={properties["aria-label"]}
      aria-labelledby={properties["aria-labelledby"]}
      className="ui-table-region"
      role="region"
      tabIndex={0}
    >
      <table
        className={cn("ui-table", className)}
        data-density={density}
        data-wide={columns && columns.length >= 8 ? "true" : undefined}
        role="table"
        {...properties}
      >
        {columns && totalWeight ? (
          <>
            <colgroup>
              {columns.map((column) => (
                <col
                  key={column.label}
                  style={{
                    width: `${(((column.weight ?? columnWeights[column.variant ?? "text"]) / totalWeight) * 100).toFixed(4)}%`,
                  }}
                />
              ))}
            </colgroup>
            <TableHeader>
              <TableRow>
                {columns.map((column) => (
                  <TableHead key={column.label} variant={column.variant}>
                    {column.label}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
          </>
        ) : null}
        {children}
      </table>
    </div>
  );
}

export function TableHeader({ className, ...properties }: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("ui-table-header", className)} role="rowgroup" {...properties} />;
}

export function TableBody({ className, ...properties }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("ui-table-body", className)} role="rowgroup" {...properties} />;
}

export function TableRow({ className, ...properties }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("ui-table-row", className)} role="row" {...properties} />;
}

export function TableHead({
  className,
  variant = "text",
  ...properties
}: ThHTMLAttributes<HTMLTableCellElement> & { variant?: TableColumnVariant | undefined }) {
  return (
    <th
      className={cn("ui-table-head", className)}
      data-variant={variant}
      role="columnheader"
      scope="col"
      {...properties}
    />
  );
}

export function TableCell({
  children,
  className,
  label,
  variant = "text",
  ...properties
}: TdHTMLAttributes<HTMLTableCellElement> & {
  label: string;
  variant?: TableColumnVariant;
}) {
  return (
    <td
      className={cn("ui-table-cell", className)}
      data-variant={variant}
      role="cell"
      {...properties}
    >
      <span aria-hidden="true" className="ui-table-cell-label">
        {label}
      </span>
      <div className="ui-table-cell-value">{children}</div>
    </td>
  );
}

export function TableCellContent({
  className,
  primary,
  secondary,
  ...properties
}: HTMLAttributes<HTMLDivElement> & { primary: ReactNode; secondary?: ReactNode }) {
  return (
    <div className={cn("ui-cell-content", className)} {...properties}>
      <div className="ui-cell-primary">{primary}</div>
      {secondary !== undefined && secondary !== null ? (
        <div className="ui-cell-secondary">{secondary}</div>
      ) : null}
    </div>
  );
}

export type StatusListItem = Readonly<{
  label: string;
  value: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger";
}>;

/** Secondary states stay compact and textual; reserve badges for the main state. */
export function StatusList({
  className,
  items,
  ...properties
}: HTMLAttributes<HTMLUListElement> & { items: readonly StatusListItem[] }) {
  return (
    <ul className={cn("ui-status-list", className)} {...properties}>
      {items.map((item) => (
        <li data-tone={item.tone ?? "neutral"} key={item.label}>
          <span className="ui-status-label">{item.label}: </span>
          <span className="ui-status-value">{item.value}</span>
        </li>
      ))}
    </ul>
  );
}
