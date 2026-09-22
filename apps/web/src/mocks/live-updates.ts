import { matches } from './esport';

/** Explicit, fictional QA frames; never loaded by the API data adapter. */
export function liveUpdateFrame(frame: number) {
  const data = structuredClone(matches);
  const match = data.items.find((item) => item.status === 'live');
  const active = match?.maps.find((map) => map.status === 'live');
  if (!match || !active) throw new Error('Le scénario QA exige une carte live.');
  match.updatedAt = data.generatedAt = new Date().toISOString();
  active.updatedAt = match.updatedAt;
  active.durationSeconds = frame === 0 ? null : 1634 + Math.min(frame, 4) * 15;
  for (const side of active.sides) {
    side.towers = Math.min(11, (side.towers ?? 0) + Math.min(frame, 4));
    for (const player of side.players) {
      player.cs += frame * 3;
      player.gold = (player.gold ?? 0) + frame * 230;
      player.level = Math.min(18, 12 + frame);
      player.kills += frame;
    }
  }
  if (frame >= 4) {
    const next = match.maps.find((map) => map.number === active.number + 1);
    active.status = 'finished';
    active.winnerId = match.awayId;
    if (next) {
      Object.assign(next, structuredClone(active), {
        number: next.number,
        status: 'live',
        winnerId: null,
        durationSeconds: 60 + (frame - 4) * 15,
      });
    } else {
      match.status = 'finished';
    }
  }
  return data;
}
