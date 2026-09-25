import type { Page } from '@playwright/test';

// Deliberately synthetic API responses, confined to browser tests.
export async function installWorkerLogsFixture(page: Pick<Page, 'addInitScript'>) {
  await page.addInitScript(
    ({ requestedAt, selectedRun }) => {
      const run = {
        id: selectedRun,
        scriptId: 'stake-markets',
        trigger: 'schedule',
        status: 'succeeded',
        requestedAt,
        startedAt: requestedAt,
        finishedAt: '2026-09-25T16:28:00Z',
        error: null,
        complete: false,
        summary: { eventsCollected: 18, quotes: 1234, eventsFailed: 1, snapshots: 18 },
        eventErrors: [{ eventId: '845833', reason: 'Ambiguous source market identity' }],
        interruption: null,
        deferredReason: null,
        statusCorrection: null,
      };
      const recent = {
        id: selectedRun,
        scriptId: 'stake-markets',
        name: 'Stake · cotes pré-match et direct',
        status: 'succeeded',
        requestedAt,
      };
      const lines = [
        {
          id: 101,
          workerId: 2,
          scriptId: 'stake-markets',
          runId: selectedRun,
          recordedAt: requestedAt,
          level: 'info',
          stage: 'exécution',
          message: 'Exécution démarrée.',
          eventId: null,
          context: {},
        },
        {
          id: 102,
          workerId: 2,
          scriptId: 'stake-markets',
          runId: selectedRun,
          recordedAt: '2026-09-25T16:22:00Z',
          level: 'warning',
          stage: 'publication',
          message: 'Rencontre non publiée : identité de marché ambiguë.',
          eventId: '845833',
          context: { kind: 'ValueError' },
        },
        {
          id: 103,
          workerId: 2,
          scriptId: 'stake-markets',
          runId: selectedRun,
          recordedAt: '2026-09-25T16:28:00Z',
          level: 'error',
          stage: 'collecte',
          message: 'Passage Stake interrompu après erreur.',
          eventId: null,
          context: { kind: 'RuntimeError', frames: ['stake_browser.py:event:358'] },
        },
      ];
      Object.assign(window, { __workerLogsFixture: { run, lines } });
      const originalFetch = window.fetch.bind(window);
      window.fetch = (input, init) => {
        const url = new URL(input instanceof Request ? input.url : String(input), location.href);
        const json = (body: object) =>
          Promise.resolve(
            new Response(JSON.stringify(body), {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            }),
          );
        if (url.pathname === '/api/v1/auth/session') {
          return json({
            user: {
              id: '11111111-1111-4111-8111-111111111111',
              email: 'admin@example.test',
              role: 'admin',
              createdAt: requestedAt,
            },
            expiresAt: '2026-12-01T00:00:00Z',
          });
        }
        if (url.pathname === '/api/v1/admin/scripts') {
          return json({
            worker: { online: true, lastSeenAt: requestedAt },
            workers: [
              {
                id: 1,
                name: 'Collectes sportives',
                online: false,
                lastSeenAt: requestedAt,
                activeRuns: [],
              },
              {
                id: 2,
                name: 'Cotes Stake',
                online: true,
                lastSeenAt: requestedAt,
                activeRuns: [],
              },
              {
                id: 3,
                name: 'Résultats des sélections',
                online: false,
                lastSeenAt: null,
                activeRuns: [],
              },
            ],
            items: [
              ...[
                {
                  id: 'lol-catalog',
                  family: 'LoL',
                  name: 'Catalogue League of Legends',
                  cron: '0 4 * * *',
                },
                {
                  id: 'loltv-matches',
                  family: 'LoL',
                  name: 'LoLTV · matchs LoL',
                  cron: '* * * * *',
                },
                {
                  id: 'oracle-latest',
                  family: 'Oracle’s Elixir',
                  name: 'Oracle’s Elixir · saison récente',
                  cron: '0 */6 * * *',
                },
                {
                  id: 'oracle-full',
                  family: 'Oracle’s Elixir',
                  name: 'Oracle’s Elixir · historique complet',
                  cron: '0 3 * * 0',
                },
                {
                  id: 'settle-selections',
                  family: 'Stake',
                  name: 'Résultats des sélections Stake',
                  cron: '* * * * *',
                },
              ].map((script) => ({
                ...script,
                workerId: script.id === 'settle-selections' ? 3 : 1,
                description: 'Description de collecte pour le test de présentation.',
                command: script.id,
                timezone: 'Europe/Paris',
                enabled: script.id !== 'oracle-full',
                revision: 1,
                nextRunAt: '2026-09-26T02:00:00Z',
                upcoming: [],
                available: script.id !== 'settle-selections',
                activeRun: null,
                runs: [],
              })),
              {
                id: 'stake-markets',
                workerId: 2,
                family: 'Stake',
                name: 'Stake · cotes pré-match et direct',
                description: 'Historise les cotes.',
                command: 'sync-stake-markets',
                cron: '*/20 * * * *',
                timezone: 'Europe/Paris',
                enabled: true,
                revision: 1,
                nextRunAt: '2026-09-25T16:40:00Z',
                upcoming: [],
                available: true,
                activeRun: null,
                runs: [run],
              },
            ],
          });
        }
        if (url.pathname === '/api/v1/admin/worker-logs') {
          const workerId = Number(url.searchParams.get('workerId'));
          const selected = url.searchParams.get('runId');
          const level = url.searchParams.get('level');
          const q = url.searchParams.get('q')?.toLowerCase();
          const after = Number(url.searchParams.get('after') || 0);
          const before = Number(url.searchParams.get('before') || 0);
          const entries = lines.filter(
            (line) =>
              line.workerId === workerId &&
              (!selected || line.runId === selected) &&
              (!level || line.level === level) &&
              (!q ||
                `${line.message} ${line.stage} ${line.eventId ?? ''}`.toLowerCase().includes(q)) &&
              (!after || line.id > after) &&
              (!before || line.id < before),
          );
          return json({
            items: entries,
            incidents: lines
              .filter((line) => line.workerId === workerId && line.level !== 'info')
              .reverse(),
            hasMore: false,
            recentRuns: workerId === 2 ? [recent] : [],
            run: selected ? run : null,
          });
        }
        return originalFetch(input, init);
      };
    },
    { requestedAt: '2026-09-25T16:20:00Z', selectedRun: '22222222-2222-4222-8222-222222222222' },
  );
}
