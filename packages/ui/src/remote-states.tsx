"use client";

import type { CSSProperties, HTMLAttributes, MouseEventHandler, ReactNode } from "react";

import { Button } from "./button";
import { cn } from "./lib/cn";

export type RemoteStateKind =
  | "loading"
  | "empty"
  | "recoverable-error"
  | "blocking-error"
  | "stale"
  | "permission-denied"
  | "mock"
  | "offline"
  | "reconnecting";

type RemoteStateDefinition = Readonly<{
  description: string;
  mark: string;
  role: "alert" | "status";
  title: string;
  tone: string;
}>;

const remoteStateDefinitions = {
  "blocking-error": {
    description: "Cette vue ne peut pas être utilisée tant que le problème persiste.",
    mark: "!",
    role: "alert",
    title: "Données indisponibles",
    tone: "border-red-300 bg-red-50/80 dark:border-red-900 dark:bg-red-950/30",
  },
  empty: {
    description: "Aucun résultat ne correspond aux critères actuels.",
    mark: "—",
    role: "status",
    title: "Aucune donnée",
    tone: "border-border-subtle bg-surface-raised",
  },
  loading: {
    description: "Les données sont en cours de chargement.",
    mark: "…",
    role: "status",
    title: "Chargement des données",
    tone: "border-border-subtle bg-surface-raised",
  },
  mock: {
    description: "Cette vue utilise des données simulées isolées des données réelles.",
    mark: "M",
    role: "status",
    title: "Données simulées",
    tone: "border-accent bg-accent-soft",
  },
  offline: {
    description: "Les données déjà chargées restent disponibles lorsqu’elles sont sûres.",
    mark: "×",
    role: "status",
    title: "Hors connexion",
    tone: "border-amber-300 bg-amber-50/80 dark:border-amber-800 dark:bg-amber-950/30",
  },
  "permission-denied": {
    description: "Vous n’avez pas les droits nécessaires pour consulter cette ressource.",
    mark: "!",
    role: "alert",
    title: "Accès refusé",
    tone: "border-red-300 bg-red-50/80 dark:border-red-900 dark:bg-red-950/30",
  },
  reconnecting: {
    description: "Une nouvelle tentative est en cours. Le contenu précédent reste visible.",
    mark: "↻",
    role: "status",
    title: "Reconnexion en cours",
    tone: "border-amber-300 bg-amber-50/80 dark:border-amber-800 dark:bg-amber-950/30",
  },
  "recoverable-error": {
    description: "La dernière tentative a échoué. Vous pouvez réessayer sans perdre le contexte.",
    mark: "!",
    role: "alert",
    title: "Actualisation impossible",
    tone: "border-amber-300 bg-amber-50/80 dark:border-amber-800 dark:bg-amber-950/30",
  },
  stale: {
    description: "Le dernier résultat valide est affiché, mais sa fraîcheur n’est plus garantie.",
    mark: "!",
    role: "status",
    title: "Données anciennes",
    tone: "border-amber-300 bg-amber-50/80 dark:border-amber-800 dark:bg-amber-950/30",
  },
} satisfies Record<RemoteStateKind, RemoteStateDefinition>;

export type RemoteSkeletonProperties = Omit<HTMLAttributes<HTMLDivElement>, "children"> &
  Readonly<{
    height?: CSSProperties["blockSize"];
    width?: CSSProperties["inlineSize"];
  }>;

export function RemoteSkeleton({
  className,
  height = "1rem",
  style,
  width = "100%",
  ...properties
}: RemoteSkeletonProperties) {
  return (
    <div
      aria-hidden="true"
      className={cn("metiquo-skeleton", className)}
      data-remote-skeleton="true"
      style={{ blockSize: height, inlineSize: width, ...style }}
      {...properties}
    />
  );
}

export type RemoteLoadingStateProperties = Omit<HTMLAttributes<HTMLDivElement>, "children"> &
  Readonly<{
    label?: string;
    minHeight?: CSSProperties["minHeight"];
    rows?: number;
  }>;

export function RemoteLoadingState({
  className,
  label = "Chargement des données",
  minHeight = "12rem",
  rows = 3,
  style,
  ...properties
}: RemoteLoadingStateProperties) {
  const safeRowCount = Number.isFinite(rows) ? Math.max(1, Math.floor(rows)) : 3;
  const rowWidths = ["100%", "86%", "72%"] as const;

  return (
    <div
      aria-busy="true"
      aria-label={label}
      className={cn(
        "grid content-center gap-4 rounded-xl border border-border-subtle bg-surface-raised p-6",
        className,
      )}
      data-remote-state="loading"
      role="status"
      style={{ ...style, minHeight }}
      {...properties}
    >
      <div aria-hidden="true" className="grid gap-3">
        <RemoteSkeleton height="1.5rem" width="42%" />
        {Array.from({ length: safeRowCount }, (_, index) => (
          <RemoteSkeleton
            height="0.875rem"
            key={index}
            width={rowWidths[index % rowWidths.length]}
          />
        ))}
      </div>
    </div>
  );
}

export type RemoteStateProperties = Omit<HTMLAttributes<HTMLElement>, "children" | "title"> &
  Readonly<{
    action?: ReactNode;
    compact?: boolean;
    description?: ReactNode;
    kind: RemoteStateKind;
    title?: ReactNode;
  }>;

export function RemoteState({
  action,
  className,
  compact = false,
  description,
  kind,
  title,
  ...properties
}: RemoteStateProperties) {
  const definition = remoteStateDefinitions[kind];

  return (
    <section
      aria-atomic="true"
      className={cn(
        "flex items-start rounded-xl border text-ink-primary",
        compact ? "gap-3 px-4 py-3" : "min-h-48 gap-4 p-6",
        definition.tone,
        className,
      )}
      data-remote-state={kind}
      role={definition.role}
      {...properties}
    >
      <span
        aria-hidden="true"
        className={cn(
          "grid shrink-0 place-items-center rounded-full border border-current font-semibold",
          compact ? "size-7 text-xs" : "size-10 text-base",
        )}
      >
        {definition.mark}
      </span>
      <div
        className={cn(
          "grid min-w-0 flex-1",
          compact ? "gap-1" : "content-center gap-2 self-stretch",
        )}
      >
        <h2 className={cn("font-semibold", compact ? "text-sm" : "text-lg")}>
          {title ?? definition.title}
        </h2>
        <p
          className={cn("text-ink-secondary", compact ? "text-xs leading-5" : "text-sm leading-6")}
        >
          {description ?? definition.description}
        </p>
        {action ? <div className={cn(compact ? "pt-1" : "pt-2")}>{action}</div> : null}
      </div>
    </section>
  );
}

type NamedRemoteStateProperties = Omit<RemoteStateProperties, "kind">;

export function RemoteEmptyState(properties: NamedRemoteStateProperties) {
  return <RemoteState kind="empty" {...properties} />;
}

export type RemoteRecoverableErrorStateProperties = Omit<NamedRemoteStateProperties, "action"> &
  Readonly<{
    onRetry: MouseEventHandler<HTMLButtonElement>;
    retryDisabled?: boolean;
    retryLabel?: string;
  }>;

export function RemoteRecoverableErrorState({
  onRetry,
  retryDisabled = false,
  retryLabel = "Réessayer",
  ...properties
}: RemoteRecoverableErrorStateProperties) {
  return (
    <RemoteState
      action={
        <Button disabled={retryDisabled} onClick={onRetry} size="small" variant="outline">
          {retryLabel}
        </Button>
      }
      kind="recoverable-error"
      {...properties}
    />
  );
}

export function RemoteBlockingErrorState(properties: NamedRemoteStateProperties) {
  return <RemoteState kind="blocking-error" {...properties} />;
}

export function RemotePermissionDeniedState(properties: NamedRemoteStateProperties) {
  return <RemoteState kind="permission-denied" {...properties} />;
}

export function RemoteStaleState({ compact = true, ...properties }: NamedRemoteStateProperties) {
  return <RemoteState compact={compact} kind="stale" {...properties} />;
}

export function RemoteMockState({ compact = true, ...properties }: NamedRemoteStateProperties) {
  return <RemoteState compact={compact} kind="mock" {...properties} />;
}

export function RemoteOfflineState({ compact = true, ...properties }: NamedRemoteStateProperties) {
  return <RemoteState compact={compact} kind="offline" {...properties} />;
}

export function RemoteReconnectingState({
  compact = true,
  ...properties
}: NamedRemoteStateProperties) {
  return <RemoteState compact={compact} kind="reconnecting" {...properties} />;
}

export type RemoteDataBoundaryProperties = Omit<HTMLAttributes<HTMLDivElement>, "children"> &
  Readonly<{
    children: ReactNode;
    isLoading?: boolean;
    isRefetching?: boolean;
    keepPreviousData?: boolean;
    loadingFallback?: ReactNode;
    refetchLabel?: string;
  }>;

export function RemoteDataBoundary({
  children,
  className,
  isLoading = false,
  isRefetching = false,
  keepPreviousData = true,
  loadingFallback,
  refetchLabel = "Actualisation des données",
  ...properties
}: RemoteDataBoundaryProperties) {
  if (isLoading || (isRefetching && !keepPreviousData)) {
    return <>{loadingFallback ?? <RemoteLoadingState />}</>;
  }

  return (
    <div
      aria-busy={isRefetching}
      className={cn("relative", className)}
      data-refetching={isRefetching ? "true" : "false"}
      {...properties}
    >
      {isRefetching ? (
        <div
          aria-label={refetchLabel}
          className="pointer-events-none absolute right-3 top-3 z-10"
          role="status"
        >
          <span className="inline-flex min-h-7 items-center rounded-full border border-border-strong bg-surface-raised px-3 text-xs font-semibold text-ink-secondary shadow-sm">
            {refetchLabel}
          </span>
        </div>
      ) : null}
      {children}
    </div>
  );
}
