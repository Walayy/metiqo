import { useState } from 'react';
import { Tabs } from 'radix-ui';
import {
  Ban,
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

function ObjectiveStats({ side }: { side: MapSide }) {
  const gold = sideGold(side);
  const values: Record<ObjectiveKey, number | string> = {
    kills: sideKills(side),
    gold: gold == null ? '—' : `${decimal(gold / 1000, 1)} k`,
    towers: side.towers ?? '—',
    dragons: side.dragons ?? '—',
    barons: side.barons ?? '—',
    heralds: side.heralds ?? '—',
    grubs: side.grubs ?? '—',
    inhibitors: side.inhibitors ?? '—',
  };
  return (
    <dl className="map-objectives">
      {objectiveMeta.map(({ key, label, icon: Icon, className }) => (
        <div className={`objective-stat objective-stat--${className}`} key={key}>
          <dt>
            <span className="objective-icon" aria-hidden="true">
              <Icon size={14} strokeWidth={1.8} />
            </span>
            <span className="objective-label">{label}</span>
          </dt>
          <dd>{values[key]}</dd>
        </div>
      ))}
    </dl>
  );
}

function TeamStats({
  side,
  catalog,
  winner,
}: {
  side: MapSide;
  catalog: Catalog;
  winner: boolean;
}) {
  const team = catalog.teams.find((t) => t.id === side.teamId);
  if (!team) return null;
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
      <ObjectiveStats side={side} />
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
                  <span className="roster-role-label">{roleMeta[player.role].label}</span>
                  <span>{championLabel}</span>
                  {player.level != null && ` · niv. ${player.level}`}
                </span>
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

function DraftBans({ active, catalog }: { active: MatchMap; catalog: Catalog }) {
  if (!active.bans.length)
    return (
      <section className="map-bans" aria-label="Champions bannis">
        <div className="ban-heading">
          <span className="ban-heading-icon" aria-hidden="true">
            <Ban size={15} />
          </span>
          <div>
            <strong>Draft &amp; bans</strong>
            <span>Bans indisponibles pour le moment.</span>
          </div>
        </div>
      </section>
    );
  const teamIds = Array.from(new Set(active.bans.map((ban) => ban.teamId)));
  return (
    <section className="map-bans" aria-label="Champions bannis">
      <div className="ban-heading">
        <span className="ban-heading-icon" aria-hidden="true">
          <Ban size={15} />
        </span>
        <div>
          <strong>Draft &amp; bans</strong>
          <span>
            {active.bans.length} interdiction{active.bans.length > 1 ? 's' : ''} publiée
            {active.bans.length > 1 ? 's' : ''}
          </span>
        </div>
      </div>
      <div className="ban-teams">
        {teamIds.map((teamId) => {
          const team = catalog.teams.find((item) => item.id === teamId);
          const teamBans = active.bans.filter((ban) => ban.teamId === teamId);
          return (
            <div className="ban-team" key={teamId}>
              <div className="ban-team-label">
                {team && <Logo src={team.image} name={team.name} code={team.code} />}
                <strong>{team?.code ?? 'Équipe'}</strong>
                <span>
                  {teamBans.length} ban{teamBans.length > 1 ? 's' : ''}
                </span>
              </div>
              <div className="ban-list">
                {teamBans.map((ban, index) => (
                  <span
                    className="ban-chip"
                    key={`${ban.teamId}-${ban.champion}-${index}`}
                    title={`${team?.name ?? 'Équipe'} · ${ban.champion}`}
                  >
                    <Logo
                      src={championAsset(ban.champion, ban.championImage)}
                      name={ban.champion}
                      code={ban.champion.slice(0, 2)}
                      className="ban-icon"
                    />
                    <span>{ban.champion}</span>
                  </span>
                ))}
              </div>
            </div>
          );
        })}
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
                {active.durationSeconds == null
                  ? 'Durée indisponible'
                  : `${Math.floor(active.durationSeconds / 60)}:${String(active.durationSeconds % 60).padStart(2, '0')} · ${
                      active.status === 'live' ? 'Temps au dernier relevé' : 'Durée finale'
                    }`}
              </span>
            </div>
            <DraftBans active={active} catalog={catalog} />
            {active.sides.length ? (
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
            <h3>{match.status === 'live' ? 'Le direct est en cours.' : 'Le match se prépare.'}</h3>
            <p>
              {match.status === 'live'
                ? 'Le dernier score est affiché dès qu’il est rendu par SofaScore. Les compositions, bans et statistiques restent vides tant que la source ne les publie pas.'
                : 'Compositions, choix des côtés et statistiques apparaîtront dès le premier relevé de la partie.'}
            </p>
          </div>
        )}
      </Tabs.Root>
    </div>
  );
}
