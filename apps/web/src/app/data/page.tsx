import { RemotePageLoadingState } from "@metiquo/ui";
import { Suspense } from "react";
import type { Metadata } from "next";

import { DataHealthDashboard } from "../../components/data-health-dashboard";

export const metadata: Metadata = { title: "Santé des données · Metiquo" };

export default function DataPage() {
  return (
    <Suspense fallback={<RemotePageLoadingState label="Chargement des données" />}>
      <DataHealthDashboard />
    </Suspense>
  );
}
