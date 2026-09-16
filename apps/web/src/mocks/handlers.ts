import { delay, http, HttpResponse } from 'msw';
import { catalog, opportunities } from './fixtures';
import { config } from '@/lib/config';
import { matches, performance } from './esport';

// QA scenarios are opt-in URL parameters, available only in mock mode.
const scenario = new URLSearchParams(window.location.search).get('mock');
let failures = 0;
export const handlers = [
  ...[
    { path: '/matches', data: matches },
    { path: '/performance', data: performance },
  ].map(({ path, data }) =>
    http.get(`${config.apiBaseUrl}${path}`, async () => {
      await delay(scenario === 'slow' ? 3000 : 400);
      if (scenario === 'error' && failures++ < 2)
        return HttpResponse.json({ message: 'Erreur simulée' }, { status: 503 });
      return HttpResponse.json({ ...data, items: scenario === 'empty' ? [] : data.items });
    }),
  ),
  http.get(`${config.apiBaseUrl}/catalog`, async () => {
    await delay(250);
    return HttpResponse.json(catalog);
  }),
  http.get(`${config.apiBaseUrl}/opportunities`, async () => {
    await delay(scenario === 'slow' ? 3000 : 650);
    // Two failures cover the initial request and the single automatic retry.
    if (scenario === 'error' && failures++ < 2)
      return HttpResponse.json({ message: 'Erreur simulée' }, { status: 503 });
    return HttpResponse.json({
      ...opportunities,
      generatedAt: new Date().toISOString(),
      items: scenario === 'empty' ? [] : opportunities.items,
    });
  }),
];
