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
export const offerSchema = z.object({ bookmaker: z.string(), odds: z.number().gt(1) });
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
    offers: z.array(offerSchema).min(1),
    history: z.array(z.object({ label: z.string(), odds: z.number().gt(1) })).min(2),
  })
  .refine(
    (item) => item.homeId !== item.awayId && [item.homeId, item.awayId].includes(item.pickId),
    {
      message: 'Les équipes doivent être distinctes et la sélection doit appartenir au match.',
    },
  );
export const opportunitiesSchema = z.object({
  generatedAt: z.iso.datetime(),
  scenarioDate: z.iso.datetime(),
  items: z.array(opportunitySchema),
});
export type League = z.infer<typeof leagueSchema>;
export type Team = z.infer<typeof teamSchema>;
export type Catalog = z.infer<typeof catalogSchema>;
export type Opportunity = z.infer<typeof opportunitySchema>;
export type OpportunitiesResponse = z.infer<typeof opportunitiesSchema>;
