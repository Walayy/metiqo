import { useId, useState } from 'react';
import { ChevronDown, CirclePercent, Hourglass, LockKeyhole } from 'lucide-react';
import type { Catalog } from '@/domain/schemas';
import type { EsportMatch } from '@/domain/matches';
import { expectedValue } from '@/domain/value';
import { decimal, scheduledDate, signedDecimal, time } from '@/lib/format';
import { SourceMark } from '@/components/ui/source-mark';
import { Logo } from '@/components/ui/logo';
import './match-odds.css';

type OddsMarket = NonNullable<EsportMatch['oddsMarkets']>[number];
type OddsSelection = OddsMarket['selections'][number];
type Team = Catalog['teams'][number];
type MarketGroup = { kind: OddsMarket['kind']; mapNumber: number | null; phases: OddsMarket[] };

function marketGroups(markets: OddsMarket[]): MarketGroup[] {
  const groups = new Map<string, MarketGroup>();
  for (const market of markets) {
    const key = `${market.kind}:${market.mapNumber ?? ''}`;
    const group = groups.get(key) ?? {
      kind: market.kind,
      mapNumber: market.mapNumber,
      phases: [],
    };
    group.phases.push(market);
    groups.set(key, group);
  }
  return [...groups.values()]
    .sort((a, b) =>
      a.kind === b.kind
        ? (a.mapNumber ?? 0) - (b.mapNumber ?? 0)
        : a.kind === 'match_winner'
          ? -1
          : 1,
    )
    .map((group) => ({
      ...group,
      phases: group.phases.toSorted((a, b) =>
        a.phase === b.phase ? 0 : a.phase === 'prematch' ? -1 : 1,
      ),
    }));
}

const outcomeLabels = {
  won: 'Gagnée',
  lost: 'Perdue',
  void: 'Annulée',
  pending: 'En attente',
} as const;

function groupOutcome(group: MarketGroup, teamId: string): OddsSelection['result'] {
  const results = group.phases
    .map((phase) => phase.selections.find((selection) => selection.teamId === teamId)?.result)
    .filter((result): result is OddsSelection['result'] => Boolean(result));
  return results.length && results.every((result) => result === results[0])
    ? results[0]!
    : 'pending';
}

function Quote({
  selection,
  team,
  phase,
  historical,
  result,
  position,
}: {
  selection: OddsSelection | undefined;
  team: Team;
  phase: OddsMarket['phase'];
  historical: boolean;
  result: OddsSelection['result'];
  position: 'home' | 'away';
}) {
  if (!selection)
    return (
      <span
        className="match-odds-quote is-missing"
        role="img"
        aria-label={`${team.name}, cote non publiée`}
      >
        —
      </span>
    );
  const value =
    result === 'pending' &&
    phase === 'prematch' &&
    !historical &&
    !selection.suspended &&
    selection.odds !== null &&
    selection.probability !== null
      ? expectedValue(selection.probability, selection.odds)
      : null;
  const displayValue = value !== null && value > 0 ? signedDecimal(value, 1) : null;
  const phaseLabel = phase === 'prematch' ? 'Pré-match' : 'En direct';
  const showHourglass = result === 'pending' && !selection.suspended && selection.odds !== null;
  const resultDescription =
    selection.suspended && result === 'pending' ? '' : `, ${outcomeLabels[result].toLowerCase()}`;
  return (
    <span
      className={`match-odds-quote is-${result}${selection.suspended ? ' is-suspended' : ''}${displayValue ? ' is-value' : ''}${historical ? ' is-historical' : ''}`}
      role="img"
      aria-label={`${team.name}, ${phaseLabel}, ${selection.suspended ? 'suspendue' : `cote ${decimal(selection.odds!)}`}${resultDescription}, relevée le ${scheduledDate(selection.observedAt)}${displayValue ? `, value ${displayValue} pour cent` : ''}`}
    >
      {showHourglass && position === 'home' && <Hourglass size={13} aria-hidden="true" />}
      {selection.suspended ? (
        <>
          <LockKeyhole className="match-odds-suspension-lock" size={13} aria-hidden="true" />
          <span>Suspendue</span>
        </>
      ) : (
        <strong>{decimal(selection.odds!)}</strong>
      )}
      {showHourglass && position === 'away' && <Hourglass size={13} aria-hidden="true" />}
    </span>
  );
}

export function MatchOdds({ match, home, away }: { match: EsportMatch; home: Team; away: Team }) {
  const markets = match.oddsMarkets ?? [];
  const groups = marketGroups(markets);
  const hasResult = groups.some((group) =>
    [home.id, away.id].some((teamId) => groupOutcome(group, teamId) !== 'pending'),
  );
  const [expanded, setExpanded] = useState(match.status === 'finished' && hasResult);
  const panelId = useId();
  if (!groups.length) return null;
  const lastObserved = markets.reduce(
    (latest, market) =>
      Date.parse(market.observedAt) > Date.parse(latest) ? market.observedAt : latest,
    markets[0]!.observedAt,
  );
  return (
    <section className="match-odds-section" aria-label="Cotes et résultats des sélections Stake">
      <button
        type="button"
        className="match-odds-toggle"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={() => setExpanded((current) => !current)}
      >
        <span className="match-odds-toggle-icon">
          <CirclePercent size={18} aria-hidden="true" />
        </span>
        <span className="match-odds-toggle-copy">
          <strong>Cotes & résultats</strong>
          <small>
            {match.status === 'finished'
              ? hasResult
                ? 'Résultats des sélections disponibles'
                : 'Résultats en attente'
              : `${groups.length} marché${groups.length > 1 ? 's' : ''} suivi${groups.length > 1 ? 's' : ''}`}
          </small>
        </span>
        <ChevronDown size={17} className="match-odds-chevron" aria-hidden="true" />
        <span className="match-odds-toggle-source" aria-hidden="true">
          <SourceMark source="Stake" />
        </span>
      </button>
      <div id={panelId} className="match-odds-panel" hidden={!expanded}>
        <div className="match-odds-intro">
          <time
            dateTime={lastObserved}
            aria-label={`Dernier relevé le ${scheduledDate(lastObserved)} · Paris`}
          >
            Dernier relevé {time(lastObserved)}
          </time>
        </div>
        <div className="match-odds-groups">
          {groups.map((group) => {
            const label =
              group.kind === 'match_winner'
                ? 'Vainqueur du match'
                : `Vainqueur de la carte ${group.mapNumber}`;
            return (
              <section
                className="match-odds-group"
                aria-label={label}
                key={`${group.kind}:${group.mapNumber ?? ''}`}
              >
                <div className="match-odds-group-heading">
                  <h3>{label}</h3>
                  {match.status === 'finished' && (
                    <span className="match-odds-result-note">
                      {groupOutcome(group, home.id) === 'pending' &&
                      groupOutcome(group, away.id) === 'pending'
                        ? 'Résultat en attente'
                        : 'Résultat validé'}
                    </span>
                  )}
                </div>
                <div className="match-odds-phases">
                  {group.phases.map((market) => (
                    <div
                      className={`match-odds-phase${market.historical ? ' is-historical' : ''}`}
                      key={market.phase}
                    >
                      <div className="match-odds-identity is-home">
                        <Logo src={home.image} name={home.name} />
                      </div>
                      <Quote
                        selection={market.selections.find(
                          (selection) => selection.teamId === home.id,
                        )}
                        team={home}
                        phase={market.phase}
                        historical={market.historical}
                        result={groupOutcome(group, home.id)}
                        position="home"
                      />
                      <div className="match-odds-phase-label">
                        <span aria-hidden="true">vs</span>
                        <strong>{market.phase === 'prematch' ? 'Pré-match' : 'En direct'}</strong>
                        <time
                          dateTime={market.observedAt}
                          aria-label={`${market.phase === 'prematch' ? 'Pré-match' : 'En direct'}, relevé le ${scheduledDate(market.observedAt)} · Paris`}
                        >
                          {time(market.observedAt)}
                        </time>
                      </div>
                      <Quote
                        selection={market.selections.find(
                          (selection) => selection.teamId === away.id,
                        )}
                        team={away}
                        phase={market.phase}
                        historical={market.historical}
                        result={groupOutcome(group, away.id)}
                        position="away"
                      />
                      <div className="match-odds-identity is-away">
                        <Logo src={away.image} name={away.name} />
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </section>
  );
}
