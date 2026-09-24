import { useEffect, useState } from 'react';

// Keep conditionally rendered dialogs mounted long enough for Radix's exit animation.
export function useDialogPresence<T>(active: T | null): T | null {
  const [retained, setRetained] = useState<T | null>(active);
  useEffect(() => {
    const timer = window.setTimeout(() => setRetained(active), active === null ? 240 : 0);
    return () => window.clearTimeout(timer);
  }, [active]);
  return active ?? retained;
}
