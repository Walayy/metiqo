import { Suspense } from "react";

import { AdminOperationsDashboard } from "../../components/data-health-dashboard";

export default function AdminPage() {
  return (
    <Suspense fallback={<div className="min-h-[32rem]" />}>
      <AdminOperationsDashboard />
    </Suspense>
  );
}
