import { RemoteLoadingState } from "@metiquo/ui";
import { Suspense } from "react";

import { EventDetail } from "../../../components/event-detail";

type EventDetailPageProperties = Readonly<{
  params: Promise<Readonly<{ eventId: string }>>;
}>;

export default async function EventDetailPage({ params }: EventDetailPageProperties) {
  const { eventId } = await params;

  return (
    <Suspense
      fallback={<RemoteLoadingState label="Chargement de l’événement" minHeight="32rem" rows={8} />}
    >
      <EventDetail eventId={eventId} />
    </Suspense>
  );
}
