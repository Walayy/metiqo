import { Badge, Card, CardContent } from "@metiquo/ui";

type PlaceholderPageProperties = Readonly<{
  description: string;
  eyebrow: string;
  title: string;
}>;

export function PlaceholderPage({ description, eyebrow, title }: PlaceholderPageProperties) {
  return (
    <div className="ui-page-stack">
      <header className="grid max-w-3xl gap-3">
        <Badge>{eyebrow}</Badge>
        <h1 className="ui-page-title">{title}</h1>
        <p className="text-body max-w-2xl text-ink-secondary">{description}</p>
      </header>
      <Card aria-labelledby="workspace-title">
        <CardContent className="grid min-h-56 place-items-center text-center">
          <div className="grid max-w-md gap-2">
            <h2 className="text-lg font-semibold" id="workspace-title">
              Vue en préparation
            </h2>
            <p className="text-sm leading-6 text-ink-secondary">
              Cette vue ne contient pas encore de données. Retrouvez les informations disponibles
              dans les autres rubriques de l’application.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
