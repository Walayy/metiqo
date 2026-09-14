import { RemotePageLoadingState } from "@metiquo/ui";
import { Suspense } from "react";
import type { Metadata } from "next";

import { AdminOperationsDashboard } from "../../components/data-health-dashboard";

export const metadata: Metadata = { title: "Administration · Metiquo" };

export default function AdminPage() {
  return (
    <Suspense fallback={<RemotePageLoadingState label="Chargement de l’administration" />}>
      <AdminOperationsDashboard />
    </Suspense>
  );
}
