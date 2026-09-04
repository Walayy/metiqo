import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from "@metiquo/ui";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl items-center px-6 py-12">
      <Card className="w-full">
        <CardHeader>
          <Badge>Fondation UI</Badge>
          <CardTitle className="text-title">Metiquo</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-6">
          <p className="text-body max-w-2xl text-ink-secondary">
            Une lecture probabiliste, traçable et prudente des marchés League of Legends.
          </p>
          <div>
            <Button type="button">Explorer le design system</Button>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
