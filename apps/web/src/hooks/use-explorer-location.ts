import { useEffect, useRef, useState } from 'react';
import { readExplorerLocation, writeExplorerLocation } from '@/features/values/explorer-location';
import type { ExplorerLocation } from '@/features/values/explorer-location';

export function useExplorerLocation() {
  const [state, setState] = useState(() =>
    readExplorerLocation(new URLSearchParams(location.search)),
  );
  const initialized = useRef(false);
  useEffect(() => {
    function restore() {
      const next = readExplorerLocation(new URLSearchParams(location.search));
      // Retain the previous item through the drawer's closing animation.
      setState((previous) => ({ ...next, selectedId: next.selectedId ?? previous.selectedId }));
    }
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, []);
  useEffect(() => {
    const url = new URL(location.href);
    const next = writeExplorerLocation(url.searchParams, state);
    const before = new URLSearchParams(url.searchParams);
    before.delete('q');
    before.delete('page');
    const after = new URLSearchParams(next);
    after.delete('q');
    after.delete('page');
    const searchOnly =
      state.search !== (url.searchParams.get('q') ?? '') && before.toString() === after.toString();
    if (url.searchParams.toString() !== next.toString()) {
      url.search = next.toString();
      if (!initialized.current || searchOnly) history.replaceState(null, '', url);
      else history.pushState(null, '', url);
    }
    initialized.current = true;
  }, [state]);
  function update(patch: Partial<ExplorerLocation>) {
    setState((previous) => ({ ...previous, ...patch }));
  }
  return [state, update] as const;
}
