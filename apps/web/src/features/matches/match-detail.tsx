import { useState } from 'react';
import { Tabs } from 'radix-ui';
import { Clock3, Trophy, Swords, TowerControl, Flame, Crown } from 'lucide-react';
import type { Catalog } from '@/domain/schemas';
import type { EsportMatch, MapSide } from '@/domain/matches';
import { seriesScore, sideKills, sideGold } from '@/domain/matches';
import { dateTime, decimal, time } from '@/lib/format';
import { Modal } from '@/components/ui/modal';
import { Logo } from '@/components/ui/logo';

function TeamStats({
  side,
  catalog,
  winner,
}: {
  side: MapSide;
  catalog: Catalog;
  winner: boolean;
}) {
  const team = catalog.teams.find((t) => t.id === side.teamId)!;
  return (
    <section
      className={`map-team side-${side.side}`}
      aria-label={`${team.name}, côté ${side.side === 'blue' ? 'bleu' : 'rouge'}`}
    >
      <div className="map-team-heading">
        <Logo src={team.image} name={team.name} code={team.code} />
        <div>
          <h3>{team.name}</h3>
          <span>Côté {side.side === 'blue' ? 'bleu' : 'rouge'}</span>
        </div>
        {winner && (
          <span className="map-winner">
            <Trophy size={14} />
            Victoire
          </span>
        )}
      </div>
      <dl className="map-objectives">
        {[
          { label: 'Éliminations', value: sideKills(side), icon: Swords },
          { label: 'Or', value: `${decimal(sideGold(side) / 1000, 1)} k`, icon: Crown },
          { label: 'Tours', value: side.towers, icon: TowerControl },
          { label: 'Dragons', value: side.dragons, icon: Flame },
          { label: 'Barons', value: side.barons, icon: Trophy },
        ].map(({ label, value, icon: Icon }) => (
          <div key={label}>
            <dt>
              <Icon size={14} />
              {label}
            </dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <div className="roster-table" role="table" aria-label={`Composition ${team.name}`}>
        <div className="roster-head" role="row">
          <span role="columnheader">Joueur / champion</span>
          <span role="columnheader" aria-label="Éliminations, morts, assistances">
            K / D / A
          </span>
          <span role="columnheader" aria-label="Sbires tués">
            CS
          </span>
          <span role="columnheader">Or</span>
        </div>
        {side.players.map((player) => (
          <div className="roster-row" role="row" key={player.id}>
            <div className="roster-player" role="cell">
              <Logo
                src={player.championImage}
                name={player.champion}
                code={player.champion.slice(0, 2)}
                className="champion-portrait"
              />
              <div>
                <strong>
                  {player.name}
                  <small>{player.role}</small>
                </strong>
                <span>{player.champion}</span>
              </div>
            </div>
            <span role="cell" className="roster-kda">
              <span className="mobile-stat-label">K/D/A</span>
              {player.kills} / {player.deaths} / {player.assists}
            </span>
            <span role="cell">
              <span className="mobile-stat-label">CS</span>
              {player.cs}
            </span>
            <span role="cell">
              <span className="mobile-stat-label">Or</span>
              {decimal(player.gold / 1000, 1)} k
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
export function MatchDetail({
  match,
  catalog,
  open,
  onClose,
}: {
  match: EsportMatch;
  catalog: Catalog;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Modal
      open={open}
      onOpenChange={(value) => {
        if (!value) onClose();
      }}
      title="Centre du match"
      description={`${catalog.leagues.find((l) => l.id === match.leagueId)?.name} · ${dateTime(match.startsAt)} · Heure de Paris`}
      className="match-dialog"
    >
      <MatchContent key={match.id} match={match} catalog={catalog} />
    </Modal>
  );
}
function MatchContent({ match, catalog }: { match: EsportMatch; catalog: Catalog }) {
  const initial =
    match.maps.find((m) => m.status === 'live') ?? match.maps.find((m) => m.status === 'finished');
  const [choice, setChoice] = useState('');
  const active =
    match.maps.find(
      (m) => String(m.number) === choice && ['live', 'finished'].includes(m.status),
    ) ?? initial;
  const home = catalog.teams.find((t) => t.id === match.homeId)!;
  const away = catalog.teams.find((t) => t.id === match.awayId)!;
  return (
    <div className="match-detail-scroll">
      <div className="match-scoreboard">
        <div>
          <Logo src={home.image} name={home.name} code={home.code} />
          <strong>{home.name}</strong>
        </div>
        <div className="series-summary">
          <span className="series-format">{match.format}</span>
          <strong>
            {match.status === 'scheduled'
              ? 'vs'
              : `${seriesScore(match, home.id)} : ${seriesScore(match, away.id)}`}
          </strong>
          {match.status === 'live' ? (
            <span className="live-badge">
              <span aria-hidden="true" />
              En direct
            </span>
          ) : (
            <span>{match.status === 'finished' ? 'Terminé' : 'À venir'}</span>
          )}
        </div>
        <div>
          <Logo src={away.image} name={away.name} code={away.code} />
          <strong>{away.name}</strong>
        </div>
      </div>
      <div className="match-information">
        <span>{match.stage ?? 'Phase non renseignée'}</span>
        {match.patch && <span>Patch {match.patch}</span>}
        <span>Relevé à {time(match.updatedAt)}</span>
      </div>
      <Tabs.Root value={active ? String(active.number) : ''} onValueChange={setChoice}>
        <Tabs.List className="map-tabs" aria-label="Cartes du match">
          {Array.from({ length: Number(match.format.slice(2)) }, (_, i) => {
            const map = match.maps.find((m) => m.number === i + 1);
            const started = map?.status === 'live' || map?.status === 'finished';
            return (
              <Tabs.Trigger key={i} value={String(i + 1)} disabled={!started}>
                <strong>Carte {i + 1}</strong>
                <span>
                  {map?.status === 'live'
                    ? 'En direct'
                    : map?.status === 'finished'
                      ? 'Terminée'
                      : map?.status === 'skipped'
                        ? 'Non jouée'
                        : 'À venir'}
                </span>
              </Tabs.Trigger>
            );
          })}
        </Tabs.List>
        {active ? (
          <Tabs.Content value={String(active.number)} className="map-content">
            <div className="map-caption">
              <h3>Carte {active.number}</h3>
              <span>
                <Clock3 size={14} />
                {Math.floor(active.durationSeconds / 60)}:
                {String(active.durationSeconds % 60).padStart(2, '0')} ·{' '}
                {active.status === 'live' ? 'Temps au dernier relevé' : 'Durée finale'}
              </span>
            </div>
            <div className="map-teams">
              {active.sides.map((side) => (
                <TeamStats
                  key={`${active.number}-${side.teamId}`}
                  side={side}
                  catalog={catalog}
                  winner={active.winnerId === side.teamId}
                />
              ))}
            </div>
          </Tabs.Content>
        ) : (
          <div className="match-pending">
            <Clock3 size={25} />
            <h3>Le match se prépare.</h3>
            <p>
              Compositions, choix des côtés et statistiques apparaîtront dès le premier relevé de la
              partie.
            </p>
          </div>
        )}
      </Tabs.Root>
    </div>
  );
}
