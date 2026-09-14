import { TitledCard } from "@metiquo/ui";
import type { Metadata } from "next";

import { ReleaseCompliancePanel } from "../../components/release-compliance-panel";
import { ThemeMenu } from "../../components/theme-menu";

export const metadata: Metadata = { title: "Paramètres · Metiquo" };

export default function SettingsPage() {
  return (
    <div className="ui-page-stack">
      <header className="grid max-w-3xl gap-3">
        <h1 className="ui-page-title">Paramètres</h1>
        <p className="text-body text-ink-secondary">
          Personnalisez l’apparence et consultez les conditions de publication de Metiquo.
        </p>
        <p className="text-sm font-medium">Metiquo ne garantit aucun gain.</p>
      </header>
      <TitledCard title="Apparence">
        <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm leading-6 text-ink-secondary">
            Choisissez un thème clair, sombre ou adapté aux réglages de votre appareil.
          </p>
          <ThemeMenu ariaLabel="Choisir l’apparence" showLabel />
        </div>
      </TitledCard>
      <ReleaseCompliancePanel />
    </div>
  );
}
