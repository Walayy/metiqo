import { RemotePageLoadingState } from "@metiquo/ui";
import { Suspense } from "react";

import { EventDetail } from "../../../components/event-detail";

export const metadata = { title: "Détail de l’événement · Metiquo" };

type EventDetailPageProperties = Readonly<{
  params: Promise<Readonly<{ eventId: string }>>;
}>;

export default async function EventDetailPage({ params }: EventDetailPageProperties) {
  const { eventId } = await params;

  return (
    <Suspense fallback={<RemotePageLoadingState label="Chargement de l’événement" />}>
      <EventDetail eventId={eventId} />
    </Suspense>
  );
}
