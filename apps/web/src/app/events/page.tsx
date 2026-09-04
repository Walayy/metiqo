import { RemoteLoadingState } from "@metiquo/ui";
import { Suspense } from "react";

import { EventsExplorer } from "../../components/events-explorer";

export default function EventsPage() {
  return (
    <Suspense
      fallback={<RemoteLoadingState label="Chargement des événements" minHeight="32rem" rows={8} />}
    >
      <EventsExplorer />
    </Suspense>
  );
}
