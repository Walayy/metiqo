import { useEffect, useState } from 'react';

export const minimumLoadingMs = 1200;

/** Presentation only: requests start immediately and retain their cancellation/retry policy. */
export function useMinimumLoading(pending: boolean, selection: string) {
  const [phase, setPhase] = useState({ selection, pending, revision: 0, elapsed: false });
  const changed = selection !== phase.selection || (pending && !phase.pending);
  // Reset before React commits a changed selection, including cache hits and back navigation.
  if (changed) {
    setPhase({ selection, pending, revision: phase.revision + 1, elapsed: false });
  } else if (pending !== phase.pending) {
    setPhase({ ...phase, pending });
  }
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPhase((current) =>
        current.revision === phase.revision ? { ...current, elapsed: true } : current,
      );
    }, minimumLoadingMs);
    return () => window.clearTimeout(timer);
  }, [phase.revision]);
  return pending || changed || !phase.elapsed;
}
