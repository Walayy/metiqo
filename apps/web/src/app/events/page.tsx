import { RemotePageLoadingState } from "@metiquo/ui";
import { Suspense } from "react";

import { EventsExplorer } from "../../components/events-explorer";

export const metadata = { title: "Événements · Metiquo" };

export default function EventsPage() {
  return (
    <Suspense fallback={<RemotePageLoadingState label="Chargement des événements" />}>
      <EventsExplorer />
    </Suspense>
  );
}
