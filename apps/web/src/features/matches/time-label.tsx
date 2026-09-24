import { countdown } from '@/domain/matches';
import { useClockText } from '@/hooks/use-clock-text';
import { observationAge } from './presentation';

export function Countdown({ startsAt }: { startsAt: string }) {
  return useClockText((now) => countdown(startsAt, now));
}
export function ObservationAge({ observedAt }: { observedAt: string }) {
  return useClockText((now) => observationAge(observedAt, now));
}
