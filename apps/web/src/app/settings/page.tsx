import { ReleaseCompliancePanel } from "../../components/release-compliance-panel";

export default function SettingsPage() {
  return (
    <div className="grid gap-8">
      <header className="grid max-w-3xl gap-3">
        <h1 className="text-title font-semibold tracking-tight">Paramètres</h1>
        <p className="text-body text-ink-secondary">
          Le thème se règle depuis la navigation. Les conditions de publication restent visibles
          ici.
        </p>
        <p className="text-sm font-medium">Metiquo ne garantit aucun gain.</p>
      </header>
      <ReleaseCompliancePanel />
    </div>
  );
}
