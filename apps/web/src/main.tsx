import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MotionConfig } from 'motion/react';
import './styles/fonts.css';
import './styles/globals.css';
import './styles/interactions.css';
import { AppRouter } from './app/app-router';
import { isKnownLocation } from './features/status/status-model';
import { retryRead } from './lib/http-error';
import { ErrorBoundary } from './app/error-boundary';
import { RevealApp } from './app/reveal-app';
import { catalogQuery, matchesQuery, opportunitiesQuery, performanceQuery } from './lib/api';
import './styles/experience.css';
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: retryRead, retryOnMount: false, refetchOnWindowFocus: false },
  },
});
async function prepareFonts() {
  // A slow font must never freeze startup or replace visible text later.
  // font-display: optional keeps the fallback stable if this budget is exceeded.
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const loaded = await Promise.race([
      Promise.all([
        document.fonts.load('500 14px "Inter Variable"'),
        document.fonts.load('600 24px "Manrope Variable"'),
      ]).then(() => true),
      new Promise<boolean>((resolve) => {
        timer = setTimeout(() => resolve(false), 2000);
      }),
    ]);
    if (!loaded) document.documentElement.dataset.fonts = 'fallback';
  } catch (error) {
    console.warn('Polices locales indisponibles, utilisation de la police système.', error);
    document.documentElement.dataset.fonts = 'fallback';
  } finally {
    clearTimeout(timer);
  }
}

// Warm the shared cache, but never hold the interface behind a slow API.
const initialData = Promise.all(
  isKnownLocation(location.pathname, location.search)
    ? [
        queryClient.prefetchQuery(catalogQuery),
        new URLSearchParams(location.search).get('view') === 'matches'
          ? queryClient.prefetchQuery(matchesQuery)
          : new URLSearchParams(location.search).get('view') === 'performance'
            ? queryClient.prefetchQuery(performanceQuery)
            : queryClient.prefetchQuery(opportunitiesQuery),
      ]
    : [],
);
let dataTimer: ReturnType<typeof setTimeout> | undefined;
await Promise.all([
  prepareFonts(),
  Promise.race([
    initialData,
    new Promise<void>((resolve) => {
      dataTimer = setTimeout(resolve, 700);
    }),
  ]),
]);
clearTimeout(dataTimer);
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RevealApp />
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <MotionConfig reducedMotion="user">
          <AppRouter />
        </MotionConfig>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
);
