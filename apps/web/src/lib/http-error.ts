export type FailureKind = 'http' | 'network' | 'timeout' | 'invalid-response' | 'unexpected';

export class HttpError extends Error {
  readonly status: number;
  readonly retryAt: number;
  readonly kind: FailureKind;
  constructor(
    status: number,
    options: { message?: string; retryAt?: number; kind?: FailureKind } = {},
  ) {
    super(options.message ?? statusMessage(status));
    this.name = 'HttpError';
    this.status = status;
    this.retryAt = options.retryAt ?? 0;
    this.kind = options.kind ?? 'http';
  }
  get retryAfter() {
    return remainingSeconds(this.retryAt);
  }
}

export function statusMessage(status: number) {
  const messages: Record<number, string> = {
    400: 'La demande est invalide. Vérifiez les informations saisies.',
    401: 'Connectez-vous pour accéder à cet espace.',
    403: 'Votre compte ne dispose pas de cet accès.',
    404: 'Cet élément est introuvable ou n’est plus disponible.',
    408: 'Le serveur n’a pas répondu à temps.',
    409: 'Les informations ont changé. Actualisez-les avant de recommencer.',
    410: 'Cet élément n’est plus disponible.',
    413: 'La demande est trop volumineuse. Réduisez son contenu.',
    422: 'Vérifiez les informations saisies avant de continuer.',
    423: 'Ce compte est suspendu. Contactez un administrateur de Metiquo.',
    429: 'Trop de demandes ont été envoyées. Patientez avant de réessayer.',
    500: 'Une erreur du serveur empêche de terminer la demande.',
    502: 'Le serveur est momentanément injoignable.',
    503: 'Le service est momentanément indisponible.',
    504: 'Le serveur met trop de temps à répondre.',
  };
  return messages[status] ?? 'La demande n’a pas pu aboutir. Réessayez dans un moment.';
}

export function remainingSeconds(deadline: number, now = Date.now()) {
  return Math.max(0, Math.ceil((deadline - now) / 1000));
}

// Retry-After accepts seconds or an HTTP date. Use the server clock when supplied.
export function retryDeadline(value: string | null, serverDate: string | null, now = Date.now()) {
  if (!value?.trim()) return 0;
  const text = value.trim();
  const delay = /^\d+$/.test(text)
    ? Number(text) * 1000
    : /[a-z]/i.test(text)
      ? Date.parse(text) -
        (serverDate && Number.isFinite(Date.parse(serverDate)) ? Date.parse(serverDate) : now)
      : NaN;
  return Number.isFinite(delay) && delay >= 0 && Number.isSafeInteger(now + delay)
    ? now + delay
    : 0;
}

export function retryRead(failures: number, error: Error) {
  return (
    failures < 1 &&
    error instanceof HttpError &&
    !error.retryAt &&
    (error.kind === 'network' || error.kind === 'timeout' || error.status >= 500)
  );
}

export function needsStatusScreen(error: Error | null): error is HttpError {
  return (
    error instanceof HttpError &&
    (error.kind !== 'http' || [401, 403, 423, 429].includes(error.status) || error.status >= 500)
  );
}
