import { config } from './config';
export const transportReady = (async () => {
  if (config.dataMode === 'mock') {
    const { worker } = await import('@/mocks/browser');
    await worker.start({
      onUnhandledRequest: 'bypass',
      quiet: true,
      serviceWorker: { url: '/mockServiceWorker.js' },
    });
  } else if ('serviceWorker' in navigator) {
    const registrations = await navigator.serviceWorker.getRegistrations();
    await Promise.all(
      registrations
        .filter(
          (r) => r.active?.scriptURL === new URL('/mockServiceWorker.js', location.origin).href,
        )
        .map((r) => r.unregister()),
    );
  }
})();
