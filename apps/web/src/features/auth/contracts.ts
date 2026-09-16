import { z } from 'zod';

export const emailSchema = z
  .email()
  .max(254)
  .transform((email) => email.trim().toLowerCase());
export const codeSchema = z.string().regex(/^[0-9]{6}$/);
export const userSchema = z.object({
  id: z.uuid(),
  email: z.email(),
  role: z.enum(['user', 'admin']),
  createdAt: z.iso.datetime({ offset: true }),
});
export const sessionSchema = z.object({
  user: userSchema.nullable(),
  expiresAt: z.iso.datetime({ offset: true }).nullable(),
});
export const challengeSchema = z.object({
  challengeId: z.uuid(),
  expiresAt: z.iso.datetime({ offset: true }),
  resendAt: z.iso.datetime({ offset: true }),
});
export type AuthSession = z.infer<typeof sessionSchema>;
export type Challenge = z.infer<typeof challengeSchema>;
