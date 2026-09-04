import { Suspense } from "react";

import { PaperTradingDashboard } from "../../components/paper-trading-dashboard";

export default function PaperTradingPage() {
  return (
    <Suspense fallback={<div className="min-h-[32rem]" />}>
      <PaperTradingDashboard />
    </Suspense>
  );
}
