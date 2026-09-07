"use client";

import { RemoteRecoverableErrorState } from "@metiquo/ui";

import { canReadPrevious } from "../lib/backend";

type ReadQuery = Readonly<{
  data?: unknown;
  error: Error | null;
  isError: boolean;
  isFetching: boolean;
  refetch: () => Promise<unknown>;
}>;

/** Keep the content mounted in its existing slot; add an explicit retry beside it. */
export function QueryRecovery({ queries }: Readonly<{ queries: readonly ReadQuery[] }>) {
  if (!queries.every(canReadPrevious)) return null;
  const failed = queries.filter((query) => query.isError && canReadPrevious(query));
  if (failed.length === 0) return null;
  return (
    <RemoteRecoverableErrorState
      compact
      title="Actualisation indisponible"
      description="La dernière lecture reste affichée. Sa fraîcheur n’a pas pu être confirmée."
      retryDisabled={failed.some((query) => query.isFetching)}
      onRetry={() => void Promise.all(failed.map((query) => query.refetch()))}
    />
  );
}
