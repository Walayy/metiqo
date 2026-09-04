import { Suspense } from "react";
import { RemoteLoadingState } from "@metiquo/ui";

import { OpportunitiesDashboard } from "../components/opportunities-dashboard";

export default function HomePage() {
  return (
    <Suspense
      fallback={<RemoteLoadingState label="Chargement du dashboard" minHeight="32rem" rows={8} />}
    >
      <OpportunitiesDashboard />
    </Suspense>
  );
}
