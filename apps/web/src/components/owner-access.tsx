"use client";

import { readBackend, requestBackend } from "../lib/backend";

import type { AuthStatus } from "@metiquo/contracts/types";
import {
  Button,
  Card,
  CardContent,
  RemoteLoadingState,
  RemoteRecoverableErrorState,
} from "@metiquo/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode, type SubmitEventHandler } from "react";

const SESSION_KEY = ["owner-session"] as const;
const AUTH_URL = "/api/backend/api/v1/auth";

async function sessionStatus(): Promise<AuthStatus> {
  const response = await readBackend(`${AUTH_URL}/session`, {
    cache: "no-store",
    credentials: "same-origin",
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error("Le service de connexion ne répond pas.");
  return response.json() as Promise<AuthStatus>;
}

export function OwnerAccess({ children }: Readonly<{ children: ReactNode }>) {
  const queryClient = useQueryClient();
  const session = useQuery({
    queryKey: SESSION_KEY,
    queryFn: sessionStatus,
    staleTime: 0,
    refetchOnWindowFocus: true,
    retry: false,
  });
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (session.data?.mode === "owner" && !session.data.authenticated) {
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== SESSION_KEY[0] });
    }
  }, [queryClient, session.data]);

  async function login() {
    setPending(true);
    setError(null);
    try {
      const response = await requestBackend(`${AUTH_URL}/login`, {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        headers: { "content-type": "application/json", "X-Metiquo-CSRF": "1" },
        body: JSON.stringify({ username, password }),
        signal: AbortSignal.timeout(15_000),
      });
      if (!response.ok) {
        setError(
          response.status === 401
            ? "Identifiants incorrects. Réessayez."
            : "Connexion indisponible. Réessayez dans quelques instants.",
        );
        return;
      }
      queryClient.setQueryData(SESSION_KEY, (await response.json()) as AuthStatus);
    } catch {
      setError("Le service de connexion ne répond pas.");
    } finally {
      setPassword("");
      setPending(false);
    }
  }
  const submit: SubmitEventHandler<HTMLFormElement> = (event) => {
    event.preventDefault();
    void login();
  };

  async function logout() {
    setPending(true);
    setError(null);
    try {
      const response = await requestBackend(`${AUTH_URL}/logout`, {
        headers: { "X-Metiquo-CSRF": "1" },
        method: "POST",
        credentials: "same-origin",
        signal: AbortSignal.timeout(15_000),
      });
      if (!response.ok) throw new Error("logout failed");
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== SESSION_KEY[0] });
      queryClient.setQueryData(SESSION_KEY, {
        mode: "owner",
        authenticated: false,
        owner: null,
      } satisfies AuthStatus);
    } catch {
      setError("Déconnexion impossible pour le moment. Réessayez.");
    } finally {
      setPending(false);
    }
  }

  if (session.isPending)
    return <RemoteLoadingState label="Vérification de la connexion" minHeight="32rem" rows={8} />;
  if (session.isError && session.data?.mode !== "disabled")
    return (
      <RemoteRecoverableErrorState
        title="Connexion indisponible"
        description="Le service de connexion ne répond pas."
        onRetry={() => void session.refetch()}
      />
    );
  if (session.data?.mode === "disabled")
    return (
      <>
        {session.isError ? (
          <RemoteRecoverableErrorState
            compact
            className="mb-6"
            title="Actualisation indisponible"
            description="La vérification du service est indisponible. La dernière lecture locale reste affichée."
            onRetry={() => void session.refetch()}
            retryDisabled={session.isFetching}
          />
        ) : null}
        {children}
      </>
    );
  if (session.data?.authenticated)
    return (
      <>
        <div className="mb-6 flex min-h-11 items-center justify-end gap-4">
          <span className="text-sm text-ink-secondary">Owner · {session.data.owner?.username}</span>
          <Button disabled={pending} onClick={() => void logout()} variant="outline">
            Déconnexion
          </Button>
        </div>
        {error && (
          <p className="mb-4 text-sm text-ink-primary" role="alert">
            {error}
          </p>
        )}
        {children}
      </>
    );

  return (
    <Card className="mx-auto mt-12 w-full max-w-md">
      <CardContent className="p-6 sm:p-8">
        <h1 className="text-2xl font-semibold tracking-tight text-ink-primary">Connexion Owner</h1>
        <p className="mt-2 text-sm text-ink-secondary">
          Connectez-vous pour accéder à votre espace.
        </p>
        <form className="mt-6 grid gap-5" onSubmit={submit}>
          <label className="grid gap-2 text-sm font-medium">
            Identifiant
            <input
              autoComplete="username"
              className="min-h-11 rounded-md border border-border-strong bg-surface-raised px-3 outline-none focus-visible:outline-2 focus-visible:outline-focus"
              maxLength={64}
              onChange={(event) => {
                setUsername(event.target.value);
              }}
              required
              value={username}
            />
          </label>
          <label className="grid gap-2 text-sm font-medium">
            Mot de passe
            <input
              autoComplete="current-password"
              className="min-h-11 rounded-md border border-border-strong bg-surface-raised px-3 outline-none focus-visible:outline-2 focus-visible:outline-focus"
              maxLength={1024}
              onChange={(event) => {
                setPassword(event.target.value);
              }}
              required
              type="password"
              value={password}
            />
          </label>
          {error && (
            <p className="text-sm text-ink-primary" role="alert">
              {error}
            </p>
          )}
          <Button disabled={pending} type="submit">
            {pending ? "Connexion…" : "Se connecter"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
