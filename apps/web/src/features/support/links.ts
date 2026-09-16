import { config } from '@/lib/config';

export function supportUrl(value: string | undefined): string | null {
  if (!value?.trim()) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
  } catch {
    return null;
  }
}
export const supportLinks = {
  donation:
    config.dataMode === 'mock'
      ? 'https://example.com/?metiquo=donation'
      : supportUrl(import.meta.env.VITE_DONATION_URL),
  referral:
    config.dataMode === 'mock'
      ? 'https://example.com/?metiquo=stake-referral'
      : supportUrl(import.meta.env.VITE_STAKE_REFERRAL_URL),
};
