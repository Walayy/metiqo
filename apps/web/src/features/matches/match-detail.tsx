import { Countdown, ObservationAge } from './time-label';
import { useId, useState } from 'react';
import { motion } from 'motion/react';
import { Tabs, Tooltip } from 'radix-ui';
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
import { championAsset, championName } from '@/domain/champions';
import { dateTime, decimal, scheduledDate } from '@/lib/format';
import { Modal } from '@/components/ui/modal';
import { Logo } from '@/components/ui/logo';
import { SelectionIndicator } from '@/components/ui/selection-indicator';
import { formatDuration, goldDifference } from './presentation';
import { UpdatedValue } from './updated-value';
import { ObservationScope } from './observation-scope';
import { MatchScore } from './match-score';
import { MatchOdds } from './match-odds';
const roleMeta = {
  TOP: { label: 'Top', icon: '/roles/top.svg' },
  JGL: { label: 'Jungle', icon: '/roles/jungle.svg' },
  MID: { label: 'Mid', icon: '/roles/middle.svg' },
  BOT: { label: 'ADC', icon: '/roles/bottom.svg' },
  SUP: { label: 'Support', icon: '/roles/utility.svg' },
} as const;
const roleOrder = Object.keys(roleMeta);
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
  const published = objectiveMeta.filter(
    ({ key }) => homeValues[key] !== '—' || awayValues[key] !== '—',
  );
  const missing = objectiveMeta.filter(
    ({ key }) => homeValues[key] === '—' && awayValues[key] === '—',
  );
  const partial = published.some(({ key }) => homeValues[key] === '—' || awayValues[key] === '—');
  const difference = goldDifference(
    active.sides.find((s) => s.teamId === home.id),
    active.sides.find((s) => s.teamId === away.id),
  );
  return (
    <div className="map-objectives">
      {difference !== null && (
        <p className="gold-difference">
          <Coins size={16} aria-hidden="true" />
          {difference === 0 ? (
            'Égalité en or'
          ) : (
            <>
              <strong>
                <UpdatedValue value={difference > 0 ? home.code : away.code} />
              </strong>
              <UpdatedValue value={`+${decimal(Math.abs(difference) / 1000, 1)} k`} /> d’or
            </>
          )}
        </p>
      )}
      <table className="map-comparison" aria-label={`Statistiques de la carte ${active.number}`}>
        <thead>
          <tr>
            <th scope="col" aria-label={home.name}>
              {home.code.trim() || home.name}
            </th>
            <td>Statistiques</td>
            <th scope="col" aria-label={away.name}>
              {away.code.trim() || away.name}
            </th>
          </tr>
        </thead>
        <tbody>
          {published.map(({ key, label, icon: Icon, className }) => (
            <tr className={`comparison-row comparison-row--${className}`} key={key}>
              <td>
                <UpdatedValue value={homeValues[key]} />
              </td>
              <th scope="row">
                <span>
                  <Icon size={16} strokeWidth={1.8} aria-hidden="true" />
                  {label}
                </span>
              </th>
              <td>
                <UpdatedValue value={awayValues[key]} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {(missing.length > 0 || partial) && (
        <p className="map-unavailable-key">
          {missing.length > 0 &&
            `Non publiés : ${missing.map((item) => item.label.toLocaleLowerCase('fr')).join(', ')}.`}
          {partial && ' — : donnée non publiée.'}
        </p>
      )}
    </div>
  );
}
function TeamStats({ side, catalog, role }: { side: MapSide; catalog: Catalog; role: string }) {
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
        {side.players
          .filter((player) => role === 'all' || player.role === role)
          .toSorted((a, b) => roleOrder.indexOf(a.role) - roleOrder.indexOf(b.role))
          .map((player) => {
            const championLabel =
              championName(player.champion) ??
              (player.championImage ? 'Nom indisponible' : 'Champion non publié');
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
                  <UpdatedValue value={player.champion ?? player.championImage}>
                    <Logo
                      src={championAsset(player.champion, player.championImage)}
                      name={championLabel}
                      code={player.champion?.slice(0, 2) ?? '—'}
                      className="champion-portrait"
                    />
                  </UpdatedValue>
                  <div>
                    <strong>
                      <UpdatedValue value={player.name} />
                    </strong>
                    <span className="roster-player-meta">
                      <span className="roster-role-label">{roleMeta[player.role].label}</span>
                      <UpdatedValue value={championLabel} />
                      <UpdatedValue className="roster-level" value={player.level}>
                        {player.level != null ? `niv. ${player.level}` : ''}
                      </UpdatedValue>
                    </span>
                  </div>
                </div>
                <span role="cell" className="roster-kda">
                  <span className="mobile-stat-label" aria-hidden="true">
                    K/D/A
                  </span>
                  <span>
                    <UpdatedValue value={player.kills} /> / <UpdatedValue value={player.deaths} /> /{' '}
                    <UpdatedValue value={player.assists} />
                  </span>
                </span>
                <span role="cell">
                  <span className="mobile-stat-label" aria-hidden="true">
                    CS
                  </span>
                  <UpdatedValue value={player.cs} />
                </span>
                <span role="cell">
                  <span className="mobile-stat-label" aria-hidden="true">
                    Or
                  </span>
                  <UpdatedValue
                    value={player.gold == null ? '—' : `${decimal(player.gold / 1000, 1)} k`}
                  />
                </span>
              </div>
            );
          })}
        {!side.players.some((player) => role === 'all' || player.role === role) && (
          <div className="match-pending roster-empty">
            Joueur ou statistiques non publiés pour ce relevé.
          </div>
        )}
      </div>
    </section>
  );
}
function TeamEmblem({ team, winner }: { team: Catalog['teams'][number]; winner: boolean }) {
  return (
    <span className="team-emblem">
      <Logo src={team.image} name={team.name} />
      {winner && (
        <Tooltip.Root>
          <Tooltip.Trigger asChild>
            <span
              className="team-victory-mark"
              role="img"
              tabIndex={0}
              aria-label={`Victoire de ${team.name}`}
            >
              <Check size={10} strokeWidth={2.5} aria-hidden="true" />
            </span>
          </Tooltip.Trigger>
          <Tooltip.Portal>
            <Tooltip.Content
              className="match-tooltip"
              side="top"
              sideOffset={8}
              collisionPadding={16}
            >
              Victoire de {team.name}
              <Tooltip.Arrow className="match-tooltip-arrow" />
            </Tooltip.Content>
          </Tooltip.Portal>
        </Tooltip.Root>
      )}
    </span>
  );
}
function SideRail({ side, team }: { side: 'blue' | 'red' | null | undefined; team: string }) {
  const label = side ? `Côté ${side === 'blue' ? 'bleu' : 'rouge'}` : 'Camp non renseigné';
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <span
          className="map-side-rail"
          data-side={side ?? 'unknown'}
          role="img"
          tabIndex={0}
          aria-label={`${team} · ${label}`}
        >
          <span className="map-side-rail-line" aria-hidden="true" />
        </span>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="match-tooltip" side="top" sideOffset={8} collisionPadding={16}>
          {label}
          <Tooltip.Arrow className="match-tooltip-arrow" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
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
      <SideRail side={side?.side} team={team.name} />
      <div className="map-team-identity">
        <TeamEmblem team={team} winner={active.winnerId === team.id} />
        <h4>{team.name}</h4>
      </div>
      {bans.length ? (
        <ul className="ban-portraits" aria-label={`Champions bannis par ${team.name}`}>
          {bans.map((ban, index) => {
            const label = championName(ban.champion) ?? 'Champion non identifié';
            return (
              <li key={index}>
                <Tooltip.Root>
                  <Tooltip.Trigger asChild>
                    <span
                      tabIndex={0}
                      role="img"
                      className="ban-portrait-target"
                      aria-label={`${label}, banni par ${team.name}`}
                    >
                      <UpdatedValue value={ban.champion ?? ban.championImage}>
                        <Logo
                          src={championAsset(ban.champion, ban.championImage)}
                          name={label}
                          className="ban-portrait"
                        />
                      </UpdatedValue>
                    </span>
                  </Tooltip.Trigger>
                  <Tooltip.Portal>
                    <Tooltip.Content
                      className="match-tooltip"
                      side="top"
                      sideOffset={8}
                      collisionPadding={16}
                    >
                      {label}
                      <Tooltip.Arrow className="match-tooltip-arrow" />
                    </Tooltip.Content>
                  </Tooltip.Portal>
                </Tooltip.Root>
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
  refreshError,
}: {
  match: EsportMatch;
  catalog: Catalog;
  open: boolean;
  onClose: () => void;
  refreshError?: string | null;
}) {
  const home = catalog.teams.find((t) => t.id === match.homeId)!;
  const away = catalog.teams.find((t) => t.id === match.awayId)!;
  return (
    <Modal
      open={open}
      onOpenChange={(value) => {
        if (!value) onClose();
      }}
      title={
        <>
          <UpdatedValue value={home.code || home.name} />{' '}
          <MatchScore match={match} fallback="contre" />{' '}
          <UpdatedValue value={away.code || away.name} />
        </>
      }
      description={`${catalog.leagues.find((l) => l.id === match.leagueId)?.name} · ${dateTime(match.startsAt)} · Heure de Paris`}
      className="match-dialog"
    >
      {refreshError && (
        <p className="match-refresh-notice" role="status">
          {refreshError}
        </p>
      )}
      <Tooltip.Provider delayDuration={160} skipDelayDuration={100}>
        <MatchContent key={match.id} match={match} catalog={catalog} />
      </Tooltip.Provider>
    </Modal>
  );
}
function MatchContent({ match, catalog }: { match: EsportMatch; catalog: Catalog }) {
  const mapSelectionId = useId();
  const roleSelectionId = useId();
  const mapHeadingId = useId();
  const initial =
    match.maps.find((m) => m.status === 'live') ?? match.maps.find((m) => m.status === 'finished');
  const [choice, setChoice] = useState(() => (initial ? String(initial.number) : ''));
  const [role, setRole] = useState('all');
  const active =
    match.maps.find(
      (m) => String(m.number) === choice && ['live', 'finished'].includes(m.status),
    ) ?? initial;
  // Pin the first published card even if this dialog opened before any card
  // existed. Finishing it or publishing the next card must not move the reader.
  if (active && choice !== String(active.number)) setChoice(String(active.number));
  const home = catalog.teams.find((t) => t.id === match.homeId)!;
  const away = catalog.teams.find((t) => t.id === match.awayId)!;
  const winnerId = matchWinnerId(match);
  const hasSeriesScore = Boolean(match.seriesScore) || match.maps.some((map) => map.winnerId);
  const mapNumbers = match.format
    ? Array.from({ length: Number(match.format.slice(2)) }, (_, i) => i + 1)
    : match.maps.map((map) => map.number).sort((a, b) => a - b);
  const showMapTabs = mapNumbers.length > 1;
  return (
    <motion.div className="match-detail-scroll" layoutScroll>
      <div className="match-scoreboard">
        <div
          className={`scoreboard-team ${winnerId === home.id ? 'is-winner' : winnerId ? 'is-loser' : ''}`}
        >
          <TeamEmblem team={home} winner={winnerId === home.id} />
          <strong>
            <UpdatedValue value={home.name} />
          </strong>
        </div>
        <div className="series-summary">
          <span className="series-format">
            <UpdatedValue value={match.format ?? 'Format inconnu'} />
          </span>
          <strong>
            <MatchScore match={match} fallback={match.status === 'scheduled' ? 'vs' : '—'} />
          </strong>
          <UpdatedValue value={match.status}>
            {match.status === 'live' ? (
              <span className="live-badge">
                <span aria-hidden="true" />
                En direct
              </span>
            ) : (
              <span>
                {match.status === 'finished' ? (
                  'Terminé'
                ) : match.status === 'cancelled' ? (
                  'Annulé'
                ) : match.status === 'postponed' ? (
                  'Reporté / interrompu'
                ) : match.currentScore && !hasSeriesScore ? (
                  'Score courant'
                ) : (
                  <Countdown startsAt={match.startsAt} />
                )}
              </span>
            )}
          </UpdatedValue>
        </div>
        <div
          className={`scoreboard-team ${winnerId === away.id ? 'is-winner' : winnerId ? 'is-loser' : ''}`}
        >
          <TeamEmblem team={away} winner={winnerId === away.id} />
          <strong>
            <UpdatedValue value={away.name} />
          </strong>
        </div>
      </div>
      <div className="match-information">
        <UpdatedValue value={match.stage}>{match.stage ?? ''}</UpdatedValue>
        <UpdatedValue value={match.patch}>{match.patch ? `Patch ${match.patch}` : ''}</UpdatedValue>
        {!active && (
          <time
            dateTime={match.updatedAt}
            title={`${scheduledDate(match.updatedAt)} · Heure de Paris`}
          >
            Rencontre relevée <ObservationAge observedAt={match.updatedAt} />
          </time>
        )}
      </div>
      <MatchOdds match={match} home={home} away={away} />
      <Tabs.Root value={active ? String(active.number) : ''} onValueChange={setChoice}>
        {showMapTabs && (
          <Tabs.List className="map-tabs" aria-label="Cartes du match">
            {mapNumbers.map((number) => {
              const i = number - 1;
              const map = match.maps.find((m) => m.number === number);
              const started = map?.status === 'live' || map?.status === 'finished';
              return (
                <Tabs.Trigger
                  key={i}
                  value={String(i + 1)}
                  disabled={!started}
                  data-live={map?.status === 'live' || undefined}
                  title={
                    map?.winnerId
                      ? `Victoire ${catalog.teams.find((t) => t.id === map.winnerId)?.name ?? ''}`
                      : undefined
                  }
                >
                  {active?.number === number && <SelectionIndicator id={mapSelectionId} />}
                  <strong>Carte {i + 1}</strong>
                  <UpdatedValue
                    value={`${map?.status}:${map?.winnerId}:${map?.status === 'finished' ? map.durationSeconds : ''}`}
                  >
                    {map?.status === 'live'
                      ? 'En direct'
                      : map?.status === 'finished'
                        ? `${catalog.teams.find((t) => t.id === map.winnerId)?.code || 'Terminée'}${formatDuration(map.durationSeconds) ? ` · ${formatDuration(map.durationSeconds)}` : ''}`
                        : map?.status === 'skipped' ||
                            (match.status === 'finished' &&
                              i + 1 > seriesScore(match, home.id) + seriesScore(match, away.id))
                          ? 'Non jouée'
                          : match.status === 'finished'
                            ? 'Non publiée'
                            : 'À venir'}
                  </UpdatedValue>
                </Tabs.Trigger>
              );
            })}
          </Tabs.List>
        )}
        {active ? (
          <Tabs.Content
            value={String(active.number)}
            forceMount
            className="map-content"
            role={showMapTabs ? 'tabpanel' : 'region'}
            aria-labelledby={mapHeadingId}
          >
            <ObservationScope value={active.number}>
              <div className="map-caption">
                <h3 id={mapHeadingId} className={showMapTabs ? undefined : 'sr-only'}>
                  {showMapTabs ? `Carte ${active.number}` : 'Détail de la carte'}
                </h3>
                <span className="map-duration">
                  <Clock3 size={14} />
                  <UpdatedValue
                    value={formatDuration(active.durationSeconds) ?? 'Durée indisponible'}
                  />
                  {active.durationSeconds != null && (
                    <UpdatedValue value={active.status}>
                      · {active.status === 'live' ? 'Temps au dernier relevé' : 'Durée finale'}
                    </UpdatedValue>
                  )}
                </span>
                <span className="map-freshness">
                  {active.updatedAt ? (
                    <time
                      dateTime={active.updatedAt}
                      title={`${scheduledDate(active.updatedAt)} · Heure de Paris`}
                    >
                      Carte relevée <ObservationAge observedAt={active.updatedAt} />
                    </time>
                  ) : (
                    'Heure du relevé de carte non publiée'
                  )}
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
                    <div
                      className="roster-role-filters"
                      role="group"
                      aria-label="Comparer les joueurs par poste"
                    >
                      <button
                        type="button"
                        aria-pressed={role === 'all'}
                        aria-label="Tous les postes"
                        onClick={() => setRole('all')}
                      >
                        {role === 'all' && <SelectionIndicator id={roleSelectionId} />}
                        Tous
                      </button>
                      {Object.entries(roleMeta).map(([key, meta]) => (
                        <Tooltip.Root key={key}>
                          <Tooltip.Trigger asChild>
                            <button
                              type="button"
                              aria-pressed={role === key}
                              aria-label={meta.label}
                              onClick={() => setRole(key)}
                            >
                              {role === key && <SelectionIndicator id={roleSelectionId} />}
                              <img src={meta.icon} alt="" width="22" height="22" />
                            </button>
                          </Tooltip.Trigger>
                          <Tooltip.Portal>
                            <Tooltip.Content
                              className="match-tooltip"
                              side="top"
                              sideOffset={8}
                              collisionPadding={16}
                            >
                              {meta.label}
                              <Tooltip.Arrow className="match-tooltip-arrow" />
                            </Tooltip.Content>
                          </Tooltip.Portal>
                        </Tooltip.Root>
                      ))}
                    </div>
                  </div>
                  <div className="map-teams">
                    {[home, away]
                      .map((team) => active.sides.find((side) => side.teamId === team.id))
                      .filter((side): side is MapSide => Boolean(side))
                      .map((side) => (
                        <TeamStats key={side.teamId} side={side} catalog={catalog} role={role} />
                      ))}
                  </div>
                </>
              ) : (
                <div className="match-pending">
                  <Clock3 size={25} />
                  <h3>Statistiques de carte indisponibles</h3>
                  <p>
                    Les statistiques apparaîtront si elles sont publiées. Le dernier score
                    disponible reste affiché.
                  </p>
                </div>
              )}
            </ObservationScope>
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
                ? 'Le dernier score disponible est affiché. Les détails apparaîtront si la source les publie.'
                : match.status === 'finished'
                  ? 'Les détails des cartes ne sont pas encore disponibles pour cette rencontre.'
                  : match.status === 'cancelled' || match.status === 'postponed'
                    ? 'Le statut sera actualisé dès que la source publiera une nouvelle information.'
                    : 'Compositions, côtés et statistiques apparaîtront pendant la rencontre, selon leur disponibilité.'}
            </p>
          </div>
        )}
      </Tabs.Root>
    </motion.div>
  );
}
