export const viewLabels = {
  matches: 'Matchs',
  values: 'Les values',
  performance: 'Performance',
  admin: 'Scripts',
  users: 'Utilisateurs',
} as const;
export type AppView = keyof typeof viewLabels;
export function isAppView(value: string): value is AppView {
  return Object.hasOwn(viewLabels, value);
}
