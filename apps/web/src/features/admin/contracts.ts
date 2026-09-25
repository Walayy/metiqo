import { z } from 'zod';

const timestamp = z.iso.datetime({ offset: true });
export const adminUserSchema = z.object({
  id: z.uuid(),
  email: z.email(),
  role: z.enum(['user', 'admin']),
  disabled: z.boolean(),
  verified: z.boolean(),
  createdAt: timestamp,
  sessions: z.number().int().nonnegative(),
});
export const usersSchema = z.object({
  items: z.array(adminUserSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  pageSize: z.number().int().positive(),
});
export const runSchema = z.object({
  id: z.uuid(),
  scriptId: z.string(),
  trigger: z.enum(['manual', 'schedule']),
  status: z.enum(['queued', 'running', 'succeeded', 'failed', 'interrupted']),
  requestedAt: timestamp,
  startedAt: timestamp.nullable(),
  finishedAt: timestamp.nullable(),
  error: z.string().nullable(),
  availableAt: timestamp.optional(),
  summary: z
    .object({
      eventsScanned: z.number().int().nonnegative().optional(),
      eventsCollected: z.number().int().nonnegative().optional(),
      liveEvents: z.number().int().nonnegative().optional(),
      eventsStopped: z.number().int().nonnegative().optional(),
      eventsFailed: z.number().int().nonnegative().optional(),
      markets: z.number().int().nonnegative().optional(),
      selections: z.number().int().nonnegative().optional(),
      quotes: z.number().int().nonnegative().optional(),
      openQuotes: z.number().int().nonnegative().optional(),
      suspendedQuotes: z.number().int().nonnegative().optional(),
      snapshots: z.number().int().nonnegative().optional(),
    })
    .nullable()
    .optional(),
  complete: z.boolean().nullable().optional(),
  eventErrors: z.array(z.object({ eventId: z.string(), reason: z.string() })).optional(),
  interruption: z
    .object({
      stage: z.string(),
      eventId: z.string().nullable(),
      kind: z.string(),
      frames: z.array(z.string()),
    })
    .nullable()
    .optional(),
  deferredReason: z.string().nullable().optional(),
});
export const scriptSchema = z.object({
  id: z.string(),
  family: z.string().min(1),
  name: z.string(),
  description: z.string(),
  command: z.string(),
  cron: z.string(),
  timezone: z.enum(['Europe/Paris', 'UTC']),
  enabled: z.boolean(),
  revision: z.number().int().positive(),
  nextRunAt: timestamp.nullable(),
  upcoming: z.array(timestamp),
  available: z.boolean(),
  activeRun: runSchema.nullable(),
  runs: z.array(runSchema),
});
export const scriptsSchema = z.object({
  items: z.array(scriptSchema),
  worker: z.object({ online: z.boolean(), lastSeenAt: timestamp.nullable() }),
});
export const previewSchema = z.object({ upcoming: z.array(timestamp) });
export const successSchema = z.object({ ok: z.literal(true) });
export type AdminUser = z.infer<typeof adminUserSchema>;
export type Script = z.infer<typeof scriptSchema>;
export type ScriptRun = z.infer<typeof runSchema>;
