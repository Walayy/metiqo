import { useState } from 'react';
import { Popover, Tabs } from 'radix-ui';
import {
  Bug,
  Check,
  Clock3,
  Coins,
  Eye,
  Flame,
  Shield,
  Swords,
  TowerControl,
  Trophy,
} from 'lucide-react';
import type { Catalog } from '@/domain/schemas';
import type { EsportMatch, MapSide, MatchMap } from '@/domain/matches';
import { matchWinnerId, seriesScore, sideKills, sideGold } from '@/domain/matches';
import { championAsset } from '@/domain/champions';
import { dateTime, decimal, time } from '@/lib/format';
import { Modal } from '@/components/ui/modal';
import { Logo } from '@/components/ui/logo';

const roleMeta = {
  TOP: { label: 'Top', icon: '/roles/top.svg' },
  JGL: { label: 'Jungle', icon: '/roles/jungle.svg' },
  MID: { label: 'Mid', icon: '/roles/middle.svg' },
  BOT: { label: 'ADC', icon: '/roles/bottom.svg' },
  SUP: { label: 'Support', icon: '/roles/utility.svg' },
} as const;

const objectiveMeta = [
  { key: 'kills', label: 'Éliminations', icon: Swords, className: 'kills' },
  { key: 'gold', label: 'Or', icon: Coins, className: 'gold' },
  { key: 'towers', label: 'Tours', icon: TowerControl, className: 'towers' },
  { key: 'dragons', label: 'Dragons', icon: Flame, className: 'dragons' },
  { key: 'barons', label: 'Barons', icon: Trophy, className: 'barons' },
  { key: 'heralds', label: 'Hérauts', icon: Eye, className: 'heralds' },
  { key: 'grubs', label: 'Larves', icon: Bug, className: 'grubs' },
  { key: 'inhibitors', label: 'Inhibiteurs', icon: Shield, className: 'inhibitors' },
] as const;

type ObjectiveKey = (typeof objectiveMeta)[number]['key'];

function objectiveValues(side: MapSide | undefined): Record<ObjectiveKey, number | string> {
  const gold = side ? sideGold(side) : null;
  return {
    kills: side ? (sideKills(side) ?? '—') : '—',
    gold: gold == null ? '—' : `${decimal(gold / 1000, 1)} k`,
    towers: side?.towers ?? '—',
    dragons: side?.dragons ?? '—',
    barons: side?.barons ?? '—',
    heralds: side?.heralds ?? '—',
    grubs: side?.grubs ?? '—',
    inhibitors: side?.inhibitors ?? '—',
  };
}

function ObjectiveComparison({
  active,
  home,
  away,
}: {
  active: MatchMap;
  home: Catalog['teams'][number];
  away: Catalog['teams'][number];
}) {
  const homeValues = objectiveValues(active.sides.find((side) => side.teamId === home.id));
  const awayValues = objectiveValues(active.sides.find((side) => side.teamId === away.id));
  return (
    <table className="map-comparison" aria-label={`Statistiques de la carte ${active.number}`}>
      <thead>
        <tr>
          <th scope="col" aria-label={home.name}>
            {home.code.trim() || home.name}
          </th>
          <td>
            <span className="map-unavailable-key">— Non publié</span>
          </td>
          <th scope="col" aria-label={away.name}>
            {away.code.trim() || away.name}
          </th>
        </tr>
      </thead>
      <tbody>
        {objectiveMeta.map(({ key, label, icon: Icon, className }) => (
          <tr className={`comparison-row comparison-row--${className}`} key={key}>
            <td>{homeValues[key]}</td>
            <th scope="row">
              <span>
                <Icon size={14} strokeWidth={1.6} aria-hidden="true" />
                {label}
              </span>
            </th>
            <td>{awayValues[key]}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TeamStats({ side, catalog }: { side: MapSide; catalog: Catalog }) {
  const team = catalog.teams.find((t) => t.id === side.teamId);
  if (!team) return null;
  return (
    <section
      className="map-team"
      aria-label={`${team.name}, ${side.side === null ? 'côté non renseigné' : `côté ${side.side === 'blue' ? 'bleu' : 'rouge'}`}`}
    >
      <div className="roster-team-heading">
        <Logo src={team.image} name={team.name} code={team.code} />
        <h4>{team.name}</h4>
      </div>
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
        {side.players.map((player) => {
          const championLabel =
            player.champion ?? (player.championImage ? 'Nom indisponible' : 'Champion non publié');
          return (
            <div className="roster-row" role="row" key={player.id}>
              <div className="roster-player" role="cell">
                <span
                  className="roster-role-icon"
                  role="img"
                  title={roleMeta[player.role].label}
                  aria-label={`Poste : ${roleMeta[player.role].label}`}
                >
                  <img src={roleMeta[player.role].icon} alt="" width="20" height="20" />
                </span>
                <Logo
                  src={championAsset(player.champion, player.championImage)}
                  name={championLabel}
                  code={player.champion?.slice(0, 2) ?? '—'}
                  className="champion-portrait"
                />
                <div>
                  <strong>{player.name}</strong>
                  <span className="roster-player-meta">
                    <span>{championLabel}</span>
                    {player.level != null && (
                      <span className="roster-level">niv. {player.level}</span>
                    )}
                  </span>
                </div>
              </div>
              <span role="cell" className="roster-kda">
                <span className="mobile-stat-label" aria-hidden="true">
                  K/D/A
                </span>
                {player.kills} / {player.deaths} / {player.assists}
              </span>
              <span role="cell">
                <span className="mobile-stat-label" aria-hidden="true">
                  CS
                </span>
                {player.cs}
              </span>
              <span role="cell">
                <span className="mobile-stat-label" aria-hidden="true">
                  Or
                </span>
                {player.gold == null ? '—' : `${decimal(player.gold / 1000, 1)} k`}
              </span>
            </div>
          );
        })}
        {!side.players.length && (
          <div className="match-pending roster-empty">
            Statistiques joueurs non publiées par la source pour ce relevé.
          </div>
        )}
      </div>
    </section>
  );
}

function MapTeamSummary({
  active,
  team,
  position,
}: {
  active: MatchMap;
  team: Catalog['teams'][number];
  position: 'home' | 'away';
}) {
  const side = active.sides.find((item) => item.teamId === team.id);
  const bans = active.bans.filter((ban) => ban.teamId === team.id);
  return (
    <section className={`map-team-summary map-team-summary--${position}`} aria-label={team.name}>
      <div className="map-team-identity">
        <Logo src={team.image} name={team.name} />
        <div>
          <h4>{team.name}</h4>
          <span className="map-team-meta">
            {active.winnerId === team.id && (
              <span className="map-winner">
                <Trophy size={12} aria-hidden="true" />
                Victoire
              </span>
            )}
            {side?.side && (
              <span className={`map-camp map-camp--${side.side}`}>
                Côté {side.side === 'blue' ? 'bleu' : 'rouge'}
              </span>
            )}
          </span>
        </div>
      </div>
      {bans.length ? (
        <ul className="ban-portraits" aria-label={`Champions bannis par ${team.name}`}>
          {bans.map((ban, index) => {
            const label = ban.champion ?? 'Champion non identifié';
            return (
              <li key={`${ban.champion}-${index}`}>
                <Popover.Root>
                  <Popover.Trigger asChild>
                    <button
                      type="button"
                      className="ban-portrait-button"
                      aria-label={`${label}, banni par ${team.name}`}
                      title={`${label} · Banni par ${team.name}`}
                    >
                      <Logo
                        src={championAsset(ban.champion, ban.championImage)}
                        name={label}
                        className="ban-portrait"
                      />
                    </button>
                  </Popover.Trigger>
                  <Popover.Portal>
                    <Popover.Content
                      className="ban-popover"
                      side="top"
                      sideOffset={8}
                      collisionPadding={16}
                      aria-label="Champion banni"
                    >
                      <strong>{label}</strong>
                      <span>Banni par {team.name}</span>
                      <Popover.Arrow className="ban-popover-arrow" />
                    </Popover.Content>
                  </Popover.Portal>
                </Popover.Root>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="bans-unavailable">Bans non publiés</p>
      )}
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
  const winnerId = matchWinnerId(match);
  const hasSeriesScore = Boolean(match.seriesScore) || match.maps.some((map) => map.winnerId);
  const hasCurrentScore = Boolean(match.currentScore);
  return (
    <div className="match-detail-scroll">
      <div className="match-scoreboard">
        <div
          className={`scoreboard-team ${winnerId === home.id ? 'is-winner' : winnerId ? 'is-loser' : ''}`}
        >
          <Logo src={home.image} name={home.name} code={home.code} />
          <strong>{home.name}</strong>
          {winnerId && (
            <span className="scoreboard-outcome">
              {winnerId === home.id && <Check size={12} aria-hidden="true" />}
              {winnerId === home.id ? 'Gagnant' : 'Perdant'}
            </span>
          )}
        </div>
        <div className="series-summary">
          <span className="series-format">{match.format}</span>
          <strong>
            {match.status === 'scheduled'
              ? 'vs'
              : hasSeriesScore
                ? `${seriesScore(match, home.id)} : ${seriesScore(match, away.id)}`
                : hasCurrentScore
                  ? `${match.currentScore?.home ?? 0} : ${match.currentScore?.away ?? 0}`
                  : '—'}
          </strong>
          {match.status === 'live' ? (
            <span className="live-badge">
              <span aria-hidden="true" />
              En direct
            </span>
          ) : (
            <span>
              {match.status === 'finished'
                ? 'Terminé'
                : match.status === 'cancelled'
                  ? 'Annulé'
                  : match.status === 'postponed'
                    ? 'Reporté / interrompu'
                    : match.currentScore && !hasSeriesScore
                      ? 'Score courant'
                      : 'À venir'}
            </span>
          )}
        </div>
        <div
          className={`scoreboard-team ${winnerId === away.id ? 'is-winner' : winnerId ? 'is-loser' : ''}`}
        >
          <Logo src={away.image} name={away.name} code={away.code} />
          <strong>{away.name}</strong>
          {winnerId && (
            <span className="scoreboard-outcome">
              {winnerId === away.id && <Check size={12} aria-hidden="true" />}
              {winnerId === away.id ? 'Gagnant' : 'Perdant'}
            </span>
          )}
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
                      : map?.status === 'skipped' ||
                          (match.status === 'finished' &&
                            i + 1 > seriesScore(match, home.id) + seriesScore(match, away.id))
                        ? 'Non jouée'
                        : match.status === 'finished'
                          ? 'Non publiée'
                          : 'À venir'}
                </span>
              </Tabs.Trigger>
            );
          })}
        </Tabs.List>
        {active ? (
          <Tabs.Content key={active.number} value={String(active.number)} className="map-content">
            <div className="map-caption">
              <h3>Carte {active.number}</h3>
              <span>
                <Clock3 size={14} />
                {active.durationSeconds == null
                  ? 'Durée indisponible'
                  : `${Math.floor(active.durationSeconds / 60)}:${String(active.durationSeconds % 60).padStart(2, '0')} · ${
                      active.status === 'live' ? 'Temps au dernier relevé' : 'Durée finale'
                    }`}
              </span>
            </div>
            <div className="map-team-summaries">
              <MapTeamSummary active={active} team={home} position="home" />
              <MapTeamSummary active={active} team={away} position="away" />
            </div>
            {active.sides.length ? (
              <>
                <ObjectiveComparison active={active} home={home} away={away} />
                <div className="map-rosters-heading">
                  <h3>Joueurs</h3>
                  <span>Composition &amp; statistiques</span>
                </div>
                <div className="map-teams">
                  {[home, away]
                    .map((team) => active.sides.find((side) => side.teamId === team.id))
                    .filter((side): side is MapSide => Boolean(side))
                    .map((side) => (
                      <TeamStats
                        key={`${active.number}-${side.teamId}`}
                        side={side}
                        catalog={catalog}
                      />
                    ))}
                </div>
              </>
            ) : (
              <div className="match-pending">
                <Clock3 size={25} />
                <h3>Statistiques de carte indisponibles</h3>
                <p>
                  Le score courant est conservé, mais SofaScore n’a pas encore publié les joueurs,
                  bans ou objectifs de cette carte.
                </p>
              </div>
            )}
          </Tabs.Content>
        ) : (
          <div className="match-pending">
            <Clock3 size={25} />
            <h3>
              {match.status === 'live'
                ? 'Le direct est en cours.'
                : match.status === 'finished'
                  ? 'Le match est terminé.'
                  : match.status === 'cancelled'
                    ? 'Le match est annulé.'
                    : match.status === 'postponed'
                      ? 'Le programme a changé.'
                      : 'Le match se prépare.'}
            </h3>
            <p>
              {match.status === 'live'
                ? 'Le dernier score est affiché dès qu’il est rendu par SofaScore. Les compositions, bans et statistiques restent vides tant que la source ne les publie pas.'
                : match.status === 'finished'
                  ? 'Les détails des cartes ne sont pas encore disponibles pour cette rencontre.'
                  : match.status === 'cancelled' || match.status === 'postponed'
                    ? 'Le statut sera actualisé dès que la source publiera une nouvelle information.'
                    : 'Compositions, choix des côtés et statistiques apparaîtront dès le premier relevé de la partie.'}
            </p>
          </div>
        )}
      </Tabs.Root>
    </div>
  );
}
