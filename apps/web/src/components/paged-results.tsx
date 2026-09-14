"use client";

import { Button } from "@metiquo/ui";
import { useState } from "react";

import { canReadPrevious } from "../lib/backend";

interface ContractPage {
  data: readonly unknown[];
  page: { offset: number; total: number };
}

export function nextPageOffset(page: ContractPage) {
  const next = page.page.offset + page.data.length;
  return page.data.length > 0 && next < page.page.total ? next : undefined;
}

/** Add to a readable result without replacing it or resetting its scroll position. */
export function PagedResults({
  label,
  query,
}: Readonly<{
  label: string;
  query: {
    data: ContractPage | undefined;
    error: Error | null;
    hasNextPage: boolean;
    isFetching: boolean;
    isFetchingNextPage: boolean;
    fetchNextPage: () => Promise<unknown>;
  };
}>) {
  const [expanded, setExpanded] = useState(false);
  if ((!query.hasNextPage && !expanded) || !query.data || !canReadPrevious(query)) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-ink-secondary" role="status" aria-atomic="true">
        {query.data.data.length} résultats affichés sur {query.data.page.total}
      </p>
      <Button
        aria-disabled={query.isFetching || !query.hasNextPage}
        aria-busy={query.isFetchingNextPage}
        onClick={() => {
          setExpanded(true);
          void query.fetchNextPage();
        }}
        variant="outline"
      >
        {query.isFetchingNextPage
          ? "Chargement…"
          : query.hasNextPage
            ? `Afficher plus ${label}`
            : "Tous les résultats sont affichés"}
      </Button>
    </div>
  );
}
