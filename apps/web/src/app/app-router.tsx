import { useSyncExternalStore } from 'react';
import { HttpError } from '@/lib/http-error';
import { StatusPage } from '@/features/status/status-panel';
import { isKnownLocation } from '@/features/status/status-model';
import { App } from './app';

function subscribe(callback: () => void) {
  window.addEventListener('popstate', callback);
  return () => window.removeEventListener('popstate', callback);
}
export function AppRouter() {
  const known = useSyncExternalStore(subscribe, () =>
    isKnownLocation(location.pathname, location.search),
  );
  return known ? <App /> : <StatusPage error={new HttpError(404)} />;
}
