import { Suspense } from "react";

import { DataHealthDashboard } from "../../components/data-health-dashboard";

export default function DataPage() {
  return (
    <Suspense fallback={<div className="min-h-[32rem]" />}>
      <DataHealthDashboard />
    </Suspense>
  );
}
