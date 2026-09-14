import { RemotePageLoadingState } from "@metiquo/ui";
import { Suspense } from "react";

import { PaperTradingDashboard } from "../../components/paper-trading-dashboard";

export const metadata = { title: "Paper trading · Metiquo" };

export default function PaperTradingPage() {
  return (
    <Suspense fallback={<RemotePageLoadingState label="Chargement du paper trading" />}>
      <PaperTradingDashboard />
    </Suspense>
  );
}
