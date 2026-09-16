import { z } from 'zod';

const count = z.number().int().nonnegative();
export const playerSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  role: z.enum(['TOP', 'JGL', 'MID', 'BOT', 'SUP']),
  champion: z.string().min(1),
  championImage: z.string(),
  kills: count,
  deaths: count,
  assists: count,
  cs: count,
  gold: count,
});
const sideSchema = z
  .object({
    teamId: z.string(),
    side: z.enum(['blue', 'red']),
    towers: count.max(11),
    dragons: count,
    barons: count,
    players: z.array(playerSchema).length(5),
  })
  .refine(
    (side) =>
      new Set(side.players.map((p) => p.role)).size === 5 &&
      new Set(side.players.map((p) => p.id)).size === 5,
    'Une composition contient cinq rôles et joueurs distincts.',
  );
const mapSchema = z
  .object({
    number: z.number().int().min(1).max(5),
    status: z.enum(['scheduled', 'live', 'finished', 'skipped']),
    durationSeconds: count,
    winnerId: z.string().nullable(),
    sides: z.array(sideSchema).max(2),
  })
  .superRefine((map, ctx) => {
    const started = map.status === 'live' || map.status === 'finished';
    if (
      started &&
      (map.sides.length !== 2 ||
        new Set(map.sides.map((s) => s.side)).size !== 2 ||
        new Set(map.sides.map((s) => s.teamId)).size !== 2)
    )
      ctx.addIssue({
        code: 'custom',
        message: 'Une carte commencée requiert deux camps distincts.',
      });
    if (
      (map.status === 'finished') !== (map.winnerId !== null) ||
      (map.winnerId && !map.sides.some((s) => s.teamId === map.winnerId))
    )
      ctx.addIssue({
        code: 'custom',
        message: 'Le vainqueur est requis uniquement pour une carte terminée.',
      });
    if (!started && (map.sides.length || map.durationSeconds))
      ctx.addIssue({ code: 'custom', message: 'Aucune statistique avant le début de la carte.' });
  });
export const matchSchema = z
  .object({
    id: z.string(),
    leagueId: z.string(),
    homeId: z.string(),
    awayId: z.string(),
    startsAt: z.iso.datetime({ offset: true }),
    updatedAt: z.iso.datetime({ offset: true }),
    format: z.enum(['BO1', 'BO3', 'BO5']),
    status: z.enum(['scheduled', 'live', 'finished']),
    patch: z.string().nullable(),
    stage: z.string().nullable(),
    maps: z.array(mapSchema),
  })
  .superRefine((match, ctx) => {
    if (
      match.homeId === match.awayId ||
      new Set(match.maps.map((m) => m.number)).size !== match.maps.length ||
      match.maps.some(
        (m) =>
          m.number > Number(match.format.slice(2)) ||
          m.sides.some((s) => ![match.homeId, match.awayId].includes(s.teamId)),
      )
    )
      ctx.addIssue({
        code: 'custom',
        message: 'Références de rencontre ou numéros de cartes incohérents.',
      });
    if (
      match.maps.filter((m) => m.status === 'live').length > 1 ||
      (match.status !== 'live' && match.maps.some((m) => m.status === 'live'))
    )
      ctx.addIssue({ code: 'custom', message: 'État du direct incohérent.' });
    const target = Math.ceil(Number(match.format.slice(2)) / 2);
    const scores = [match.homeId, match.awayId].map(
      (id) => match.maps.filter((map) => map.winnerId === id).length,
    );
    if (
      (match.status === 'scheduled' && match.maps.some((map) => map.status !== 'scheduled')) ||
      (match.status !== 'scheduled' && match.maps.length !== Number(match.format.slice(2))) ||
      (match.status === 'finished' &&
        (!scores.includes(target) ||
          scores.every((score) => score >= target) ||
          match.maps.some((map) => map.status === 'scheduled'))) ||
      (match.status === 'live' && scores.some((score) => score >= target))
    )
      ctx.addIssue({
        code: 'custom',
        message: 'Le statut de la série doit correspondre aux cartes et au score.',
      });
  });
export const matchesSchema = z
  .object({ generatedAt: z.iso.datetime({ offset: true }), items: z.array(matchSchema) })
  .refine(
    (data) => new Set(data.items.map((m) => m.id)).size === data.items.length,
    'Les identifiants de rencontre doivent être uniques.',
  );
export type EsportMatch = z.infer<typeof matchSchema>;
export type MatchMap = z.infer<typeof mapSchema>;
export type MapSide = z.infer<typeof sideSchema>;
export const seriesScore = (match: EsportMatch, teamId: string) =>
  match.maps.filter((map) => map.winnerId === teamId).length;
export const sideKills = (side: MapSide) =>
  side.players.reduce((sum, player) => sum + player.kills, 0);
export const sideGold = (side: MapSide) =>
  side.players.reduce((sum, player) => sum + player.gold, 0);
export function countdown(startsAt: string, now: number) {
  const seconds = Math.max(0, Math.ceil((Date.parse(startsAt) - now) / 1000));
  if (!seconds) return 'Début attendu';
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `Dans ${days} j ${hours} h`;
  if (hours) return `Dans ${hours} h ${String(minutes).padStart(2, '0')}`;
  return `Dans ${minutes} min ${String(seconds % 60).padStart(2, '0')} s`;
}
