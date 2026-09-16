export const decimal = (value: number, digits = 2) =>
  value.toLocaleString('fr-FR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const compactEuro = (value: number) =>
  new Intl.NumberFormat('fr-FR', {
    style: 'currency',
    currency: 'EUR',
    notation: 'compact',
    maximumFractionDigits: Math.abs(value) < 10 ? 2 : 1,
  }).format(value);
export const scheduledDate = (value: string, timeZone = 'Europe/Paris') =>
  new Intl.DateTimeFormat('fr-FR', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone,
  }).format(new Date(value));
export const accountDate = (value: string) =>
  new Intl.DateTimeFormat('fr-FR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'Europe/Paris',
  }).format(new Date(value));
export const percent = (value: number, digits = 1) => `${decimal(value, digits)} %`;
export const signedDecimal = (value: number, digits = 2) =>
  `${value > 0 ? '+' : value < 0 ? '−' : ''}${decimal(Math.abs(value), digits)}`;
export const dateTime = (value: string) => `${shortDate(value)} · ${time(value)}`;
export const calendarDay = (value: string) =>
  new Intl.DateTimeFormat('fr-FR', { day: 'numeric', timeZone: 'Europe/Paris' }).format(
    new Date(value),
  );
export const calendarMonth = (value: string) =>
  new Intl.DateTimeFormat('fr-FR', {
    month: 'long',
    year: 'numeric',
    timeZone: 'Europe/Paris',
  }).format(new Date(value));
export const time = (value: string) =>
  new Intl.DateTimeFormat('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Europe/Paris',
  }).format(new Date(value));
export const shortDate = (value: string) =>
  new Intl.DateTimeFormat('fr-FR', {
    day: 'numeric',
    month: 'short',
    timeZone: 'Europe/Paris',
  }).format(new Date(value));
export const normalize = (text: string) =>
  text
    .trim()
    .replace(/\s+/g, ' ')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();

const regions: Record<string, string> = {
  INTERNATIONAL: 'International',
  'NORTH AMERICA': 'Amérique du Nord',
  BRAZIL: 'Brésil',
  AMERICAS: 'Amériques',
  EMEA: 'Europe, Moyen-Orient et Afrique',
  KOREA: 'Corée du Sud',
  CHINA: 'Chine',
  PACIFIC: 'Pacifique',
  JAPAN: 'Japon',
  'HONG KONG, MACAU, TAIWAN': 'Hong Kong, Macao et Taïwan',
  VIETNAM: 'Viêt Nam',
  'LATIN AMERICA NORTH': 'Amérique latine — Nord',
  'LATIN AMERICA SOUTH': 'Amérique latine — Sud',
  OCEANIA: 'Océanie',
};
export const regionLabel = (region: string) => regions[region.toUpperCase()] ?? region;

export const catalogDate = (value: string) =>
  new Intl.DateTimeFormat('fr-FR', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${value}T12:00:00Z`));
