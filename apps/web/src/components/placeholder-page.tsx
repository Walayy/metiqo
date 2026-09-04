import { Badge, Card, CardContent } from "@metiquo/ui";

type PlaceholderPageProperties = Readonly<{
  description: string;
  eyebrow: string;
  title: string;
}>;

export function PlaceholderPage({ description, eyebrow, title }: PlaceholderPageProperties) {
  return (
    <div className="grid gap-8">
      <header className="grid max-w-3xl gap-3">
        <Badge>{eyebrow}</Badge>
        <h1 className="text-title text-balance font-semibold tracking-tight">{title}</h1>
        <p className="text-body max-w-2xl text-ink-secondary">{description}</p>
      </header>
      <Card aria-labelledby="workspace-title">
        <CardContent className="grid min-h-56 place-items-center text-center">
          <div className="grid max-w-md gap-2">
            <h2 className="text-lg font-semibold" id="workspace-title">
              Espace prêt
            </h2>
            <p className="text-sm leading-6 text-ink-secondary">
              Le shell, le thème et les contrats sont en place. Les données métier de cette vue
              arrivent dans le ticket écran dédié.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
