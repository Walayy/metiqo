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
});
export const scriptSchema = z.object({
  id: z.string(),
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
