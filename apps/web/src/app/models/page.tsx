import { RemotePageLoadingState } from "@metiquo/ui";
import { Suspense } from "react";
import type { Metadata } from "next";

import { ModelsDashboard } from "../../components/models-dashboard";

export const metadata: Metadata = { title: "Modèles & backtests · Metiquo" };

export default function ModelsPage() {
  return (
    <Suspense fallback={<RemotePageLoadingState label="Chargement des modèles" />}>
      <ModelsDashboard />
    </Suspense>
  );
}
