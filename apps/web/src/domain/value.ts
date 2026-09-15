import type { Opportunity } from './schemas';

export function expectedValue(probability: number, odds: number): number {
  if (
    !Number.isFinite(probability) ||
    probability < 0 ||
    probability > 1 ||
    !Number.isFinite(odds) ||
    odds <= 1
  ) {
    throw new RangeError('Probabilité ou cote invalide.');
  }
  return (probability * odds - 1) * 100;
}
export const trackedBookmaker = { id: 'stake', name: 'Stake' } as const;
export function currentQuote(opportunity: Opportunity) {
  const latest = opportunity.history.at(-1);
  if (!latest) throw new Error('Aucune cote disponible.');
  return latest;
}
export const valueOf = (opportunity: Opportunity) =>
  expectedValue(opportunity.probability, currentQuote(opportunity).odds);
export const oddsChange = (opportunity: Opportunity) =>
  currentQuote(opportunity).odds - opportunity.history[0]!.odds;
export const fairOdds = (probability: number) => 1 / probability;
export const marketLabel = (market: Opportunity['market']) =>
  market === 'winner' ? 'Vainqueur du match' : 'Vainqueur · carte 1';
