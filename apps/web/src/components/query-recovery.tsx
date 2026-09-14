"use client";

import {
  RemoteBlockingErrorState,
  RemotePermissionDeniedState,
  RemoteRecoverableErrorState,
} from "@metiquo/ui";

import { BackendReadError, canReadPrevious } from "../lib/backend";

type ReadQuery = Readonly<{
  data?: unknown;
  error: Error | null;
  isError: boolean;
  isFetching: boolean;
  isFetchNextPageError?: boolean;
  fetchNextPage?: () => Promise<unknown>;
  refetch: () => Promise<unknown>;
}>;

/** Missing records and revoked access need different recovery guidance from a failed refresh. */
export function QueryFailure({
  description,
  missingDescription,
  missingTitle,
  queries,
}: Readonly<{
  description: string;
  missingDescription: string;
  missingTitle: string;
  queries: readonly ReadQuery[];
}>) {
  if (
    queries.some(
      (query) => query.error instanceof BackendReadError && [401, 403].includes(query.error.status),
    )
  ) {
    return <RemotePermissionDeniedState />;
  }
  const primaryError = queries[0]?.error;
  if (primaryError instanceof BackendReadError && [404, 410].includes(primaryError.status)) {
    return <RemoteBlockingErrorState description={missingDescription} title={missingTitle} />;
  }
  return (
    <RemoteRecoverableErrorState
      description={description}
      onRetry={() => void Promise.all(queries.map((query) => query.refetch()))}
      retryDisabled={queries.some((query) => query.isFetching)}
    />
  );
}

/** Keep the content mounted in its existing slot; add an explicit retry beside it. */
export function QueryRecovery({ queries }: Readonly<{ queries: readonly ReadQuery[] }>) {
  if (!queries.every(canReadPrevious)) return null;
  const failed = queries.filter((query) => query.isError && canReadPrevious(query));
  if (failed.length === 0) return null;
  const nextPageFailed = failed.every((query) => query.isFetchNextPageError);
  return (
    <RemoteRecoverableErrorState
      compact
      title={nextPageFailed ? "Suite des résultats indisponible" : "Actualisation indisponible"}
      description={
        nextPageFailed
          ? "Les résultats déjà chargés restent affichés. Réessayez pour lire la suite."
          : "La dernière lecture reste affichée. Sa fraîcheur n’a pas pu être confirmée."
      }
      retryDisabled={failed.some((query) => query.isFetching)}
      onRetry={() =>
        void Promise.all(
          failed.map((query) =>
            query.isFetchNextPageError && query.fetchNextPage
              ? query.fetchNextPage()
              : query.refetch(),
          ),
        )
      }
    />
  );
}
