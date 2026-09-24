import { useSyncExternalStore } from 'react';

// One clock for the small labels that actually change. The surrounding page,
// tables and tooltips do not render again when a second passes.
let now = Date.now();
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | undefined;
function tick() {
  if (document.visibilityState !== 'visible') return;
  now = Date.now();
  for (const listener of listeners) listener();
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) {
    now = Date.now();
    timer = setInterval(tick, 1000);
    document.addEventListener('visibilitychange', tick);
  }
  return () => {
    listeners.delete(listener);
    if (!listeners.size) {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', tick);
    }
  };
}
export function useClockText(format: (now: number) => string) {
  return useSyncExternalStore(subscribe, () => format(now));
}
