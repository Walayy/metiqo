"use client";

import { Button } from "@metiquo/ui";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTransition } from "react";

export default function ErrorPage({ retry }: Readonly<{ retry: () => void }>) {
  const queryClient = useQueryClient();
  const [pending, startTransition] = useTransition();
  return (
    <section className="ui-page-stack max-w-xl py-8" aria-labelledby="error-title">
      <h1 className="ui-page-title" id="error-title">
        Impossible d’afficher cette page
      </h1>
      <p className="text-body text-ink-secondary" role="alert">
        Une erreur inattendue a interrompu l’affichage. Vous pouvez réessayer ou revenir aux
        opportunités.
      </p>
      <div className="ui-toolbar">
        <Button
          aria-disabled={pending}
          aria-busy={pending}
          onClick={() => {
            startTransition(async () => {
              await queryClient.resetQueries({
                predicate: (query) => query.queryKey[0] !== "owner-session",
              });
              retry();
            });
          }}
        >
          {pending ? "Nouvelle tentative…" : "Réessayer"}
        </Button>
        <Button asChild variant="secondary">
          <Link href="/">Revenir aux opportunités</Link>
        </Button>
      </div>
    </section>
  );
}
