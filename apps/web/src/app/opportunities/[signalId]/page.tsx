import { RemoteLoadingState } from "@metiquo/ui";
import { Suspense } from "react";

import { SignalDetail } from "../../../components/signal-detail";

type SignalDetailPageProperties = Readonly<{
  params: Promise<Readonly<{ signalId: string }>>;
}>;

export default async function SignalDetailPage({ params }: SignalDetailPageProperties) {
  const { signalId } = await params;

  return (
    <Suspense
      fallback={<RemoteLoadingState label="Chargement du signal" minHeight="32rem" rows={8} />}
    >
      <SignalDetail signalId={signalId} />
    </Suspense>
  );
}
