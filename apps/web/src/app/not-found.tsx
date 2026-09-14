import { Button } from "@metiquo/ui";
import Link from "next/link";

export default function NotFound() {
  return (
    <section className="ui-page-stack max-w-xl py-8" aria-labelledby="not-found-title">
      <p className="ui-eyebrow">Erreur 404</p>
      <h1 className="ui-page-title" id="not-found-title">
        Page introuvable
      </h1>
      <p className="text-body text-ink-secondary">
        Cette adresse ne correspond à aucune page. Retrouvez les opportunités ou utilisez la
        navigation.
      </p>
      <Button asChild className="justify-self-start">
        <Link href="/">Revenir aux opportunités</Link>
      </Button>
    </section>
  );
}
