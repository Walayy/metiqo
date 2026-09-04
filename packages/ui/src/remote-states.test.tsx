import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  RemoteBlockingErrorState,
  RemoteDataBoundary,
  RemoteEmptyState,
  RemoteLoadingState,
  RemoteMockState,
  RemoteOfflineState,
  RemotePermissionDeniedState,
  RemoteRecoverableErrorState,
  RemoteReconnectingState,
  RemoteSkeleton,
  RemoteStaleState,
} from "./remote-states";

const stateMatrix: readonly (readonly [
  state: string,
  title: string,
  role: "alert" | "status",
  component: ReactElement,
])[] = [
  ["empty", "Aucune donnée", "status", <RemoteEmptyState />],
  [
    "recoverable-error",
    "Actualisation impossible",
    "alert",
    <RemoteRecoverableErrorState key="recoverable-error" onRetry={() => undefined} />,
  ],
  ["blocking-error", "Données indisponibles", "alert", <RemoteBlockingErrorState />],
  ["stale", "Données anciennes", "status", <RemoteStaleState />],
  ["permission-denied", "Accès refusé", "alert", <RemotePermissionDeniedState />],
  ["mock", "Données simulées", "status", <RemoteMockState />],
  ["offline", "Hors connexion", "status", <RemoteOfflineState />],
  ["reconnecting", "Reconnexion en cours", "status", <RemoteReconnectingState />],
];

afterEach(cleanup);

describe("remote state library", () => {
  it.each(stateMatrix)(
    "renders the %s state with an accessible message",
    (state, title, role, component) => {
      const { container } = render(component);

      expect(screen.getByRole(role)).toHaveAttribute("data-remote-state", state);
      expect(screen.getByRole("heading", { name: title, level: 2 })).toBeInTheDocument();
      expect(container.querySelector("svg")).not.toBeInTheDocument();
    },
  );

  it("renders loading skeletons with reserved dimensions and no spinner", () => {
    const { container } = render(<RemoteLoadingState minHeight="18rem" rows={4} />);

    const loading = screen.getByRole("status", { name: "Chargement des données" });
    expect(loading).toHaveAttribute("aria-busy", "true");
    expect(loading).toHaveStyle({ minHeight: "18rem" });
    expect(container.querySelectorAll('[data-remote-skeleton="true"]')).toHaveLength(5);
    expect(container.querySelector('[role="progressbar"]')).not.toBeInTheDocument();
  });

  it("lets each skeleton reserve exact width and height", () => {
    render(<RemoteSkeleton height={48} width="75%" />);

    expect(document.querySelector('[data-remote-skeleton="true"]')).toHaveStyle({
      blockSize: "48px",
      inlineSize: "75%",
    });
  });

  it("offers a keyboard-accessible retry for recoverable errors", async () => {
    const user = userEvent.setup();
    const handleRetry = vi.fn();
    render(<RemoteRecoverableErrorState onRetry={handleRetry} />);

    const retry = screen.getByRole("button", { name: "Réessayer" });
    await user.tab();
    expect(retry).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(handleRetry).toHaveBeenCalledOnce();
  });

  it("keeps safe previous content visible while a refetch is in progress", () => {
    render(
      <RemoteDataBoundary isRefetching>
        <p>Dernier snapshot validé</p>
      </RemoteDataBoundary>,
    );

    expect(screen.getByText("Dernier snapshot validé")).toBeVisible();
    expect(screen.getByRole("status", { name: "Actualisation des données" })).toBeInTheDocument();
    expect(screen.getByText("Dernier snapshot validé").parentElement).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });

  it("uses the reserved loading fallback for an initial load or an unsafe refetch", () => {
    const { rerender } = render(
      <RemoteDataBoundary isLoading loadingFallback={<p>Emplacement réservé</p>}>
        <p>Contenu absent</p>
      </RemoteDataBoundary>,
    );

    expect(screen.getByText("Emplacement réservé")).toBeInTheDocument();
    expect(screen.queryByText("Contenu absent")).not.toBeInTheDocument();

    rerender(
      <RemoteDataBoundary
        isRefetching
        keepPreviousData={false}
        loadingFallback={<p>Rechargement sûr</p>}
      >
        <p>Contenu sensible</p>
      </RemoteDataBoundary>,
    );

    expect(screen.getByText("Rechargement sûr")).toBeInTheDocument();
    expect(screen.queryByText("Contenu sensible")).not.toBeInTheDocument();
  });
});
