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
export function bestOffer(opportunity: Opportunity) {
  const first = opportunity.offers[0];
  if (!first) throw new Error('Aucune cote disponible.');
  return opportunity.offers.reduce((best, offer) => (offer.odds > best.odds ? offer : best), first);
}
export const valueOf = (opportunity: Opportunity) =>
  expectedValue(opportunity.probability, bestOffer(opportunity).odds);
export const fairOdds = (probability: number) => 1 / probability;
export const marketLabel = (market: Opportunity['market']) =>
  market === 'winner' ? 'Vainqueur du match' : 'Vainqueur · carte 1';
