import { Suspense } from "react";
import { RemotePageLoadingState } from "@metiquo/ui";

import { OpportunitiesDashboard } from "../components/opportunities-dashboard";

export const metadata = { title: "Opportunités · Metiquo" };

export default function HomePage() {
  return (
    <Suspense fallback={<RemotePageLoadingState label="Chargement du dashboard" />}>
      <OpportunitiesDashboard />
    </Suspense>
  );
}
