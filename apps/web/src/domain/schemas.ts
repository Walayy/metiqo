import { z } from 'zod';

export const leagueSchema = z.object({
  id: z.string(),
  slug: z.string(),
  name: z.string(),
  region: z.string(),
  image: z.string(),
  sourceImage: z.string(),
  tier: z.enum(['international', 'major', 'regional']),
});
export const teamSchema = z.object({
  id: z.string(),
  name: z.string(),
  code: z.string(),
  slug: z.string(),
  leagueId: z.string(),
  image: z.string(),
  sourceImage: z.string(),
});
export const catalogSchema = z.object({
  retrievedAt: z.iso.date(),
  source: z.url(),
  leagues: z.array(leagueSchema),
  teams: z.array(teamSchema),
});
export const oddsHistorySchema = z
  .array(
    z.object({
      recordedAt: z.iso.datetime(),
      odds: z.number().gt(1),
    }),
  )
  .min(1)
  .refine(
    (history) =>
      history.every(
        (point, index) =>
          index === 0 || Date.parse(point.recordedAt) > Date.parse(history[index - 1]!.recordedAt),
      ),
    { message: 'Les relevés doivent être uniques et classés par date croissante.' },
  );
export const opportunitySchema = z
  .object({
    id: z.string(),
    leagueId: z.string(),
    homeId: z.string(),
    awayId: z.string(),
    pickId: z.string(),
    startsAt: z.iso.datetime(),
    format: z.enum(['BO1', 'BO3', 'BO5']),
    market: z.enum(['winner', 'map1']),
    probability: z.number().gt(0).lt(1),
    bookmaker: z.literal('stake'),
    history: oddsHistorySchema,
  })
  .refine(
    (item) => item.homeId !== item.awayId && [item.homeId, item.awayId].includes(item.pickId),
    {
      message: 'Les équipes doivent être distinctes et la sélection doit appartenir au match.',
    },
  );
export const opportunitiesSchema = z.object({
  generatedAt: z.iso.datetime(),
  referenceDate: z.iso.datetime(),
  items: z.array(opportunitySchema),
});
export type League = z.infer<typeof leagueSchema>;
export type Team = z.infer<typeof teamSchema>;
export type Catalog = z.infer<typeof catalogSchema>;
export type Opportunity = z.infer<typeof opportunitySchema>;
export type OpportunitiesResponse = z.infer<typeof opportunitiesSchema>;
