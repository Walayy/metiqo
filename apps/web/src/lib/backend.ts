export class BackendReadError extends Error {
  constructor(readonly status: number) {
    super(
      status === 401 || status === 403
        ? "Cette lecture n’est plus autorisée."
        : status === 404
          ? "Cette ressource n’est pas disponible."
          : "Le service de données ne répond pas. Réessayez dans quelques instants.",
    );
    this.name = "BackendReadError";
  }
}

/** One bounded request; writes are never automatically replayed here. */
export function requestBackend(input: RequestInfo | URL, init: RequestInit = {}) {
  const deadline = AbortSignal.timeout(15_000);
  return fetch(input, {
    ...init,
    signal: init.signal ? AbortSignal.any([init.signal, deadline]) : deadline,
  });
}

export async function readBackend(input: RequestInfo | URL, init: RequestInit = {}) {
  const response = await requestBackend(input, init);
  if (!response.ok) throw new BackendReadError(response.status);
  return response;
}

export function canReadPrevious(query: Readonly<{ data?: unknown; error: Error | null }>) {
  return (
    query.data !== undefined &&
    !(
      query.error instanceof BackendReadError &&
      [400, 401, 403, 404, 410].includes(query.error.status)
    )
  );
}
