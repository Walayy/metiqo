import { RemoteLoadingState } from "@metiquo/ui";
import { Suspense } from "react";

import { ModelsDashboard } from "../../components/models-dashboard";

export default function ModelsPage() {
  return (
    <Suspense
      fallback={<RemoteLoadingState label="Chargement des modèles" minHeight="32rem" rows={8} />}
    >
      <ModelsDashboard />
    </Suspense>
  );
}
