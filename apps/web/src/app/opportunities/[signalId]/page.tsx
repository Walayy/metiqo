import { RemotePageLoadingState } from "@metiquo/ui";
import { Suspense } from "react";

import { SignalDetail } from "../../../components/signal-detail";

export const metadata = { title: "Détail du signal · Metiquo" };

type SignalDetailPageProperties = Readonly<{
  params: Promise<Readonly<{ signalId: string }>>;
}>;

export default async function SignalDetailPage({ params }: SignalDetailPageProperties) {
  const { signalId } = await params;

  return (
    <Suspense fallback={<RemotePageLoadingState label="Chargement du signal" />}>
      <SignalDetail signalId={signalId} />
    </Suspense>
  );
}
